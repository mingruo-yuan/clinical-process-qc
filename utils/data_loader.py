# -*- coding: utf-8 -*-
"""
患者数据加载器
数据目录结构:
mock_data/
├── patient_001/
│   ├── patient.json          # 病历数据
│   └── 外院报告/              # 可选: OCR测试图片
│       ├── xxx.jpg
│       └── yyy.pdf
├── patient_002/
└── ...
"""
import os
import json
import re
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mock_data")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".pdf", ".webp")


def _normalize_keys(obj):
    """递归去掉dict key中的空白字符, 兼容DB导出的'诊断 (tbl_xxx)'与代码引用的'诊断(tbl_xxx)'格式差异。值原样保留。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            nk = re.sub(r"\s+", "", k) if isinstance(k, str) else k
            out[nk] = _normalize_keys(v)
        return out
    if isinstance(obj, list):
        return [_normalize_keys(i) for i in obj]
    return obj


def _scan_patient_folders() -> List[str]:
    """扫描 mock_data 下的患者文件夹, 按序号排序返回绝对路径列表"""
    if not os.path.isdir(BASE_DIR):
        return []
    folders = []
    for name in os.listdir(BASE_DIR):
        full = os.path.join(BASE_DIR, name)
        if os.path.isdir(full) and (os.path.exists(os.path.join(full, "patient.json")) or os.path.exists(os.path.join(full, "patient.txt"))):
            folders.append(full)

    def sort_key(path: str):
        m = re.search(r"(\d+)", os.path.basename(path))
        return int(m.group(1)) if m else 9999

    folders.sort(key=sort_key)
    return folders


def list_patients() -> List[Dict[str, Any]]:
    """返回患者列表, 每项含 folder/id/姓名/住院号/图片数量"""
    patients = []
    for folder in _scan_patient_folders():
        data = _read_json(folder)
        info = {}
        if data:
            front = data.get("病案首页", {})
            info = {
                "姓名": front.get("姓名", "未知"),
                "住院号": front.get("住院号", ""),
                "性别": front.get("性别", ""),
                "年龄": front.get("年龄", ""),
            }
        patients.append({
            "folder": folder,
            "id": os.path.basename(folder),
            "json_exists": data is not None,
            "image_count": len(list_images(folder)),
            **info,
        })
    return patients


def _read_json(folder: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(folder, "patient.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _normalize_keys(json.load(f))
    except Exception:
        return None


def load_patient(folder: str) -> Dict[str, Any]:
    """加载单个患者: 返回 {data: 病历dict, images: 图片路径列表, folder, id}"""
    data = _read_json(folder)
    if data is None:
        data = {}
    return {
        "data": data,
        "images": list_images(folder),
        "folder": folder,
        "id": os.path.basename(folder),
    }


def save_external_reports(folder: str, reports: Dict[str, Any]) -> bool:
    """将OCR写回的'外院报告'持久化到患者 patient.json, 保留文件其余内容不变。
    使重启/新会话后外院报告仍保留, 后续技能(鉴别诊断/术前/出院等)始终能读到。"""
    path = os.path.join(folder, "patient.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["外院报告"] = reports
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return True
    except Exception:
        return False


def list_images(folder: str) -> List[str]:
    """返回患者文件夹下所有报告图片的绝对路径"""
    images = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(IMAGE_EXTS):
                images.append(os.path.join(root, f))
    images.sort()
    return images


def load_all_patients() -> List[Dict[str, Any]]:
    """加载全部患者"""
    return [load_patient(f) for f in _scan_patient_folders()]


# ============ 步骤输入裁剪 (模拟患者入院全流程, 每步只喂入该时点已有的病历数据) ============
# 章节名为 _normalize_keys 归一化后的键(去除空白字符)。
# 分组为临床时点归属: core=入院即存在, preop_reports=入院初检查报告,
# lab=检验, postop=手术及术后才产生。
STEP_GROUPS = {
    "core": [
        "诊断(tbl_dia_all_diagnoses)",
        "入院记录",
        "外院报告",
        "住院患者营养风险筛查NRS-2002评估表入院(护理系统)",
        "自理能力评估表",
        "长期医嘱单(tbl_mar_medication_orders_cdt_order_term)",
        "临时医嘱单(tbl_mar_medication_orders_cdt_order_term)",
    ],
    "preop_reports": [
        "电子喉镜报告单(tbl_std_reports)",
        "CT报告单(tbl_std_reports)",
        "电子胃镜报告单(tbl_std_reports)",
        "超声检查报告单(tbl_std_reports)",
        "超声心动图报告单(tbl_std_reports)",
        "心电图报告单(tbl_std_reports)",
        "常规通气功能检查(tbl_std_pat)",
    ],
    "lab": ["化验单"],
    "frontsheet_only": ["病案首页"],
    "postop": [
        "手术记录",
        "麻醉记录单(tbl_sug_infusion_main)",
        "病程记录(tbl_doc_first_medical_record_post_operation)",
        "病理检查报告单(tbl_std_pis_reports)",
        "术后患者护理记录单（术日）(tbl_nur_nursing_notes)",
        "术后患者护理记录单（术后一日）(tbl_nur_nursing_notes)",
        "手术风险评估表",
        "住院患者VTE评分",
        "住院患者营养风险筛查NRS-2002评估表术后(护理系统)",
        "PACU记录单",
    ],
}

# 各流程节点可用章节分组; None = 全量(出院/病案首页时整个入院流程已结束)
STEP_INPUT_SCOPE = {
    "admission": ["core"],
    # S03医嘱遗漏检测专用: 需含病案首页(入院日期)、术前检查报告与化验单, 用于"检查检验时效性"核查
    "admission_order": ["core", "preop_reports", "lab", "frontsheet_only"],
    "first_record": ["core", "preop_reports"],
    "supplement": ["core", "preop_reports", "lab"],
    "preop": ["core", "preop_reports", "lab"],
    "postop": ["core", "preop_reports", "lab", "postop"],
    "discharge": None,
    "frontsheet": None,
}

# 章节内字段级裁剪: 个别章节混有未来时点字段, 手术前步骤只暴露入院时点字段。
# 例: "诊断"章节同时含"入院诊断"与"出院诊断", 入院/首次病程/手术指征评估/术前讨论阶段不得看到出院诊断。
FIELD_MASKS = {
    "诊断(tbl_dia_all_diagnoses)": {
        "steps": ["admission", "first_record", "supplement", "preop"],
        "keep": ["入院诊断"],
    },
    # S03时效性核查仅需入院日期(出院日期为出院后才产生), 用于计算距入院天数
    "病案首页": {
        "steps": ["admission_order"],
        "keep": ["入院日期"],
    },
}


def filter_sections_for_step(patient_data: Dict[str, Any], step_id: Optional[str] = None) -> Dict[str, Any]:
    """按流程步骤裁剪病历数据: 仅返回该步骤时点已有的章节(含章节内字段裁剪)。
    step_id 为 None 或步骤定义为全量时, 返回原数据。"""
    if not step_id:
        return patient_data
    groups = STEP_INPUT_SCOPE.get(step_id)
    if groups is None:
        return patient_data
    allowed = {_norm(k) for g in groups for k in STEP_GROUPS.get(g, ())}
    out = {}
    for k, v in patient_data.items():
        if _norm(k) not in allowed:
            continue
        mask = FIELD_MASKS.get(_norm(k))
        if mask and step_id in mask["steps"] and isinstance(v, dict):
            v = {fk: fv for fk, fv in v.items() if fk in mask["keep"]}
        out[k] = v
    return out


def _norm(key: str) -> str:
    return re.sub(r"\s+", "", key)
