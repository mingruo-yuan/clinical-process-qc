# -*- coding: utf-8 -*-
"""
S06 - 手术方案决策 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

# 指南模板

SURGERY_GUIDELINE = load_guideline("02_手术指征与术式.md")
OPC_GUIDELINE = load_guideline("05_口咽癌诊疗要点.md")
THYROID_GUIDELINE = load_guideline("06_甲状腺癌诊疗要点.md")
THYROID_GUIDELINE_SUMMARY = load_guideline("07_甲状腺癌诊疗要点汇总.md")

SKILL_CONFIG = SkillConfig(
    skill_id="S06",
    skill_name="手术方案决策",
    description="根据检查结果和指南推荐手术方案",

    trigger_rules=[
        "当用户进入'术前讨论'流程时自动激活",
        "当诊断、分期、检查结果均存在时触发",
    ],

    capabilities=[
        "明确肿瘤TNM分期",
        "推荐具体手术方式和入路",
        "说明选择依据和替代方案",
        "列出手术关键注意事项",
    ],

    execution_steps=[
        "Step 1: 提取诊断和分期信息",
        "Step 2: 提取影像学和检查结果",
        "Step 3: 依据病理报告(浸润深度/面积/淋巴结数量及部位/脉管神经侵犯/切缘)与影像(原发灶范围/颈部淋巴结/远处转移征象)逐项确定 T、N、M, 即使'病理分期'字段为空或为占位符(## 找不到数据等)也须推断并给出依据",
        "Step 4: 根据指南确定手术适应证",
        "Step 5: 推荐手术方案",
        "Step 6: 列出替代方案",
        "Step 7: 说明关键注意事项",
    ],

    constraints=[
        "推荐方案必须符合临床指南",
        "必须说明选择依据",
        "必须列出替代方案",
        "关键注意事项必须具体可操作",
        "TNM分期必须逐项给出依据: T依据(如浸润深度/累及结构)、N依据(如淋巴结数量及分区)、M依据(如远处转移影像征象); 有据可依时不得输出'不清楚/无法确定', 即使病理分期字段为空或占位符(## 找不到数据等)也必须推断; 只有当依据确实缺失时才允许标注'待补齐检查'",
        "分期体系按病种选择: 口咽癌用p16阴性/阳性对应的AJCC第8版口咽癌TNM; 甲状腺癌用AJCC第8版甲状腺癌TNM(注意分化型癌以55岁为年龄界、MTC无年龄分层); 喉/下咽/颈段食管癌用AJCC第8版头颈鳞癌TNM。必要时标注'术后病理分期p'或'临床分期c'",
    ],

    required_fields=[
        "诊断(tbl_dia_all_diagnoses).出院诊断",
        "CT报告单(tbl_std_reports)",
        "病理检查报告单(tbl_std_pis_reports)",
    ],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
        "超声心动图报告单(tbl_std_reports)",
        "心电图报告单(tbl_std_reports)",
        "常规通气功能检查(tbl_std_pat)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.9,
        "肿瘤分期": {
            "T": "", "N": "", "M": "", "分期": "",
            "T依据": "", "N依据": "", "M依据": "", "分期体系": "",
            "状态": "确定/待MDT复核",
        },
        "推荐术式": [{"名称": "", "类型": "", "依据": "", "优势": "", "风险": "", "来源": ""}],
        "替代方案": [{"名称": "", "适应证": ""}],
        "关键注意事项": [],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
        "参考": [{"要点": "遵循的指南条目简述", "来源": "来源页码"}],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科手术专家，擅长制定手术方案。

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
    "肿瘤分期": {{"T": "pT4a", "N": "pN1", "M": "cM0", "分期": "IVA期", "T依据": "局灶侵及骨骼肌组织等", "N依据": "右颈部IIa区/III区查见转移癌，33枚中2枚见癌转移", "M依据": "CT未见远处转移征象", "分期体系": "按病种选择(AJCC第8版: 甲状腺癌/口咽癌p16±/头颈鳞癌)", "状态": "确定"}},
    "推荐术式": [{{"名称": "手术名称", "类型": "类型", "依据": "依据", "优势": "优势", "风险": "风险", "来源": "来源页码"}}],
    "替代方案": [{{"名称": "替代术式", "适应证": "适应证"}}],
    "关键注意事项": ["注意事项"],
    "标注": [
        {{"所属部分": "病理检查报告单/病理分期", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": [],
    "参考": [{{"要点": "遵循的指南条目简述", "来源": "来源页码"}}]
}}
用中文回答。

## TNM 分期判定要求
即使病理报告单的"病理分期"字段为空、为占位符(如"找不到数据""## 找不到数据""--""N/A")或完全缺失, 也必须依据现有客观数据逐项推断 T/N/M 并给出依据:
- **T**: 依据病理报告的浸润深度、累及结构(骨骼肌/邻近结构)及影像原发灶范围(如"上下范围约5.5cm""累及软腭/舌根/咽旁间隙"等); 甲状腺癌依据肿瘤最大径、是否超出甲状腺被膜、累及带状肌/邻近组织等。
- **N**: 依据病理报告的淋巴结数量、分区及影像颈部淋巴结情况(如"33枚中2枚见癌转移，IIa/III区"); 甲状腺癌还需注明中央区(VI区)与侧颈区转移、淋巴结最大径。
- **M**: 依据胸部/腹部影像或PET/CT的远处转移征象(如"扫及层面未见明显异常"); 若未行相关检查, 标注"cM0推定"并提示补齐。
- 分期体系按病种选择: 口咽癌用 p16 状态对应的 AJCC第8版体系(需区分阳性/阴性); 甲状腺癌用 AJCC第8版甲状腺癌TNM(分化型癌以55岁为年龄界、MTC无年龄分层); 喉/下咽/颈段食管癌用 AJCC第8版头颈鳞癌TNM。在"分期体系"字段注明。
- 每个 T/N/M 的"依据"必须引用病历原文(可概述但保留关键数据), 不得编造。
- 只有在某一方面确实无任何数据时, 才允许该分项标注"待补齐检查", 并在"建议"中列出需补的检查; 有据可依时不得写"不清楚/无法确定"。
- "状态": 分期与指南/数据吻合且依据充分为"确定"; 存在需MDT复核的临界点(如切缘紧邻、ENE边界、p16状态影响分期体系等)标"待MDT复核"。

## 原文标注要求
若分期或术式决策直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "病理检查报告单/病理分期"、"诊断/出院诊断"、"手术记录/手术名称"、"CT报告单" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
无需标注时返回 []。

## 临床指南参考(专家诊疗要点)
以下要点涵盖喉癌、下咽癌、颈段食管癌、口咽癌及甲状腺癌五个病种，请根据患者诊断仅采用对应病种条目。

{SURGERY_GUIDELINE}

### 口咽癌诊疗要点
{OPC_GUIDELINE}

### 甲状腺癌诊疗要点
{THYROID_GUIDELINE}

### 甲状腺癌诊疗要点汇总(路径速查)
{THYROID_GUIDELINE_SUMMARY}

## 指南遵循要求
1. 肿瘤分期、术式推荐及"是否适合保喉"的判断必须依据上述《手术指征与术式》要点。
2. 若与指南内容冲突，须明确说明理由及依据。

## 引用要求
每个推荐术式必须在"来源"字段注明所依据的指南来源页码；并在"参考"字段列出本次输出的主要指南引用。若无指南依据，参考填 []。"""


class SurgicalPlanAdvisor(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请为以下患者制定手术方案:

{context}

请按照执行步骤进行分析，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        for proc in raw_result.get("推荐术式", []):
            proc.setdefault("来源", "")
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        procs = result.get("推荐术式", [])
        name = procs[0].get("名称", "待定") if procs else "待定"
        return {
            "总结": result.get("总结", f"推荐: {name}"),
            "置信度": result.get("置信度", 0.9),
            "肿瘤分期": result.get("肿瘤分期", {}),
            "推荐术式": procs,
            "替代方案": result.get("替代方案", []),
            "关键注意事项": result.get("关键注意事项", []),
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", []),
            "参考": result.get("参考", []),
        }
