# -*- coding: utf-8 -*-
"""
技能结果缓存
将每次技能执行结果持久化到 results_cache/{patient_id}/ 下,
缓存键包含病历数据哈希 + LLM模式 + (S01的图片输入), 数据更新后自动失效。
"""
import hashlib
import json
import os
import shutil
from typing import Any, Dict, Optional

_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_cache")

_LLM_KEYS = ("api_key", "base_url", "model")


def _extra_hash(extra: Any) -> str:
    if extra is None:
        return ""
    try:
        return hashlib.sha256(repr(extra).encode("utf-8")).hexdigest()[:8]
    except Exception:
        return repr(extra)[:200]


def _data_hash(patient_data: Dict, extra: Any = None, llm_mode: bool = False) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(patient_data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
    h.update(b"|llm=" + str(llm_mode).encode("utf-8"))
    h.update(b"|extra=" + _extra_hash(extra).encode("utf-8"))
    try:
        from utils.llm_client import LLM_CONFIG
        h.update(b"|cfg=" + json.dumps(
            {k: LLM_CONFIG.get(k) for k in ("temperature", "seed", "model", "base_url")},
            sort_keys=True, default=str).encode("utf-8"))
    except Exception:
        pass
    return h.hexdigest()[:16]


def _path(skill_id: str, patient_id: str, patient_data: Dict, extra: Any, llm_mode: bool) -> str:
    return os.path.join(
        _BASE, patient_id, f"{skill_id}_{_data_hash(patient_data, extra, llm_mode)}.json"
    )


def load(skill_id: str, patient_id: str, patient_data: Dict, extra: Any = None, llm_mode: bool = False) -> Optional[Dict]:
    """读取缓存, 命中返回结果dict, 否则None"""
    path = _path(skill_id, patient_id, patient_data, extra, llm_mode)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save(skill_id: str, patient_id: str, patient_data: Dict, result_dict: Dict, extra: Any = None, llm_mode: bool = False) -> str:
    """保存结果, 并清理同技能旧版本缓存(数据已变更自动失效)"""
    pdir = os.path.join(_BASE, patient_id)
    os.makedirs(pdir, exist_ok=True)
    path = _path(skill_id, patient_id, patient_data, extra, llm_mode)
    for f in os.listdir(pdir):
        if f.startswith(f"{skill_id}_") and f != os.path.basename(path):
            try:
                os.remove(os.path.join(pdir, f))
            except OSError:
                pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2, default=str)
    return path


def load_latest(skill_id: str, patient_id: str) -> Optional[Dict]:
    """加载该患者该技能最近一次保存的缓存结果(每次save会清理旧文件, 故每个患者每技能至多一份)。
    用于S01等无法持久化输入(如上传文件)的场景在重新进入页面时回显最近结果。"""
    pdir = os.path.join(_BASE, patient_id)
    if not os.path.isdir(pdir):
        return None
    files = [f for f in os.listdir(pdir) if f.startswith(f"{skill_id}_") and f.endswith(".json")]
    if not files:
        return None
    latest = max(files, key=lambda f: os.path.getmtime(os.path.join(pdir, f)))
    try:
        with open(os.path.join(pdir, latest), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear(patient_id: Optional[str] = None) -> int:
    """清空缓存, 返回删除文件数"""
    target = os.path.join(_BASE, patient_id) if patient_id else _BASE
    if not os.path.isdir(target):
        return 0
    n = 0
    for root, _dirs, files in os.walk(target):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    if patient_id:
        try:
            shutil.rmtree(target)
        except OSError:
            pass
    return n
