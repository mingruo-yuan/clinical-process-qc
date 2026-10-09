# -*- coding: utf-8 -*-
"""
S05 - 手术指征与禁忌评估 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

# 指南模板

PREOP_GUIDELINE = load_guideline("01_术前推荐检查.md")
SURGERY_GUIDELINE = load_guideline("02_手术指征与术式.md")
OPC_GUIDELINE = load_guideline("05_口咽癌诊疗要点.md")
THYROID_GUIDELINE = load_guideline("06_甲状腺癌诊疗要点.md")
THYROID_GUIDELINE_SUMMARY = load_guideline("07_甲状腺癌诊疗要点汇总.md")

SKILL_CONFIG = SkillConfig(
    skill_id="S05",
    skill_name="手术指征与禁忌评估",
    description="根据检查检验结果评估手术条件",

    trigger_rules=[
        "当用户进入'手术指征和禁忌'流程时自动激活",
        "当病理结果和检查报告均存在时触发",
    ],

    capabilities=[
        "评估手术适应证是否满足",
        "检查手术禁忌症",
        "列出术前准备清单",
        "评估手术风险等级",
    ],

    execution_steps=[
        "Step 1: 提取诊断、分期、病理结果",
        "Step 2: 提取各项检查结果",
        "Step 3: 逐项评估手术指征",
        "Step 4: 逐项检查手术禁忌症",
        "Step 5: 生成术前准备清单",
        "Step 6: 综合评估手术风险",
    ],

    constraints=[
        "评估必须基于客观检查数据",
        "禁忌症必须有明确的检查依据",
        "高风险手术需标注'建议多学科会诊'",
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
        "是否建议手术": True,
        "指征评估": [{"项目": "", "状态": "", "依据": "", "来源": ""}],
        "禁忌检查": [{"项目": "", "状态": "", "依据": "", "来源": ""}],
        "术前准备清单": [{"项目": "", "状态": ""}],
        "风险评估": [{"风险": "", "等级": "", "描述": ""}],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
        "参考": [{"要点": "遵循的指南条目简述", "来源": "来源页码"}],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的头颈外科手术专家，擅长评估手术指征和禁忌症。

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
    "是否建议手术": true,
    "指征评估": [{{"项目": "评估项目", "状态": "符合/不符合", "依据": "依据", "来源": "来源页码"}}],
    "禁忌检查": [{{"项目": "禁忌项目", "状态": "未见/存在", "依据": "依据", "来源": "来源页码"}}],
    "术前准备清单": [{{"项目": "检查项目", "状态": "已完成/待完成"}}],
    "风险评估": [{{"风险": "风险项", "等级": "高/中/低", "描述": "描述"}}],
    "标注": [
        {{"所属部分": "病理检查报告单/病理分期", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": [],
    "参考": [{{"要点": "遵循的指南条目简述", "来源": "来源页码"}}]
}}
用中文回答。

## 原文标注要求
若评估结论直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "病理检查报告单/病理分期"、"诊断/出院诊断"、"CT报告单"、"入院记录/既往史" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
若问题是"某术前检查缺失"而无对应原文片段, "原文片段"留空, "所属部分"指向应完成该检查的位置。无需标注时返回 []。

## 临床指南参考(专家诊疗要点)
以下要点涵盖喉癌、下咽癌、颈段食管癌、口咽癌及甲状腺癌五个病种，请根据患者诊断仅采用对应病种条目。

### 术前推荐检查(用于生成术前准备清单与禁忌评估依据)
{PREOP_GUIDELINE}

### 手术指征、手术禁忌及推荐术式
{SURGERY_GUIDELINE}

### 口咽癌诊疗要点
{OPC_GUIDELINE}

### 甲状腺癌诊疗要点
{THYROID_GUIDELINE}

### 甲状腺癌诊疗要点汇总(路径速查)
{THYROID_GUIDELINE_SUMMARY}

## 指南遵循要求
1. 手术指征、禁忌症的判断及术前准备清单必须依据上述《诊疗要点》逐项核对。
2. 若与指南内容冲突，须明确说明理由及依据。

## 引用要求
指征评估、禁忌检查的每条判断必须在"来源"字段注明所依据的指南来源页码；并在"参考"字段列出本次输出的主要指南引用。若无指南依据，参考填 []。"""


class SurgicalIndicationAssessor(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请评估以下患者是否具备手术条件:

{context}

请按照执行步骤进行评估，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        for item in raw_result.get("指征评估", []):
            item.setdefault("来源", "")
        for item in raw_result.get("禁忌检查", []):
            item.setdefault("来源", "")
        indicated = raw_result.get("是否建议手术", True)
        if not indicated:
            raw_result.setdefault("警告", []).append("存在手术禁忌，请进一步评估")
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        indicated = result.get("是否建议手术", True)
        return {
            "总结": result.get("总结", "符合手术条件" if indicated else "存在手术禁忌"),
            "置信度": result.get("置信度", 0.9),
            "是否建议手术": indicated,
            "指征评估": result.get("指征评估", []),
            "禁忌检查": result.get("禁忌检查", []),
            "术前准备清单": result.get("术前准备清单", []),
            "风险评估": result.get("风险评估", []),
            "标注": result.get("标注", []),
            "警告": result.get("警告", []),
            "建议": result.get("建议", []),
            "参考": result.get("参考", []),
        }
