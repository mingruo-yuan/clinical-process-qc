# -*- coding: utf-8 -*-
"""
S04 - 鉴别诊断生成 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

## 鉴别诊断模板

THYROID_GUIDELINE = load_guideline("06_甲状腺癌诊疗要点.md")
OPC_GUIDELINE = load_guideline("05_口咽癌诊疗要点.md")


SKILL_CONFIG = SkillConfig(
    skill_id="S04",
    skill_name="鉴别诊断生成",
    description="根据入院资料生成鉴别诊断及排除理由",

    trigger_rules=[
        "当用户进入'首次病程记录'流程时自动激活",
        "当主诉、现病史、检查结果均存在时触发",
    ],

    capabilities=[
        "列出所有需要鉴别的疾病",
        "为每个诊断提供支持和反对依据",
        "解释为什么选择此诊断而非其他",
        "建议进一步检查",
    ],

    execution_steps=[
        "Step 1: 提取主诉、现病史、体格检查、辅助检查",
        "Step 2: 列出3-5个需要鉴别的诊断(按可能性排序)",
        "Step 3: 对每个鉴别诊断分三个要点输出: ①特点(简短介绍该疾病的临床特点) ②支持点(本患者支持该诊断的病历依据) ③鉴别点(与原发诊断的关键区别)",
        "Step 4: 确认最终诊断(最可能诊断)并给出选择理由",
        "Step 5: 给出进一步检查建议",
    ],

    constraints=[
        "必须基于病历资料，不得编造",
        "鉴别诊断必须输出3-5个，按可能性从高到低排列",
        "每个诊断必须分三个要点: '特点'(简短介绍该疾病临床特点)、'支持点'(该诊断在本患者的支持依据)、'鉴别点'(与原发诊断的关键区别)",
        "要点须基于病历依据，不得空泛描述，避免一大段话",
    ],

    required_fields=[
        "入院记录.主诉",
        "入院记录.现病史",
        "电子喉镜报告单(tbl_std_reports)",
        "CT报告单(tbl_std_reports)",
    ],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
        "超声心动图报告单(tbl_std_reports)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.9,
        "主要诊断": "最可能的诊断",
        "鉴别诊断": [
            {"诊断": "疾病", "可能性": "高/中/低", "特点": "简短介绍该疾病临床特点", "支持点": "本患者支持该诊断的病历依据", "鉴别点": "与原发诊断的关键区别"}
        ],
        "进一步检查": [],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科临床医学专家，擅长鉴别诊断。

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
    "主要诊断": "最可能的诊断(原发诊断)",
    "鉴别诊断": [
        {{"诊断": "疾病", "可能性": "高/中/低", "特点": "简短介绍该疾病的临床特点", "支持点": "该诊断在本患者身上的支持依据", "鉴别点": "与原发诊断(主要诊断)的关键区别"}}
    ],
    "进一步检查": ["建议检查"],
    "标注": [
        {{"所属部分": "入院记录/现病史", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": []
}}
用中文回答。

## 鉴别诊断书写要求
1. "鉴别诊断"必须包含3-5个诊断，按可能性从高到低排列；第一个为最可能的鉴别诊断。
2. 每个诊断必须分三个要点输出（禁止合成一大段话）：
   - "特点": 用1-2句话简短介绍该疾病的典型临床特点（客观描述该病本身，不局限于本患者）。
   - "支持点": 列出本患者支持该诊断的病历依据（结合现病史、体格检查、喉镜/CT等检查，可多条用分号分隔）。
   - "鉴别点": 说明它与"主要诊断"(原发诊断)的关键区别，即为什么不像/为什么需要排除。
3. "主要诊断"即当前考虑的原发诊断，鉴别诊断围绕它展开。

## 原文标注要求
若结论直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "入院记录/现病史"、"入院记录/专科情况"、"CT报告单"、"电子喉镜报告单" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
若问题是"某检查尚未完善"而无对应原文片段, "原文片段"留空, "所属部分"指向应完善检查的位置。无需标注时返回 []。

## 病种提示
本系统覆盖头颈肿瘤五个病种：喉癌、下咽癌、颈段食管癌、口咽癌及甲状腺癌。
- 甲状腺癌鉴别核心：超声提示甲状腺结节/TI-RADS分级、FNA病理、Tg/TgAb、MTC需查Ctn/CEA与RET基因；需与甲状腺良性结节(结节性甲状腺肿/腺瘤)、甲状腺炎(桥本)、淋巴结反应性增生、颈部其他原发转移鉴别。
- 口咽癌需关注p16/HPV状态，与扁桃体/舌根淋巴瘤、咽旁间隙肿瘤鉴别。
- 喉癌/下咽癌需与慢性喉炎、喉角化病/白斑、声带息肉、喉结核、喉乳头状瘤等鉴别。

### 甲状腺癌诊疗要点(用于鉴别依据)
{THYROID_GUIDELINE}

### 口咽癌诊疗要点(用于鉴别依据)
{OPC_GUIDELINE}

## 鉴别依据要求
1. "支持点"与"鉴别点"必须结合上述诊疗要点及病历原文数据(超声/病理/化验/影像), 不得凭印象空写。
2. 甲状腺结节病例必须结合 TI-RADS 分级与 FNA/病理结果给出良性 vs 恶性鉴别。"""


class DifferentialDiagnosisGenerator(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请根据以下患者资料进行鉴别诊断:

{context}

请按照执行步骤进行分析，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        diff_list = result.get("鉴别诊断", [])
        primary = result.get("主要诊断", "")
        return {
            "总结": result.get("总结", f"已生成{len(diff_list)}项鉴别诊断，首先考虑{primary}"),
            "置信度": result.get("置信度", 0.9),
            "主要诊断": primary,
            "鉴别诊断": diff_list,
            "进一步检查": result.get("进一步检查", []),
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", []),
        }
