# -*- coding: utf-8 -*-
"""
S03 - 医嘱遗漏检测 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

## 医嘱 指南 模板

PREOP_GUIDELINE = load_guideline("01_术前推荐检查.md")
OPC_GUIDELINE = load_guideline("05_口咽癌诊疗要点.md")
THYROID_GUIDELINE = load_guideline("06_甲状腺癌诊疗要点.md")
THYROID_GUIDELINE_SUMMARY = load_guideline("07_甲状腺癌诊疗要点汇总.md")

SKILL_CONFIG = SkillConfig(
    skill_id="S03",
    skill_name="医嘱遗漏检测",
    description="检测入院后应开但未开的药物、检查、检验",

    trigger_rules=[
        "当用户进入'入院记录'流程时自动激活",
        "当医嘱数据存在时触发",
    ],

    capabilities=[
        "根据诊断检查必要的药物医嘱",
        "根据手术类型检查术前检查完整性",
        "检查药物剂量和用法合理性",
        "检查检验时效性: 报告日期是否在临床有效期内, 过期应重做",
    ],

    execution_steps=[
        "Step 1: 提取当前所有医嘱",
        "Step 2: 根据诊断确定应开药物清单",
        "Step 3: 根据手术类型确定术前检查清单",
        "Step 4: 逐项对比，标记遗漏",
        "Step 5: 检查检验时效性核查: 逐项核对已做检查/检验的报告日期与入院日期的间隔, 判断是否过期应重做",
    ],

    constraints=[
        "只报告确实遗漏的项目",
        "必须说明遗漏的理由",
        "紧急用药遗漏需高优先级标注",
        "报告日期缺失时按'时间不详'标注并提示补充",
        "仅报告'已过期应重做'的检查检验, 有效期内项目不列入",
    ],

    required_fields=[
        "诊断(tbl_dia_all_diagnoses).入院诊断",
        "长期医嘱单/临时医嘱单 (至少其一)",
    ],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
        "CT报告单(tbl_std_reports)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.85,
        "现有医嘱": {"药物": [], "检查": []},
        "遗漏医嘱": [
            {"项目": "项目", "类别": "类别", "原因": "理由", "优先级": "高/中/低", "依据": "指南依据"}
        ],
        "检查检验时效性": [
            {
                "检查项目": "项目",
                "报告日期": "YYYY-MM-DD 或 时间不详",
                "距入院天数": 0,
                "是否过期": "是/否",
                "过期天数": 0,
                "是否需重做": "是/否",
                "需重做原因": "已过期X天/其他",
                "建议": "处理建议",
            }
        ],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
        "参考": [{"要点": "遵循的指南条目简述", "来源": "来源页码"}],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科临床医生，擅长审核医嘱。

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
    "现有医嘱": {{"药物": ["已开药物"], "检查": ["已开检查"]}},
    "遗漏医嘱": [
        {{"项目": "遗漏项目", "类别": "药物/检查/检验", "原因": "理由", "优先级": "高/中/低", "依据": "依据的指南条目"}}
    ],
    "检查检验时效性": [
        {{
            "检查项目": "检查/检验名称",
            "报告日期": "YYYY-MM-DD 或 时间不详",
            "距入院天数": 0,
            "是否过期": "是/否",
            "过期天数": 0,
            "是否需重做": "是/否",
            "需重做原因": "已过期X天",
            "建议": "处理建议"
        }}
    ],
    "标注": [
        {{"所属部分": "长期医嘱单", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": [],
    "参考": [{{"要点": "遵循的指南条目简述", "来源": "来源页码"}}]
}}
用中文回答。

## 检查检验时效性核查规则(Step 5)
对病历中已有的每项术前检查/检验, 依据其"检查日期"(报告章节的"检查日期"字段)与"入院日期"(病案首页/入院记录)计算间隔天数, 逐项判断:
1. 临床有效期限(按检查类型):
   - 血常规/生化/凝血等检验: 不超过7天
   - 心电图/胸片: 不超过1个月
   - 电子喉镜/CT/MRI/超声/电子胃镜等影像与内镜: 不超过3个月
   - 病理: 以术前为主
2. 判定规则:
   - 超过上述期限 -> "是否过期"=是, "过期天数"=超期天数, "是否需重做"=是
   - 未过期 -> "是否需重做"=否
   - 无检查日期 -> "报告日期"=时间不详, 在"建议"中提示补充检查日期
3. "距入院天数"=入院日期减去报告日期的天数(报告日期晚于入院时为0或负数均可, 负数表示入院后所做)。
4. 对"是否需重做"=是的项目, 仅在"检查检验时效性"中列出并在该条目的"需重做原因"中标注"已过期X天，应重做", 不要重复放入"遗漏医嘱"。

## 原文标注要求
若检出问题直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "长期医嘱单"、"临时医嘱单"、"入院记录/辅助检查"、"病理检查报告单" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
若问题是"某检查/药物遗漏"而无对应原文片段, "原文片段"留空, "所属部分"指向应出现但缺失的位置(如 "长期医嘱单")。无需标注时返回 []。

## 临床指南参考(专家诊疗要点)
以下要点涵盖喉癌、下咽癌、颈段食管癌、口咽癌及甲状腺癌五个病种，请根据患者入院诊断仅采用对应病种条目。

{PREOP_GUIDELINE}

### 口咽癌诊疗要点
{OPC_GUIDELINE}

### 甲状腺癌诊疗要点
{THYROID_GUIDELINE}

### 甲状腺癌诊疗要点汇总(路径速查)
{THYROID_GUIDELINE_SUMMARY}

## 指南遵循要求
1. 判断"应开但未开的检查、检验、药物"必须依据上述《术前推荐检查》要点逐项核对。
2. 若与指南内容冲突，须明确说明理由及依据。

## 引用要求
每条遗漏医嘱必须在"依据"字段注明所依据的指南条目；并在"参考"字段列出本次输出的主要指南引用及来源页码。若无指南依据，参考填 []。"""


class OrderGapDetector(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _validate_input(self, patient_data: Dict) -> List[str]:
        def norm(s: str) -> str:
            return "".join(s.split())
        norm_data = {norm(k): k for k in patient_data}
        missing = []
        diag_key = norm_data.get(norm("诊断(tbl_dia_all_diagnoses)"))
        if not (diag_key and patient_data.get(diag_key, {}).get("入院诊断")):
            missing.append("诊断(tbl_dia_all_diagnoses).入院诊断")
        lt = patient_data.get(norm_data.get(norm("长期医嘱单(tbl_mar_medication_orders_cdt_order_term)")))
        tmp = patient_data.get(norm_data.get(norm("临时医嘱单(tbl_mar_medication_orders_cdt_order_term)")))
        if not lt and not tmp:
            missing.append("长期医嘱单/临时医嘱单 (至少其一)")
        return missing

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请检查以下患者的医嘱是否完整:

{context}

请按照执行步骤进行检查，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        import re as _re
        for m in raw_result.get("遗漏医嘱", []):
            m.setdefault("依据", "")
        for t in raw_result.get("检查检验时效性", []):
            t.setdefault("报告日期", "时间不详")
            t.setdefault("距入院天数", 0)
            t.setdefault("是否过期", "否")
            t.setdefault("过期天数", 0)
            t.setdefault("是否需重做", "否")
            t.setdefault("需重做原因", "")
            t.setdefault("建议", "")
            # 过期天数<=0 时修正"已过期0天"表述, 避免矛盾文案
            oday = t.get("过期天数") or 0
            if oday <= 0:
                t["需重做原因"] = _re.sub(r"已过期\s*0\s*天", "已超出有效期限", t.get("需重做原因", ""))
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        import re as _re
        missing = result.get("遗漏医嘱", [])
        timeliness = result.get("检查检验时效性", [])
        warnings = list(result.get("警告", []))
        # 时效性需重做项并入"发现的问题"; 若与遗漏医嘱同名(去掉"重做"等修饰)则合并, 避免重复
        def _norm(s):
            s = _re.sub(r"（[^）]*）", "", s or "")
            s = _re.sub(r"\([^)]*\)", "", s)
            s = _re.sub(r"^(重做|复查|再次)", "", s)
            return "".join(s.split())
        warned_missing = {}
        for m in missing:
            w = {
                "type": "遗漏医嘱",
                "项目": m.get("项目", ""),
                "类别": m.get("类别", ""),
                "原因": m.get("原因", ""),
                "优先级": m.get("优先级", "中"),
                "依据": m.get("依据", ""),
            }
            warnings.append(w)
            warned_missing.setdefault(_norm(m.get("项目", "")), w)
        for t in timeliness:
            if t.get("是否需重做") == "是":
                dup = warned_missing.get(_norm(t.get("检查项目", "")))
                if dup is not None and dup.get("项目"):
                    # 已在遗漏医嘱中存在: 合并时效信息, 不重复入列
                    dup.setdefault("报告日期", t.get("报告日期", ""))
                    dup.setdefault("距入院天数", t.get("距入院天数", 0))
                    dup.setdefault("是否过期", t.get("是否过期", "否"))
                    dup.setdefault("过期天数", t.get("过期天数", 0))
                    dup.setdefault("建议", t.get("建议", ""))
                    dup["_merged_timeliness"] = True
                    continue
                warnings.append({
                    "type": "检查检验时效性",
                    "项目": t.get("检查项目", ""),
                    "类别": "检查/检验",
                    "原因": t.get("需重做原因", "") or t.get("建议", ""),
                    "优先级": "中",
                    "依据": "检查检验时效性核查(Step 5)",
                    "报告日期": t.get("报告日期", ""),
                    "距入院天数": t.get("距入院天数", 0),
                    "是否过期": t.get("是否过期", "否"),
                    "过期天数": t.get("过期天数", 0),
                    "建议": t.get("建议", ""),
                })
        return {
            "总结": result.get("总结", f"发现{len(missing)}项可能遗漏的医嘱"),
            "置信度": result.get("置信度", 0.85),
            "现有医嘱": result.get("现有医嘱", {}),
            "遗漏医嘱": missing,
            "检查检验时效性": timeliness,
            "标注": result.get("标注", []),
            "警告": warnings,
            "建议": result.get("建议", []),
            "参考": result.get("参考", []),
        }
