# -*- coding: utf-8 -*-
"""
临床指南知识库加载 - 从 clinical_knowledge/ 目录读取阶段切片
供各技能注入到 SYSTEM_PROMPT 作为临床决策依据
"""
import os
from functools import lru_cache

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clinical_knowledge")


@lru_cache(maxsize=None)
def load_guideline(filename: str) -> str:
    path = os.path.join(_KNOWLEDGE_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
