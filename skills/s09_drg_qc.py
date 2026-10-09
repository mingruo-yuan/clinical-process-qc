# -*- coding: utf-8 -*-
"""
S09 - 病案首页DRG质控 (Agent Style)
"""
from typing import Any, Dict, List
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from utils.llm_client import call_llm_json
from utils.guidelines import load_guideline

# 检查条目
FRONTSHEET_RULES = load_guideline("04_病案首页质控词条.md")


SKILL_CONFIG = SkillConfig(
    skill_id="S09",
    skill_name="病案首页及DRG质控",
    description="对比病案首页与病历内容，按病案首页质控词条逐项检查，检测编码和质控问题",

    trigger_rules=[
        "当用户进入'病案首页及DRG质控'流程时自动激活",
        "当病案首页数据存在时触发",
    ],

    capabilities=[
        "检查病案首页字段完整性，不允许有漏填项",
        "出院诊断/病理诊断与出院记录/病理报告一致性核对（含入院记录入院诊断延续性）",
        "药物过敏、血型及RH、护理级别等基础信息核对",
        "科主任/医疗组长/主任（副主任）医师与查房记录一致性核对",
        "手术及操作编码与手术记录一致性核对（术者、切口等级、麻醉方式、麻醉医师）",
        "死亡患者尸检、临床路径、离院方式、质控日期等专项核查",
    ],

    execution_steps=[
        "提取病案首页各字段并检查是否有漏填项",
        "出院诊断与出院记录及入院记录(入院诊断)一致性检查",
        "损伤中毒外部原因核对",
        "病理诊断与病理报告一致性及完整性检查",
        "药物过敏史核对",
        "死亡患者尸检记录检查",
        "血型及RH核对",
        "科主任医疗组长及主任副主任医师与查房记录一致性检查",
        "质控日期检查",
        "手术及操作编码与手术记录一致性核对",
        "临床路径核查",
        "离院方式核查",
    ],

    constraints=[
        "检查必须基于客观数据",
        "结论必须可追溯到具体字段",
        "血型及RH：首页填写'未查'为正常状态（表示尚未检测），不判定为漏填扣分；仅当首页填写了具体血型值但与化验单不一致时才判定为不通过",
        "质控日期必须在出院24小时内，可填出院日期当天或+1天",
        "病历中无临床路径表时，临床路径字段全部为'否'",
        "病历中无自动出院协议时，离院方式全部为'医嘱离院'",
        "护理级别数据未录入时，标注'数据未录入'并提示待补录，不判定为错误",
        "DRG编码库尚未接入，'从DRG库抓取可能名称及编码'仅提示待接入，不判错",
    ],

    required_fields=["病案首页", "手术记录", "病理检查报告单(tbl_std_pis_reports)"],

    optional_fields=[
        "外院报告",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "超声检查报告单(tbl_std_reports)",
        "CT报告单(tbl_std_reports)",
    ],

    output_template={
        "总结": "一句话结论",
        "置信度": 0.85,
        "检查结果": [{"项目": "", "状态": "", "详情": ""}],
        "编码审查": {"诊断编码": "", "手术编码": "", "备注": ""},
        "一致性检查": [{"项目": "", "状态": ""}],
        "标注": [
            {"所属部分": "章节/字段", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}
        ],
        "警告": [],
        "建议": [],
    },
)

SYSTEM_PROMPT = f"""你是一位资深的病案管理和DRG质控专家。

## 任务
{SKILL_CONFIG.description}

## 执行步骤
{chr(10).join(SKILL_CONFIG.execution_steps)}

## 约束规则
{chr(10).join('- ' + c for c in SKILL_CONFIG.constraints)}

## 病案首页质控词条
以下是病案首页质控词条及其判定规则，请严格按词条逐项检查：

{FRONTSHEET_RULES}

## 输出格式
请严格按照以下JSON格式返回：
{{
    "总结": "一句话结论",
    "置信度": 0.85,
    "检查结果": [{{"项目": "质控检查项名称", "状态": "通过/待核查/不通过", "详情": "详细说明"}}],
    "编码审查": {{"诊断编码": "ICD-10编码", "手术编码": "ICD-9-CM-3编码", "备注": "备注"}},
    "一致性检查": [{{"项目": "一致性项目", "状态": "一致/不一致"}}],
    "标注": [
        {{"所属部分": "病案首页/出院诊断", "原文片段": "病历原文片段", "问题": "问题", "严重度": "高/中/低", "建议": "建议"}}
    ],
    "警告": [],
    "建议": []
}}
用中文回答。

## 检查结果项目名要求
"检查结果"中"项目"字段直接写质控检查项名称(如"病案首页信息完整性"、"出院诊断与出院记录及入院诊断一致性"、"病理诊断与病理报告一致性"、"药物过敏史核对"、"血型及RH核对"、"护理级别核对"、"科主任医疗组长一致性"、"质控日期检查"、"手术及操作编码核对"、"临床路径核查"、"离院方式核查"等), 严禁加"Step"、"步骤"等序号前缀, 不要用"Step 1"、"Step2"等英文格式。每个"检查结果"项应对应"执行步骤"中的一个检查项。

## 原文标注要求
若质控问题直接对应病历原文中的具体内容, 请在"标注"字段输出:
- "所属部分": 病历章节/字段, 如 "病案首页/出院诊断"、"病案首页/手术及操作名称"、"手术记录/手术名称"、"病理检查报告单/病理诊断名称" 等。章节用病历章节名即可(可省略表名括号后缀)。
- "原文片段": 必须逐字复制病历原文(不得改写、缩写、增删字或标点), 供前端在原文中高亮。
- "严重度": "高"/"中"/"低"
- "问题": 该处存在的问题。
- "建议": 处理建议。
无需标注时返回 []。"""


class DRGQualityControl(AgentSkill):
    def __init__(self):
        super().__init__()

    def _define_config(self) -> SkillConfig:
        return SKILL_CONFIG

    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        user_prompt = f"""请对以下患者的病案首页进行DRG质控检查:

{context}

请按照执行步骤和病案首页质控词条逐项进行检查，并以JSON格式返回结果。"""

        return call_llm_json(SYSTEM_PROMPT, user_prompt, on_chunk=getattr(self, "_kwargs", {}).get("on_chunk"))

    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        return raw_result

    def _format_output(self, result: Dict) -> Dict:
        checks = result.get("检查结果", [])
        warnings = result.get("警告", [])
        return {
            "总结": result.get("总结", f"DRG质控: {len(checks)}项检查完成，{len(warnings)}项问题"),
            "置信度": result.get("置信度", 0.85),
            "检查结果": checks,
            "编码审查": result.get("编码审查", {}),
            "一致性检查": result.get("一致性检查", []),
            "标注": result.get("标注", []),
            "警告": warnings,
            "建议": result.get("建议", []),
        }
