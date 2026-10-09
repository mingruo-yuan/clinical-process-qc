# -*- coding: utf-8 -*-
"""
病历原文标注渲染模块
将技能输出"标注"列表中的原文片段定位到患者病历原文, 生成带高亮的HTML片段,
用于在页面中"病历原文在上 + 高亮问题"。
"""
import html
import re
from typing import Any, Dict, List, Tuple

# 与主应用统一的热度色（高/中/低），高改为砖红浅底
SEVERITY_COLORS = {
    "高": "#F0CEC9",  # 砖红
    "中": "#ffe0b3",  # 橙
    "低": "#fff3b3",  # 黄
}

_SEVERITY_ORDER = {"高": 3, "中": 2, "低": 1}


def _build_pattern(needle: str):
    """构造允许空白/全角半角标点差异的匹配模式。
    兼容: 全角/半角冒号(:：)、顿号/逗号(、，)、句号(。)、中英文逗号, 以及任意空白差异。"""
    out = []
    for ch in needle:
        if ch.isspace():
            out.append(r"\s*")
        elif ch in "：:":
            out.append(r"[：:]")
        elif ch in "，,":
            out.append(r"[，,]?")
        elif ch in "、":
            out.append(r"[、,]?")
        elif ch in "。":
            out.append(r"[。]?")
        elif ch in "；;":
            out.append(r"[；;]?")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out))


def find_section(patient_data: Dict, target: str) -> Tuple[str, Any]:
    """定位标注所指的章节与字段。
    target 形如 "入院记录/现病史"、"诊断/入院诊断"、"病案首页"、"长期医嘱单"。
    返回 (section_key, field_key或None); 定位不到返回 (None, None)。
    """
    if not target:
        return None, None
    parts = [p.strip() for p in target.split("/") if p.strip()]
    section_part = parts[0]
    field_part = parts[1] if len(parts) > 1 else None

    keys = list(patient_data.keys())
    if section_part in patient_data:
        sk = section_part
    else:
        sk = None
        for k in keys:
            if k.startswith(section_part):
                sk = k
                break
        if sk is None:
            for k in keys:
                if section_part in k:
                    sk = k
                    break
    if sk is None:
        return None, None

    sec = patient_data.get(sk)
    if not isinstance(sec, dict):
        return sk, None
    if not field_part:
        return sk, None
    if field_part in sec:
        return sk, field_part
    for k in sec.keys():
        if field_part in k:
            return sk, k
    return sk, None


def field_text(value: Any) -> str:
    """将病历字段值转成可展示文本"""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "；".join(field_text(i) for i in value)
    if isinstance(value, dict):
        return "；".join(f"{k}: {field_text(v)}" for k, v in value.items())
    return ""


def _needle_candidates(needle: str, label: str = None) -> List[str]:
    """生成候选匹配片段: 原文片段可能带"字段名: "前缀(LLM从上下文整行复制), 需去掉前缀后二次匹配"""
    cands = [needle]
    stripped = None
    if label and needle.startswith(label):
        stripped = needle[len(label):]
    else:
        m = re.match(r"^(.{1,14})[\s:：]\s*(.{1,})$", needle, re.S)
        if m and label and m.group(1).strip() == label:
            stripped = m.group(2)
        elif m and not label:
            stripped = m.group(2)
    if stripped is not None:
        stripped = re.sub(r"^[\s:：]+", "", stripped)
        if stripped:
            cands.append(stripped)
    return cands


def highlight_text(text: str, notes: List[Dict], label: str = None) -> Tuple[str, set]:
    """在text中高亮各标注的原文片段。
    返回 (html, 命中的标注在notes中的索引集合)。"""
    spans = []
    matched = set()
    for idx, n in enumerate(notes):
        needle = (n.get("原文片段") or "").strip()
        if not needle:
            continue
        for cand in _needle_candidates(needle, label):
            pat = _build_pattern(cand)
            m = pat.search(text)
            if m:
                spans.append((m.start(), m.end(), idx))
                matched.add(idx)
                break
    if not spans:
        return html.escape(text), matched

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    merged = []
    for s in spans:
        if merged and s[0] < merged[-1][1]:
            prev = merged[-1]
            if _SEVERITY_ORDER.get(s[2] and notes[s[2]].get("严重度", ""), 0) > _SEVERITY_ORDER.get(
                notes[prev[2]].get("严重度", ""), 0
            ):
                merged[-1] = s
            continue
        merged.append(s)

    out = []
    pos = 0
    for start, end, idx in merged:
        if start < pos:
            continue
        out.append(html.escape(text[pos:start]))
        color = SEVERITY_COLORS.get(notes[idx].get("严重度", ""), SEVERITY_COLORS["低"])
        title = html.escape((notes[idx].get("问题") or "").strip())
        out.append(
            f'<span style="background-color:{color};padding:0 2px;border-radius:3px"'
            + (f' title="{title}"' if title else "")
            + ">"
        )
        out.append(html.escape(text[start:end]))
        out.append("</span>")
        pos = end
    out.append(html.escape(text[pos:]))
    return "".join(out), matched


def build_annotation_blocks(patient_data: Dict, annotations: List[Dict]):
    """按章节分组标注, 生成渲染块。
    返回 (blocks, unmatched)
    blocks: [{section, lines: [{label, html, notes}], extras: [未定位到原文的标注]}]
    unmatched: 所属部分无法定位到章节的标注
    """
    if not annotations:
        return [], []
    by_section: Dict[str, List[Tuple[Any, Dict]]] = {}
    unmatched = []
    for n in annotations:
        sec_key, field_key = find_section(patient_data, n.get("所属部分", ""))
        if sec_key is None:
            unmatched.append(n)
            continue
        by_section.setdefault(sec_key, []).append((field_key, n))

    blocks = []
    for sec_key, items in by_section.items():
        sec = patient_data.get(sec_key)
        fields = list(sec.items()) if isinstance(sec, dict) else [("", sec)]
        section_level = [n for f, n in items if f is None]
        field_map: Dict[str, List[Dict]] = {}
        for f, n in items:
            if f is not None:
                field_map.setdefault(f, []).append(n)

        lines = []
        extras = []
        sec_matched = set()
        for field, value in fields:
            text = field_text(value)
            if not text.strip():
                continue
            f_notes = field_map.get(field, [])
            all_notes = list(section_level) + f_notes
            if not all_notes:
                lines.append({"label": field, "html": html.escape(text), "notes": []})
                continue
            h, matched_ids = highlight_text(text, all_notes, label=field)
            for j, n in enumerate(all_notes):
                if j in matched_ids:
                    sec_matched.add(id(n))
            for j, n in enumerate(all_notes):
                if j not in matched_ids and n in f_notes:
                    extras.append(n)
            lines.append({"label": field, "html": h, "notes": all_notes})

        # 章节级标注: 空原文片段或未被任何字段命中 -> 附加说明(去重)
        for n in section_level:
            needle = (n.get("原文片段") or "").strip()
            if not needle or id(n) not in sec_matched:
                extras.append(n)

        # 标注指向的字段不在该章节中(原文缺失等), 直接列为附加说明
        for f, n in items:
            if f is not None and f not in [k for k, _ in fields]:
                extras.append(n)

        # 去重
        seen = set()
        deduped = []
        for n in extras:
            if id(n) not in seen:
                seen.add(id(n))
                deduped.append(n)

        blocks.append({"section": sec_key, "lines": lines, "extras": deduped})
    return blocks, unmatched
