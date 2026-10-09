# -*- coding: utf-8 -*-
"""
S08 - 出院医嘱生成 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

# 条目模板

POSTOP_GUIDELINE = load_guideline("03_术后治疗指征.md")
OPC_GUIDELINE = load_guideline("05_口咽癌诊疗要点.md")
THYROID_GUIDELINE = load_guideline("06_甲状腺癌诊疗要点.md")
THYROID_GUIDELINE_SUMMARY = load_guideline("07_甲状腺癌诊疗要点汇总.md")
GLOSSARY = load_guideline("10_专业术语词汇表.md")

SKILL_CONFIG = SkillConfig(
    skill_id="S08",
    skill_name="出院护理服务包及医嘱生成",
    description="依据手术记录、病程记录、病理报告协助生成出院护理服务包及出院医嘱",

    trigger_rules=[
        "当用户进入'出院护理服务包及医嘱'流程时自动激活",
        "当手术记录、病理报告均存在时触发",
    ],

    capabilities=[
        "生成药物医嘱",
        "制定饮食和活动建议",
        "安排随访计划",
        "评估辅助治疗需求",
        "提取并解释专有名词",
    ],

    execution_steps=[
        "Step 1: 提取手术记录",
        "Step 2: 提取病理结果",
        "Step 3: 生成药物医嘱",
        "Step 4: 制定饮食和活动建议",
        "Step 5: 安排随访计划",
        "Step 6: 评估辅助治疗需求",
        "Step 7: 提取并解释病历中的专有名词",
    ],

    constraints=[
        "药物剂量和用法必须准确",
        "随访安排必须符合指南",
        "必须包含注意事项",
    ],

    required_fields=["手术记录", "病理检查报告单(tbl_std_pis_reports)", "出院记录"],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
        "CT报告单(tbl_std_reports)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.9,
        "病理分期": {
            "pT": "", "pN": "", "M": "", "分期": "",
            "依据": "", "分期体系": "", "状态": "确定/待MDT复核",
        },
        "药物": [{"项目": "", "疗程": "", "备注": ""}],
        "饮食": [],
        "活动": [],
        "伤口护理": [],
        "随访": [{"时间": "", "项目": ""}],
        "辅助治疗": {"建议": "", "理由": "", "时机": ""},
        "注意事项": [],
        "术语解释": [{"术语": "", "解释": "", "来源": ""}],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
        "参考": [{"要点": "遵循的指南条目简述", "来源": "来源页码"}],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科临床医生，擅长制定出院医嘱。

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
    "置信度": 0.9,
    "病理分期": {{"pT": "pT4a", "pN": "pN1", "M": "cM0", "分期": "IVA期", "依据": "浸润深度/淋巴结数/ENE/切缘等推断要点", "分期体系": "按病种选择(AJCC第8版: 甲状腺癌/口咽癌p16±/头颈鳞癌)", "状态": "确定"}},
    "药物": [{{"项目": "药物 剂量 用法", "疗程": "疗程", "备注": "备注"}}],
    "饮食": ["饮食建议"],
    "活动": ["活动建议"],
    "伤口护理": ["护理建议"],
    "随访": [{{"时间": "时间", "项目": "检查项目"}}],
    "辅助治疗": {{"建议": "建议", "理由": "理由", "时机": "时间"}},
    "注意事项": ["注意事项"],
    "术语解释": [{{"术语": "术语名称", "解释": "简洁权威的解释", "来源": "权威来源如AJCC/CSCO/NCCN/UpToDate"}}],
    "标注": [
        {{"所属部分": "出院记录/出院医嘱", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": [],
    "参考": [{{"要点": "遵循的指南条目简述", "来源": "来源页码"}}]
}}
用中文回答。

## 病理分期推断要求
即使病理检查报告单的"病理分期"字段为空或"找不到数据", 也必须依据术后病理与影像数据逐项推断 pT/pN/M 并给出依据, 用于辅助治疗决策:
- **pT**: 依据病理报告浸润深度(DOI)、面积/最大径、累及结构(骨骼肌/邻近结构)及影像原发灶范围; 甲状腺癌依据肿瘤最大径、是否超出甲状腺被膜、累及带状肌/邻近组织等。
- **pN**: 依据颈清扫病理淋巴结总数/阳性数/分区/有无ENE(如"33枚中2枚见癌转移，IIa/III区，无ENE"); 甲状腺癌还需注明中央区(VI区)与侧颈区转移、淋巴结最大径。
- **M**: 依据胸部/腹部影像或PET/CT远处转移征象; 未行检查则标注"cM0推定"并提示补齐。
- 分期体系按病种选择: 口咽癌用 p16 状态对应的 AJCC第8版体系(需区分阳性/阴性); 甲状腺癌用 AJCC第8版甲状腺癌TNM(分化型癌以55岁为年龄界、MTC无年龄分层); 喉/下咽/颈段食管癌用 AJCC第8版头颈鳞癌TNM。在"分期体系"字段注明。
- "依据"须引用病历原文关键数据, 不得编造; 有据可依时不得写"不清楚/无法确定"。
- 仅当某方面确实无任何数据时, 才允许标注"待补齐检查"并在"建议"列出需补检查。
- "状态": 依据充分为"确定"; 存在MDT需复核的临界点(如切缘极近、ENE边界、p16影响体系)标"待MDT复核"。
- 辅助治疗的"理由"必须结合推断出的分期与术后风险分层(一般高危→术后放疗; 最高危如切缘阳性/不足或ENE+→同步放化疗)。甲状腺癌术后辅助治疗按复发风险分层(RAI指征/LT4-TSH抑制/高风险外照射), 与鳞癌不同。

## 原文标注要求
若出院医嘱或随访安排直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "出院记录/出院医嘱"、"手术记录/手术名称"、"病理检查报告单/病理分期" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
无需标注时返回 []。

## 临床指南参考(专家诊疗要点)
以下要点涵盖喉癌、下咽癌、颈段食管癌、口咽癌及甲状腺癌五个病种，请根据患者诊断仅采用对应病种条目。

{POSTOP_GUIDELINE}

### 口咽癌诊疗要点
{OPC_GUIDELINE}

### 甲状腺癌诊疗要点
{THYROID_GUIDELINE}

### 甲状腺癌诊疗要点汇总(路径速查)
{THYROID_GUIDELINE_SUMMARY}

## 指南遵循要求
1. 出院后的辅助治疗、随访计划及第二原发癌监测必须依据上述《术后治疗指征》要点。
2. 若与指南内容冲突，须明确说明理由及依据。

## 引用要求
辅助治疗、随访等关键建议必须在"参考"字段注明所依据的指南条目及来源页码。若无指南依据，参考填 []。

## 专业术语解释要求
在"术语解释"字段中，提取本病例病历、病理报告、出院医嘱中出现的所有专有名词（包括但不限于分期术语、病理指标、手术名称、药物名称、检查项目、DRG编码等），逐一给出简洁权威的解释。解释须注明权威来源（如AJCC分期手册、CSCO指南、NCCN指南、UpToDate、病理学教材等）。参考下方《头颈肿瘤专业术语词汇表》确保解释准确。

{GLOSSARY}"""


class DischargeOrderGenerator(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请为以下患者生成出院医嘱:

{context}

请按照执行步骤进行分析，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        meds = result.get("药物", [])
        return {
            "总结": result.get("总结", f"已生成出院医嘱，含{len(meds)}项药物医嘱"),
            "置信度": result.get("置信度", 0.9),
            "病理分期": result.get("病理分期", {}),
            "药物": meds,
            "饮食": result.get("饮食", []),
            "活动": result.get("活动", []),
            "伤口护理": result.get("伤口护理", []),
            "随访": result.get("随访", []),
            "辅助治疗": result.get("辅助治疗", {}),
            "注意事项": result.get("注意事项", []),
            "术语解释": result.get("术语解释", []),
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", []),
            "参考": result.get("参考", []),
        }
