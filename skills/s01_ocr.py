# -*- coding: utf-8 -*-
"""
S01 - 外院病历OCR识别 (Agent Style)
识别流程: 本地RapidOCR提取文字 -> 可选LLM结构化提取字段
无需LLM也能完成OCR(返回原始识别文本)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
import os
from utils.llm_client import call_llm_json, LLM_CONFIG
from utils.ocr_engine import ocr_batch, is_available


SKILL_CONFIG = SkillConfig(
    skill_id="S01",
    skill_name="外院病历OCR识别",
    description="识别外院病历、检查报告图片/PDF，提取结构化数据",

    trigger_rules=[
        "当用户上传图片或PDF文件时自动激活",
        "支持格式: JPG, PNG, PDF",
        "支持报告类型: 住院病历、检查报告、病理报告、出院小结",
    ],

    capabilities=[
        "本地RapidOCR识别报告图片文字(无需API)",
        "区分不同类型的报告（CT/MRI/喉镜/病理等）",
        "可选: LLM将OCR文本结构化提取关键字段",
        "标注识别置信度低的内容",
    ],

    execution_steps=[
        "Step 1: 识别文件类型（图片/PDF）",
        "Step 2: 本地OCR提取文字内容",
        "Step 3: 判断报告类型",
        "Step 4: 可选LLM结构化提取关键字段",
        "Step 5: 标注识别置信度低的内容",
    ],

    constraints=[
        "必须保留原始图片/文件路径以便追溯",
        "识别置信度低于0.8的内容需标注'待人工确认'",
        "敏感信息（身份证号、手机号）需脱敏处理",
        "识别结果必须与原图可对照",
        "同一PDF文件只输出一条报告, 不要按页拆分; 页码标记(如'—— 第N页 ——')保留在文本中用于区分页面",
    ],

    required_fields=[],

    output_template={
        "总结": "已识别N份报告",
        "置信度": 0.9,
        "报告": [
            {
                "文件名": "文件名",
                "报告类型": "报告类型",
                "文本": "OCR识别全文",
                "提取数据": {},
                "低置信度字段": [],
            }
        ],
        "标注": [
            {"所属部分": "外院报告/文件名", "原文片段": "OCR识别原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
    },
)

SYSTEM_PROMPT = f"""你是一位专业的医学文档识别专家，负责将OCR提取的报告文本整理为结构化数据。

## 任务
{SKILL_CONFIG.description}

## 执行步骤
{chr(10).join(SKILL_CONFIG.execution_steps)}

## 约束规则
{chr(10).join('- ' + c for c in SKILL_CONFIG.constraints)}

## 输出格式
请严格按照以下JSON格式返回：
{{
    "总结": "已识别N份报告",
    "置信度": 0.9,
    "报告": [
        {{
            "文件名": "文件名",
            "报告类型": "CT报告/喉镜报告/出院小结/病理报告",
            "提取数据": {{
                "诊断": "诊断",
                "日期": "检查日期",
                "发现": "检查所见",
                "结论": "结论"
            }},
            "低置信度字段": ["识别不确定的字段"]
        }}
    ],
    "标注": [
        {{"所属部分": "外院报告/文件名", "原文片段": "OCR识别原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": ["建议确认识别结果"]
}}
用中文回答。

## 原文标注要求
仅在OCR文字本身存在明显错误时标注（如乱码、缺字、错字、前后矛盾）。
以下情况**不要标注**: 日期格式差异、数字精度、检查名称缩写、正常医学术语。
同一页内相似问题合并为一条, 每份报告最多2-3条标注。
标注字段说明:
- "所属部分": 外院报告及文件名
- "原文片段": OCR识别出的原文片段
- "问题": 具体错误描述
- "严重度": "高"/"中"/"低"
- "建议": 人工核对建议
无需标注时返回 []。"""


class OCRExtractor(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        images = getattr(self, "_kwargs", {}).get("images", [])
        if not images:
            return {"总结": "未提供报告图片，跳过OCR", "报告": [], "警告": [], "建议": ["请上传外院报告图片"]}

        if not is_available():
            return {"总结": "RapidOCR未安装", "报告": [], "警告": ["请执行 pip install rapidocr_onnxruntime"],
                    "建议": ["安装RapidOCR后重试"]}

        # Step 1-2: 本地OCR逐张提取文字(图片走RapidOCR, PDF走文本抽取/渲染OCR)
        import tempfile
        img_paths = []
        tmp_files = []
        name_map = {}
        try:
            for i in images:
                if isinstance(i, dict) and "data" in i:
                    ext = os.path.splitext(i.get("name", ".jpg"))[1].lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".pdf"):
                        ext = ".jpg"
                    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                    tmp.write(i["data"])
                    tmp.close()
                    img_paths.append(tmp.name)
                    tmp_files.append(tmp.name)
                    name_map[os.path.basename(tmp.name)] = i.get("name") or os.path.basename(tmp.name)
                elif isinstance(i, dict) and "path" in i:
                    img_paths.append(i["path"])
                else:
                    img_paths.append(i)
            ocr_results = ocr_batch([p for p in img_paths if isinstance(p, str)])
            # 回填上传时的原始文件名(临时文件路径会掩盖原名)
            for r in ocr_results:
                orig = name_map.get(r.get("文件名"))
                if orig:
                    r["文件名"] = orig

            # Step 4: 可选LLM结构化
            if LLM_CONFIG["api_key"]:
                llm_result = self._structure_with_llm(ocr_results, context)
                return self._merge_ocr_text(llm_result, ocr_results)

            # 无LLM时直接返回本地OCR结果
            reports = []
            for r in ocr_results:
                low_conf = [x["文字"] for x in r["文本行"] if x["置信度"] < 0.8]
                reports.append({
                    "文件名": r["文件名"],
                    "报告类型": "待确认",
                    "文本": r["文本"],
                    "提取数据": {},
                    "低置信度字段": low_conf,
                })
            return {
                "总结": f"本地OCR识别{len(reports)}份报告",
                "置信度": 0.85,
                "报告": reports,
                "警告": [f"{len(reports)}份报告使用本地OCR识别，建议人工复核"],
                "建议": ["如需自动结构化提取字段，请配置OPENAI_API_KEY"],
            }
        finally:
            for f in tmp_files:
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _merge_ocr_text(self, llm_result: Dict, ocr_results: List[Dict]) -> Dict:
        """将本地OCR/PDF提取的全文合并回LLM结构化结果, 确保原文不丢失。
        若LLM将同一PDF拆为多条报告, 自动合并为一条(保留完整OCR文本)。"""
        if not isinstance(llm_result, dict):
            return llm_result
        reports = llm_result.get("报告", [])
        if not isinstance(reports, list):
            return llm_result
        ocr_by_name = {}
        for r in ocr_results:
            ocr_by_name.setdefault(r.get("文件名", ""), r)
        used = set()
        matched = []  # (llm_report, ocr_result) pairs
        for rep in reports:
            if not isinstance(rep, dict):
                continue
            if rep.get("文本"):
                continue
            match = None
            fname = rep.get("文件名", "")
            if fname in ocr_by_name and fname not in used:
                match = ocr_by_name[fname]
                used.add(fname)
            else:
                for r in ocr_results:
                    if r.get("文件名") not in used:
                        match = r
                        used.add(r.get("文件名"))
                        break
            if match is None:
                continue
            rep["文件名"] = match.get("文件名", rep.get("文件名", ""))
            rep.setdefault("来源", match.get("来源", "OCR"))
            low = [x["文字"] for x in match.get("文本行", []) if x.get("置信度", 1) < 0.8]
            rep["低置信度字段"] = rep.get("低置信度字段") or low
            matched.append((rep, match))

        # 合并: 同一OCR源文件对应的多条LLM报告 -> 保留第一条, 丢弃重复
        seen_ocr = {}
        merged_reports = []
        for rep, ocr_r in matched:
            ocr_key = ocr_r.get("文件名", "")
            if ocr_key in seen_ocr:
                # 同一PDF的后续条目: 合并提取数据(取并集), 丢弃重复文本
                prev = seen_ocr[ocr_key]
                if rep.get("提取数据") and isinstance(rep["提取数据"], dict):
                    prev.setdefault("提取数据", {}).update(rep["提取数据"])
                continue
            # 首次匹配: 使用完整的OCR文本(不按页拆分)
            rep["文本"] = ocr_r.get("文本", "")
            seen_ocr[ocr_key] = rep
            merged_reports.append(rep)

        llm_result["报告"] = merged_reports
        return llm_result

    def _structure_with_llm(self, ocr_results: List[Dict], context: str) -> Dict:
        """将OCR文本交给LLM做结构化字段提取"""
        blocks = []
        for r in ocr_results:
            blocks.append(f"【{r['文件名']}】\n{r['文本']}")
        user_prompt = f"""以下为 {len(ocr_results)} 份外院报告文件(图片OCR或PDF)的识别文本，请逐份整理为结构化数据:

{chr(10).join(blocks)}

【患者病历参考(用于判断报告类型)】
{context}

重要: 同一PDF文件只输出一条报告,不要按页拆分。页码标记(如'—— 第N页 ——')保留在文本中用于区分页面。
请按照执行步骤逐份整理,并以JSON格式返回结构化结果。"""
        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        for report in raw_result.get("报告", []):
            if "低置信度字段" not in report:
                report["低置信度字段"] = []
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        reports = result.get("报告", [])
        return {
            "总结": result.get("总结", f"已识别{len(reports)}份报告"),
            "置信度": result.get("置信度", 0.9),
            "报告": reports,
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", ["请确认OCR识别结果是否准确"]),
        }
