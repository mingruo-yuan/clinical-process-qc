# -*- coding: utf-8 -*-
from .base import AgentSkill, SkillConfig, SkillResult, SkillStatus
from .s01_ocr import OCRExtractor
from .s02_diagnosis_check import DiagnosisInconsistencyDetector
from .s03_order_check import OrderGapDetector
from .s04_differential import DifferentialDiagnosisGenerator
from .s05_surgical_indication import SurgicalIndicationAssessor
from .s06_surgical_plan import SurgicalPlanAdvisor
from .s07_pathology import PathologyInterpreter
from .s08_discharge import DischargeOrderGenerator
from .s09_drg_qc import DRGQualityControl

__all__ = [
    "AgentSkill", "SkillConfig", "SkillResult", "SkillStatus",
    "OCRExtractor", "DiagnosisInconsistencyDetector", "OrderGapDetector",
    "DifferentialDiagnosisGenerator", "SurgicalIndicationAssessor",
    "SurgicalPlanAdvisor", "PathologyInterpreter", "DischargeOrderGenerator",
    "DRGQualityControl",
]

WORKFLOW_STEPS = [
    {"id": "admission", "name": "入院记录", "skills": ["S01", "S02", "S03"]},
    {"id": "first_record", "name": "首次病程记录", "skills": ["S04"]},
    {"id": "supplement", "name": "手术指征和禁忌", "skills": ["S05"]},
    {"id": "preop", "name": "术前讨论", "skills": ["S06"]},
    {"id": "postop", "name": "术后", "skills": ["S07"]},
    {"id": "discharge", "name": "出院护理服务包及医嘱", "skills": ["S08"]},
    {"id": "frontsheet", "name": "病案首页及DRG质控", "skills": ["S09"]},
]

SKILL_REGISTRY = {
    "S01": OCRExtractor,
    "S02": DiagnosisInconsistencyDetector,
    "S03": OrderGapDetector,
    "S04": DifferentialDiagnosisGenerator,
    "S05": SurgicalIndicationAssessor,
    "S06": SurgicalPlanAdvisor,
    "S07": PathologyInterpreter,
    "S08": DischargeOrderGenerator,
    "S09": DRGQualityControl,
}
