# -*- coding: utf-8 -*-
"""
S02 - 入院诊断不一致检测 (Agent Style)
"""
import re
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json

## 现在的入院诊断遗漏是几个特别简单的规则，但实际需要按病种，匹配是否在DRG的分组 编码中出现过
## 或者维护一个大列表 或者根据统计信息，

SKILL_CONFIG = SkillConfig(
    skill_id="S02",
    skill_name="入院诊断不一致检测",
    description="对比入院诊断与病历资料，检测遗漏的合并症和诊断不一致",

    trigger_rules=[
        "当用户进入'入院记录'流程时自动激活",
        "当入院诊断字段存在时触发",
        "当既往史中包含慢性病时重点检查",
    ],

    capabilities=[
        "检测入院诊断是否遗漏病历中提及的合并症",
        "检测入院诊断与主诉/现病史的一致性",
        "对比外院诊断与本院入院诊断的差异",
        "检查是否缺少必要的分期信息",
    ],

    execution_steps=[
        "Step 1: 提取入院诊断、既往史、主诉",
        "Step 2: 识别既往史中的所有慢性病",
        "Step 3: 识别既往史中的否定表述（如'否认高血压、糖尿病'、'无手术史'），否定表述的疾病自动排除，不判为遗漏",
        "Step 4: 逐项检查每个合并症是否在入院诊断中体现",
        "Step 5: 检查主诉与入院诊断的语义一致性",
        "Step 6: 汇总所有不一致项，给出建议",
    ],

    constraints=[
        "只报告有明确证据的遗漏，不得凭空猜测",
        "既往史出现'否认/无/未见/阴性'等否定表述的疾病，视为未患该病，不得检为遗漏合并症，除非病历中有独立、明确的阳性证据",
        "不得引用入院时点之后才产生的病历内容（如出院诊断、手术记录、病案首页）作为证据",
        "必须引用病历原文作为依据",
        "如无遗漏，返回空的warnings列表",
        "置信度低于0.7时需标注'待人工复核'",
    ],

    required_fields=[
        "诊断(tbl_dia_all_diagnoses).入院诊断",
        "入院记录.既往史",
        "入院记录.主诉",
    ],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.85,
        "入院诊断": "当前入院诊断",
        "检出合并症": [
            {"疾病": "疾病名称", "证据": "证据原文", "状态": "遗漏/完整"}
        ],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科临床医学专家，专注于病历质量控制。

## 任务
{SKILL_CONFIG.description}

## 执行步骤
{chr(10).join(SKILL_CONFIG.execution_steps)}

## 约束规则
{chr(10).join('- ' + c for c in SKILL_CONFIG.constraints)}

## 输出格式
请严格按照以下JSON格式返回：
{{
    "总结": "一句话结论",
    "置信度": 0.85,
    "入院诊断": "当前入院诊断",
    "检出合并症": [
        {{"疾病": "疾病名称", "证据": "病历中的证据原文", "状态": "遗漏/完整"}}
    ],
    "标注": [
        {{"所属部分": "入院记录/既往史", "原文片段": "病历原文片段(含证据,如'药物过敏史：青霉素')", "问题": "问题(遗漏类需注明'未在入院诊断中体现')", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": ["问题1"],
    "建议": ["建议1"]
}}
用中文回答。

## 原文标注要求
若检出问题直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "入院记录/既往史"、"入院记录/主诉"、"诊断/入院诊断" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 纠正或处理建议。
对于"某合并症/既往史未录入入院诊断"这类遗漏问题, 同样必须在"原文片段"填写病历中支持该发现的证据原文(如既往史中的慢性病描述), "所属部分"指向证据所在章节(如 "入院记录/既往史"), 并在"问题"中说明"未在入院诊断中体现"。只有确无任何证据原文时才允许留空。无需标注时返回 []。

## 否定表述处理(必须严格遵守)
既往史中"否认×××"、"无×××"、"未见×××"、"×阴性"、"未患×××"等否定表述的疾病, 表示患者未患该病:
- 一律不得将其检出为"遗漏合并症", 也不得在"警告"中提及该病。
- 不得把否定表述当作"已患该病"的证据。
- 仅当病历中存在独立的阳性证据(如体格检查、检查报告明确提示该病)时, 才可检出, 且必须在"证据"中引用该阳性原文。
例如既往史写"否认高血压、糖尿病、冠心病等基础疾病"时, 高血压、糖尿病、冠心病均不得检出。"""


NEGATORS = ("否认", "无", "没有", "未患", "未见", "阴性")
CLAUSE_SEPS = ("。", "；", ";", "，", ",")


def _is_negated(past_history: str, disease: str) -> bool:
    """判断既往史中该疾病是否被否定表述覆盖(如'否认高血压、糖尿病、冠心病')"""
    text = re.sub(r"\s+", "", past_history or "")
    disease = re.sub(r"\s+", "", disease or "")
    if not text or not disease:
        return False
    pos = 0
    while True:
        idx = text.find(disease, pos)
        if idx < 0:
            return False
        # 以句级分隔符(。；;，,)划分否定管辖范围; 顿号'、'是列举分隔, 不切断'否认…A、B、C'
        seps = [text.rfind(s, 0, idx) for s in CLAUSE_SEPS]
        seps = [s for s in seps if s >= 0]
        clause_start = max(seps) + 1 if seps else 0
        clause = text[clause_start:idx]
        if any(n in clause for n in NEGATORS):
            return True
        # 否定在后: "外伤史：无" / "手术史：无"
        tail = text[idx + len(disease):idx + len(disease) + 6]
        if tail.startswith("史") and (tail.startswith("：无", 1) or tail.startswith(":无", 1) or tail.startswith("无", 1)):
            return True
        pos = idx + len(disease)


class DiagnosisInconsistencyDetector(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        def norm(s: str) -> str:
            return "".join(s.split())
        diag_key = next((k for k in patient_data if norm(k) == "诊断(tbl_dia_all_diagnoses)"), None)
        ruyi = patient_data.get(diag_key, {}) if diag_key else {}
        adm_rec = patient_data.get("入院记录") or {}
        admission_dx = ruyi.get("入院诊断", "")
        past_history = adm_rec.get("既往史", "")
        chief_complaint = adm_rec.get("主诉", "")

        user_prompt = f"""请按以下步骤检查入院诊断:

【入院诊断】
{admission_dx}

【既往史】
{past_history}

【主诉】
{chief_complaint}

【患者完整病历】
{context}

请严格按照执行步骤进行分析，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        for cond in raw_result.get("检出合并症", []):
            if "证据" not in cond:
                cond["证据"] = "待补充"
        past_history = (patient_data.get("入院记录") or {}).get("既往史", "")
        kept = []
        for cond in raw_result.get("检出合并症", []):
            if _is_negated(past_history, cond.get("疾病", "")):
                raw_result.setdefault("警告", []).append(
                    f"既往史为否定表述（否认…{cond.get('疾病', '')}），不纳入遗漏合并症"
                )
                continue
            kept.append(cond)
        raw_result["检出合并症"] = kept
        confidence = raw_result.get("置信度", 0.85)
        if confidence < 0.7:
            raw_result.setdefault("建议", []).append("置信度较低，建议人工复核")
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        return {
            "总结": result.get("总结", ""),
            "置信度": result.get("置信度", 0.85),
            "入院诊断": result.get("入院诊断", ""),
            "检出合并症": result.get("检出合并症", []),
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", []),
        }
