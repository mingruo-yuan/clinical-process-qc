# -*- coding: utf-8 -*-
"""
Streamlit Demo - Workflow-based
"""
import streamlit as st
import sys
import os
import html
import re
import time
import requests as _requests
import json
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skills import SKILL_REGISTRY, WORKFLOW_STEPS, SkillStatus, SkillResult
from utils.data_loader import list_patients, load_patient, filter_sections_for_step, save_external_reports
from utils.annotation_render import build_annotation_blocks
from utils import result_cache, llm_client
from utils.guideline_links import add_guideline_links

# 统一配色与字号：集中定义全局色板，确保全局风格一致且便于调整
PALETTE = {
    # 品牌与结构色（深海蓝专业医疗 B 端风格）
    "brand_main": "#2568C8",      # 主蓝色按钮/重点操作
    "brand_dark": "#143460",      # 深蓝导航栏/侧边栏
    "brand_secondary": "#195296", # 顶部横幅深蓝
    "brand_bar": "#143460",       # 顶栏深蓝底（白字对比清晰）
    "surface": "#FFFFFF",         # 纯白底
    "surface_alt": "#F3F7FB",     # 页面主体浅灰白
    "surface_tint": "#E8F0FE",    # 主色系浅底/分割线（浅蓝）
    "surface_muted": "#F3F7FB",   # 灰白底（弱背景）
    "border_light": "#E2E8F0",    # 细线/边框
    "border_brand": "#B8D4F0",    # 蓝色系边框/分割

    # 文本色
    "text_primary": "#222933",    # 标题深灰
    "text_secondary": "#444A55",  # 普通正文
    "text_muted": "#788292",      # 次要浅灰文字
    "text_caption": "#94a3b8",    # 说明/注释（灰400）

    # 语义色（状态）
    "success": "#16a34a",         # 成功主色
    "success_text": "#14532d",
    "success_bg": "#f0fdf4",
    "success_bd": "#bbf7d0",

    "warning": "#f59e0b",         # 告警主色
    "warning_text": "#92400e",
    "warning_bg": "#fffbeb",
    "warning_bd": "#fcd34d",

    "error": "#B04A3D",           # 错误主色（砖红，不刺眼）
    "error_text": "#7E332A",
    "error_bg": "#FBF1EF",
    "error_bd": "#E9D2CE",

    # 强调/热度提示
    "heat_high": "#F0CEC9",       # 砖红浅底（高）
    "heat_mid": "#ffe0b3",
    "heat_low": "#fff3b3",

    "support": "#16A34A",         # 支持点标签（绿色）
    "diff": "#FFAA22",            # 鉴别点标签（橙色，功能强调色）
}

def C(name: str) -> str:
    """取色板颜色，缺省时返回空字符串避免拼接报错"""
    return PALETTE.get(name, "")

# 出院护理服务包外源知识(独立JSON, 便于后续修改定价/服务内容)
NURSING_PKG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nursing_package", "nursing_package.json")


def load_nursing_package():
    """读取上门护理服务包配置, 不存在或损坏时返回 None"""
    try:
        with open(NURSING_PKG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_patient_index(patients, param):
    """按 URL 参数匹配患者: 支持病案号/文件夹id/住院号/姓名, 未命中返回0"""
    if not patients:
        return 0
    if param:
        for i, p in enumerate(patients):
            if (p.get("病案号") == param or p["id"] == param
                    or p.get("住院号") == param or p.get("姓名") == param):
                return i
    return 0


# ── DRG API ──────────────────────────────────────────────────────────────
DRG_API_BASE = "http://assistant.cares-copilot.com"


def drg_group(zd_list: str, ss_list: str, gender: str = "1", age: int = 57,
              show_messages: bool = True) -> dict:
    """调用 DRG 分组接口, 返回 {statusCode, mdc, adrg, drg, drgName, messages}"""
    try:
        resp = _requests.post(
            f"{DRG_API_BASE}/api/v1/drg/group",
            json={
                "gender": gender,
                "age": age,
                "zdList": zd_list,
                "ssList": ss_list,
                "showMessages": show_messages,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"statusCode": -1, "statusMsg": str(e)}


def drg_calc_fee(drg_code: str, hospital_level: str = "A",
                 medical_insurance_type: str = "employee") -> dict:
    """调用 DRG 费用测算接口, 返回 {weight, fee_base, std_fee, high_fee, low_fee}"""
    try:
        resp = _requests.post(
            f"{DRG_API_BASE}/api/v1/drg/calcfee",
            json={
                "drg": drg_code,
                "hospital_level": hospital_level,
                "medical_insurance_type": medical_insurance_type,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
    if param:
        for i, p in enumerate(patients):
            if (p.get("病案号") == param or p["id"] == param
                    or p.get("住院号") == param or p.get("姓名") == param):
                return i
    return 0


def init_session_state():
    patients = list_patients()
    # 默认展示王文武(patient_003, index=2)
    default_idx = 2 if len(patients) > 2 else 0
    if 'patient_list' not in st.session_state:
        st.session_state.patient_list = patients
    if 'patient_index' not in st.session_state:
        st.session_state.patient_index = default_idx
    if 'patient_folder' not in st.session_state:
        st.session_state.patient_folder = patients[default_idx]["folder"] if patients else None
    if 'patient_data' not in st.session_state:
        if patients:
            st.session_state.patient_data = load_patient(patients[default_idx]["folder"])["data"]
        else:
            st.session_state.patient_data = {}
    if 'patient_images' not in st.session_state:
        if patients:
            st.session_state.patient_images = load_patient(patients[0]["folder"])["images"]
        else:
            st.session_state.patient_images = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
    if 'step_results' not in st.session_state:
        st.session_state.step_results = {}
    if 'force_rerun' not in st.session_state:
        st.session_state.force_rerun = False
    if 'auto_analyze' not in st.session_state:
        st.session_state.auto_analyze = True


def _sync_patient_param():
    """按 URL 参数(patient/patient_id)加载患者: 首载与中途变更统一在此处理, 带标记防止死循环"""
    qid = st.query_params.get("patient") or st.query_params.get("patient_id")
    if not qid:
        st.session_state.pop("patient_param_unmatched", None)
        return
    if st.session_state.get("patient_param") == qid:
        return
    st.session_state.patient_param = qid
    st.session_state.pop("patient_param_unmatched", None)
    if not st.session_state.patient_list:
        return
    matched = any(p["id"] == qid or p.get("住院号") == qid or p.get("姓名") == qid
                  for p in st.session_state.patient_list)
    if not matched:
        st.session_state.patient_param_unmatched = qid
        return
    idx = _resolve_patient_index(st.session_state.patient_list, qid)
    folder = st.session_state.patient_list[idx]["folder"]
    if os.path.basename(folder) == os.path.basename(st.session_state.patient_folder or ""):
        return
    st.session_state.patient_index = idx
    st.session_state.patient_folder = folder
    st.session_state.patient_data = load_patient(folder)["data"]
    st.session_state.patient_images = load_patient(folder)["images"]
    st.session_state.current_step = 0
    st.session_state.step_results = {}
    for k in list(st.session_state.keys()):
        if k.startswith("qilu_streamed_") or k.startswith("np_streamed_"):
            del st.session_state[k]


def _sync_step_param():
    """按 URL 参数(step)切换当前流程步。优先使用步骤id(WORKFLOW_STEPS[i]['id'])。
    未提供或不匹配时保持现状。"""
    sid = st.query_params.get("step")
    if not sid:
        return
    # 已经同步过该参数且未变化则跳过
    if st.session_state.get("_step_param") == sid:
        return
    st.session_state._step_param = sid
    # 匹配 id -> index
    idx = None
    for i, s in enumerate(WORKFLOW_STEPS):
        if s.get("id") == sid:
            idx = i
            break
    if idx is None:
        return
    if st.session_state.get("current_step") != idx:
        st.session_state.current_step = idx
        # 切步时清理分段流式标记，保持进场动画一致
        for k in list(st.session_state.keys()):
            if k.startswith("np_streamed_") or k.startswith("qilu_streamed_"):
                del st.session_state[k]
        st.session_state.pop("_stream_scope", None)


def _render_tabs(nav_id: str, items, active_id: str, param_key: str, active_px=20, inactive_px=18):
    """渲染统一风格标签卡导航：选中态略大+蓝色背景，未选中态正常大小，整体协调不割裂。"""
    cur_params = dict(st.query_params)
    st.markdown(
        '<style>'
        # 容器：紧贴页面内容，底部2px灰线分隔
        f'#tabs_{nav_id}{{display:flex;flex-wrap:nowrap;align-items:stretch;gap:6px;'
        'overflow-x:auto;overflow-y:hidden;white-space:nowrap;scrollbar-width:thin;'
        f'padding:4px 0 0;margin:0 0 4px;border-bottom:2px solid {C("border_light")};}}'
        # 公共：无下划线、无边框、圆角、统一高度
        f'#tabs_{nav_id} a{{text-decoration:none;display:inline-flex;align-items:center;'
        f'padding:10px 18px;border-radius:8px 8px 0 0;border:none;transition:all .15s ease;}}'
        # 未选中：灰色文字、白底、medium粗细
        f'#tabs_{nav_id} a.tab-inactive{{color:{C("text_muted")};font-size:{inactive_px}px;'
        f'font-weight:500;background:transparent;border-bottom:3px solid transparent;}}'
        f'#tabs_{nav_id} a.tab-inactive:hover{{color:{C("text_primary")};background:{C("surface_tint")};}}'
        # 选中：蓝色文字、浅蓝底、略大、加粗、底部蓝色指示线
        f'#tabs_{nav_id} a.tab-active{{color:{C("brand_main")};font-size:{active_px}px;'
        f'font-weight:800;background:{C("surface_tint")};border-bottom:3px solid {C("brand_main")};}}'
        '#tabs_' + nav_id + ' a{flex-shrink:0;}'
        '</style>',
        unsafe_allow_html=True,
    )
    links = []
    for it in items:
        # 支持外链项: 通过 external_url 字段标记，target 为 _blank，不参与激活态
        external_url = it.get("external_url")
        if external_url:
            href = external_url
            active = False
            target = "_blank"
        else:
            params = dict(cur_params)
            params[param_key] = it["id"]
            href = "?" + urlencode(params, doseq=True)
            active = (it["id"] == active_id)
            target = "_self"
        cls = "tab-active" if active else "tab-inactive"
        links.append(
            f'<a class="{cls}" href="' + html.escape(href, quote=True) + f'" target="{target}">' + html.escape(it["label"]) + '</a>'
        )
    st.markdown(f'<div id="tabs_{nav_id}">{"".join(links)}</div>', unsafe_allow_html=True)


def _render_top_tabs():
    items = [{"id": s["id"], "label": f"{i+1}. {s['name']}"} for i, s in enumerate(WORKFLOW_STEPS)]
    # 追加第8个外链标签，样式与前面一致，点击新开页
    items.append({
        "id": "external_special_db",
        "label": "8. 专病库管理",
        "external_url": "http://your-database-platform.com",
    })
    active = WORKFLOW_STEPS[st.session_state.get("current_step", 0)]["id"] if WORKFLOW_STEPS else ""
    # 顶部导航字号24，3px底线，单行可横向滚动
    _render_tabs("main", items, active, param_key="step", active_px=20, inactive_px=17)

def run_skill(skill_id, force=False, context_data=None, _stream_placeholder=None, **kwargs):
    """执行技能。
    context_data: 可选, 按流程步骤裁剪后的病历子集, 仅用于LLM上下文(校验仍用完整数据)
    _stream_placeholder: 可选, st.empty()占位, 提供时LLM结果真流式逐段显示"""
    skill_class = SKILL_REGISTRY.get(skill_id)
    if not skill_class:
        return None
    patient_id = os.path.basename(st.session_state.patient_folder or "") or "unknown"
    force = force or st.session_state.get("force_rerun", False)
    llm_mode = bool(llm_client.LLM_CONFIG.get("api_key"))

    # S01 缓存键需包含图片输入(上传图片内容/自带图片路径)
    extra = None
    if skill_id == "S01":
        imgs = kwargs.get("images", [])
        extra = tuple(
            (i.get("path", "") if isinstance(i, dict) and "path" in i else i.get("name", ""),
             i.get("data", b"").__len__() if isinstance(i, dict) and "data" in i else "")
            for i in imgs
        )
    # S01(OCR) 的输出会写回"外院报告", 若把它计入缓存键会导致自身缓存每次失效, 故对S01剔除该章节
    # S01: 缓存键仅依赖图片(名字+大小), 忽略patient_data/context变化, 只要PDF匹配就命中
    cache_data = st.session_state.patient_data
    if skill_id == "S01":
        cache_data = {}
    elif context_data is not None:
        import hashlib
        scope_marker = ("scope", hashlib.sha256(
            json.dumps(context_data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12])
        extra = (extra, scope_marker) if extra else scope_marker

    if not force:
        cached = result_cache.load(skill_id, patient_id, cache_data, extra, llm_mode)
        if cached is not None:
            result = SkillResult.from_dict(cached)
            result._cached = True
            time.sleep(0.3)  # 缓存命中模拟处理延迟(demo展示)
            return result

    on_chunk = None
    if _stream_placeholder is not None:
        _state = {"buf": "", "last": 0.0}

        def on_chunk(text):
            _state["buf"] += text
            now = time.monotonic()
            if now - _state["last"] >= 0.05:
                _state["last"] = now
                fields = _stream_parse(_state["buf"])
                _stream_placeholder.markdown(
                    _live_preview_html(
                        fields,
                        cursor_text=fields["总结"],
                        streaming=True,
                    ),
                    unsafe_allow_html=True,
                )

    skill = skill_class()
    result = skill.analyze(
        cache_data,
        context_data=context_data,
        on_chunk=on_chunk,
        **kwargs,
    )
    try:
        result_cache.save(skill_id, patient_id, cache_data, result.to_dict(), extra, llm_mode)
    except Exception:
        pass
    result._cached = False
    return result


def _match_value_end(raw: str, p: int, n: int):
    """返回 raw[p:] 处JSON值(字符串/数组/对象/标量)的结束下标, 未闭合返回None"""
    c = raw[p]
    if c == '"':
        p += 1
        while p < n:
            if raw[p] == "\\":
                p += 2
            elif raw[p] == '"':
                return p + 1
            else:
                p += 1
        return None
    if c in "{[":
        depth = 0
        i = p
        while i < n:
            ch = raw[i]
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return None
    m = re.match(r"([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?|true|false|null)", raw[p:])
    return p + len(m.group(0)) if m else None


def _read_string_partial(raw: str, p: int) -> str:
    """读取未闭合字符串值当前的文本(可能不完整), 用于总结打字机"""
    s = raw[p + 1:]
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            if i + 1 < len(s):
                out.append(s[i:i + 2])
                i += 2
            else:
                break
        elif ch == '"':
            break
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _scan_array(raw: str, start: int):
    """raw[start] == '[', 增量扫描数组元素: 每条元素一旦闭合即返回。
    返回 (已完成元素列表, 数组是否整体闭合, 数组结束下标)"""
    items = []
    i = start + 1
    n = len(raw)
    while True:
        while i < n and raw[i] in " \t\n\r":
            i += 1
        if i >= n:
            return items, False, None
        if raw[i] == "]":
            return items, True, i + 1
        end = _match_value_end(raw, i, n)
        if end is None:
            return items, False, None
        q = end
        while q < n and raw[q] in " \t\n\r":
            q += 1
        if q >= n:
            return items, False, None
        if raw[q] not in ",]":
            return items, False, None
        try:
            items.append(json.loads(raw[i:end]))
        except Exception:
            pass
        if raw[q] == "]":
            return items, True, q + 1
        i = q + 1


def _stream_parse(raw: str) -> dict:
    """流式增量解析LLM的JSON原文:
    - 字符串值: 未闭合时返回当前部分文本(总结打字机), 闭合后返回完整值
    - 数组值: 每条元素一旦闭合立即加入结果, 不等整个数组闭合
    让"发现的问题/建议"等在生成过程中逐条出现, 而不是最后一下子蹦出"""
    res = {"总结": "", "警告": [], "建议": [], "置信度": 0.0}
    if not raw:
        return res
    n = len(raw)
    i = 0
    while i < n:
        j = raw.find('"', i)
        if j < 0:
            break
        k = raw.find('"', j + 1)
        if k < 0:
            break
        key = raw[j + 1:k]
        p = k + 1
        while p < n and raw[p] in " \t\n\r":
            p += 1
        if p >= n or raw[p] != ":":
            i = k + 1
            continue
        p += 1
        while p < n and raw[p] in " \t\n\r":
            p += 1
        if p >= n:
            break
        c = raw[p]
        if c == '"':
            end = _match_value_end(raw, p, n)
            if end is None:
                if key == "总结":
                    res["总结"] = _read_string_partial(raw, p)
                break
            q = end
            while q < n and raw[q] in " \t\n\r":
                q += 1
            if q < n and raw[q] not in ",}":
                break
            try:
                res[key] = json.loads(raw[p:end])
            except Exception:
                pass
            i = end
        elif c == "[":
            items, closed, end = _scan_array(raw, p)
            res[key] = items
            if not closed:
                break
            q = end
            while q < n and raw[q] in " \t\n\r":
                q += 1
            if q < n and raw[q] not in ",}":
                break
            i = end
        elif c == "{":
            end = _match_value_end(raw, p, n)
            if end is None:
                break
            q = end
            while q < n and raw[q] in " \t\n\r":
                q += 1
            if q < n and raw[q] not in ",}":
                break
            try:
                res[key] = json.loads(raw[p:end])
            except Exception:
                pass
            i = end
        else:
            m = re.match(r"([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?|true|false|null)", raw[p:])
            if not m:
                break
            q = p + len(m.group(0))
            while q < n and raw[q] in " \t\n\r":
                q += 1
            if q < n and raw[q] not in ",}":
                break
            try:
                res[key] = json.loads(raw[p:q])
            except Exception:
                pass
            i = q
    return res


def _detail_value_html(v):
    """把详情字段的任意值(字符串/列表/对象)渲染为可读HTML, 用于流式预览的"输出内容"卡片"""
    if isinstance(v, str):
        return _esc(v)
    if isinstance(v, (int, float)):
        return _esc(str(v))
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                if "诊断" in item and any(k in item for k in ("特点", "支持点", "鉴别点", "说明")):
                    # S04 鉴别诊断条目: 诊断名+可能性+特点/支持点/鉴别点分行
                    title = _esc(item.get("诊断") or "诊断")
                    if item.get("可能性"):
                        title += f' <span style="color:{C("text_muted")};font-size:16px;">(可能性: {_esc(item["可能性"])})</span>'
                    rows = []
                    for key, label, color in (
                        ("特点", "特点", C("brand_main")),
                        ("支持点", "支持点", C("support")),
                        ("鉴别点", "鉴别点", C("diff")),
                    ):
                        val = item.get(key)
                        if val:
                            rows.append(
                                f'<div style="padding:2px 0;"><span style="color:{color};font-weight:600;">{label}:</span> '
                                f'{_esc(val)}</div>'
                            )
                    if not rows and item.get("说明"):
                        rows.append(f'<div style="padding:2px 0;">{_esc(item["说明"])}</div>')
                    parts.append(
                        f'<div style="border-left:3px solid {C("border_brand")};background:{C("surface_muted")};border-radius:6px;'
                        f'padding:6px 10px;margin:4px 0;"><div style="font-weight:600;color:{C("text_primary")};">{title}</div>'
                        f'{"".join(rows)}</div>'
                    )
                    continue
                if "检查项目" in item:
                    # S03 检查检验时效性条目: 过期黄/外院重做橙/正常绿
                    name = item.get("检查项目") or "未命名检查"
                    overdue = item.get("是否过期") == "是"
                    redo = item.get("是否需重做") == "是"
                    oday = item.get("过期天数") or 0
                    if overdue:
                        badge, bb, fg, bg = f"已过期 {oday} 天", C("warning"), C("warning_text"), C("warning_bg")
                        reason = item.get("需重做原因") or f"已过期{oday}天，应重做"
                    elif redo:
                        # 外院需重做: 也用统一告警色，减少色值数量
                        badge, bb, fg, bg = "需重做", C("warning"), C("warning_text"), C("warning_bg")
                        reason = item.get("需重做原因") or "外院所做，医保目录内可报销，应在本院重做"
                    else:
                        badge, bb, fg, bg = "有效期内", C("success"), C("success_text"), C("success_bg")
                        reason = item.get("建议") or "在有效期内"
                    date = item.get("报告日期") or "时间不详"
                    days = item.get("距入院天数")
                    addon = f" · 距入院 {days} 天" if isinstance(days, (int, float)) else ""
                    inner = (
                        f'<span style="background:{bb};color:#fff;border-radius:10px;padding:0 8px;'
                        f'font-size:16px;margin-right:6px;">{_esc(badge)}</span>'
                        f'<span style="color:{C("text_primary")};font-weight:600;">{_esc(name)}</span>'
                        f'<div style="color:{fg};margin-top:2px;">报告日期: {_esc(date)}{_esc(addon)}</div>'
                        f'<div style="color:{C("text_secondary")};">{_esc(reason)}</div>'
                        + (f'<div style="color:{C("text_muted")};font-size:16px;">建议: {_esc(item.get("建议") or "")}</div>'
                            if item.get("建议") else "")
                    )
                    parts.append(
                        f'<div style="border-left:3px solid {bb};background:{bg};border-radius:6px;'
                        f'padding:6px 10px;margin:4px 0;">{inner}</div>'
                    )
                    continue
                inner = " · ".join(
                    f'<span style="color:{C("text_secondary")};">{_esc(k)}:</span> {_esc(str(x))}'
                    for k, x in item.items() if x not in (None, "")
                )
                parts.append(
                    f'<div style="border-left:3px solid {C("border_brand")};background:{C("surface_muted")};border-radius:6px;'
                    f'padding:6px 10px;margin:4px 0;">{inner}</div>'
                )
            else:
                parts.append(f'<div style="padding:2px 0;">· {_esc(str(item))}</div>')
        return "".join(parts)
    if isinstance(v, dict):
        return "".join(
            f'<div style="padding:2px 0;"><b>{_esc(k)}:</b> {_detail_value_html(x)}</div>'
            for k, x in v.items() if x not in (None, "")
        )
    return _esc(str(v))


def _live_preview_html(fields, cursor_text=None, reveal=None, reveal_detail=None, streaming=False):
    """与最终渲染同款样式的前端流式预览: 状态横幅(总结打字机) + 问题卡片 + 建议 +
    "输出内容"卡片(主要诊断/鉴别诊断/进一步检查/标注等逐条填充) + 置信度, 边生成边出现"""
    warnings = fields.get("警告") or []
    suggestions = fields.get("建议") or []
    if reveal:
        warnings = list(warnings)[:reveal[0]]
        suggestions = list(suggestions)[:reveal[1]]
    summary = cursor_text if cursor_text is not None else (fields.get("总结") or "")
    parts = [
        '<style>.qilucursor{display:inline-block;width:2px;height:1em;background:' + C("text_caption") + ';'
        'vertical-align:-2px;animation:qilub 0.9s step-start infinite}'
        '@keyframes qilub{50%{opacity:0}}</style>',
        _alert_html("summary" if fields.get("警告") else "success", summary, cursor=True),
    ]
    for w in warnings:
        parts.append(render_warning_item(w))
    if suggestions:
        body = "".join(
            f'<div style="padding:4px 0;color:{C("brand_dark")};">· {_esc(s)}</div>' for s in suggestions
        )
        parts.append(_card(_dot(C("brand_main")) + "建议", body, "info"))
    detail_keys = [k for k in fields if k not in ("总结", "警告", "建议", "置信度")]
    if reveal_detail is not None:
        detail_keys = detail_keys[:reveal_detail]
    if detail_keys:
        body = "".join(
            f'<div style="margin:4px 0;"><b style="color:{C("text_primary")};">{_esc(k)}</b>'
            f'<div style="margin-left:10px;">{_detail_value_html(fields[k])}</div></div>'
            for k in detail_keys
        )
        parts.append(_card(_dot("#334155") + "输出内容", body, "default"))
    if streaming:
        parts.append(
            '<div style="color:' + C("text_caption") + ';font-size:0.9rem;margin-top:6px;">生成中'
            '<span class="qiludots"></span></div>'
            '<style>.qiludots::after{content:"";animation:qilud 1.2s step-start infinite}'
            '@keyframes qilud{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}</style>'
        )
    return "".join(parts)


def auto_run_skills(skill_ids, step_id=None):
    """进入流程页时自动执行技能: 开关开启且该技能尚无结果时才运行。
    按流程步骤裁剪输入(模拟入院全流程)。
    无缓存 -> 真流式(SSE)生成; 有缓存 -> 秒出, 由页面分块淡入展示。"""
    if not st.session_state.get("auto_analyze", True):
        return
    context_data = filter_sections_for_step(st.session_state.patient_data, step_id) if step_id else None
    for sid in skill_ids:
        if sid in st.session_state.step_results:
            continue
        ph = st.empty()
        try:
            result = run_skill(sid, context_data=context_data, _stream_placeholder=ph)
            ph.empty()
            st.session_state.step_results[sid] = result
        except Exception:
            ph.empty()


def _esc(v):
    return html.escape(str(v if v is not None else ""), quote=False)


def _load_similar_cases(folder):
    """加载患者相似病例配置，不存在或格式错误返回空dict"""
    if not folder:
        return {}
    path = os.path.join(folder, "similar_cases.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.dialog("相似病例", width="large")
def _show_similar_case_dialog(case_name: str, case_diag: str, img_path: str = None, url: str = "#",
                              finding: str = "", diagnosis: str = ""):
    """弹窗展示相似病例详情及喉镜图片"""
    col_img, col_info = st.columns([3, 2])
    with col_img:
        st.markdown(f"**病例:** {case_name}")
        st.markdown(f"**诊断:** {case_diag}")
        if img_path and os.path.exists(img_path):
            st.image(img_path, width=500)
        else:
            st.info("暂无喉镜图片")
    with col_info:
        if finding:
            st.markdown("**检查所见:**")
            st.markdown(finding)
        if diagnosis:
            st.markdown("**检查诊断:**")
            st.markdown(diagnosis)
    link_url = url if url and url != "#" else "#"
    st.markdown(
        f'<div style="margin-top:12px;">'
        f'<a href="{link_url}" target="_blank" '
        f'style="display:inline-block;background:#2568C8;color:#fff;font-size:16px;font-weight:600;'
        f'padding:6px 20px;border-radius:6px;text-decoration:none;">查看完整病历 →</a></div>',
        unsafe_allow_html=True
    )


def _dot(color: str, size: int = 10) -> str:
    """CSS彩色圆点"""
    return (f'<span style="display:inline-block;width:{size}px;height:{size}px;'
            f'border-radius:50%;background:{color};vertical-align:middle;'
            f'margin:0 6px 2px 0;"></span>')


def _badge(text: str, color: str = "#FFAA22") -> str:
    """CSS色块徽记（橙色为默认强调色）"""
    return (f'<span style="background:{color};color:#fff;border-radius:10px;'
            f'padding:0 10px;font-size:16px;vertical-align:middle;'
            f'margin-right:6px;">{_esc(text)}</span>')


_ALERT_STYLES = {
    # (边框, 背景, 文字, 图标)
    "success": (C("success_bd"), C("success_bg"), C("success_text"), _dot(C("success"))),
    "warning": (C("warning_bd"), C("warning_bg"), C("warning_text"), _dot(C("warning"))),
    "error": (C("error_bd"), C("error_bg"), C("error_text"), _dot(C("error"))),
    "info": (C("border_brand"), C("surface_tint"), C("brand_dark"), _dot(C("brand_main"))),
    "summary": (C("border_brand"), C("surface_tint"), C("brand_dark"), _dot(C("brand_main"))),
}


def _alert_html(kind: str, text: str, cursor: bool = False) -> str:
    """状态横幅: 流式预览与最终渲染共用同一套颜色/图标, 保证前后一致无跳变"""
    bd, bg, fg, icon = _ALERT_STYLES.get(kind, _ALERT_STYLES["info"])
    cur = '<span class="qilucursor"></span>' if cursor else ""
    return (
        f'<div style="border:1px solid {bd};border-left:4px solid {bd};border-radius:10px;background:{bg};'
        f'padding:0.75rem 1rem;margin:0.5rem 0;color:{fg};">'
        f'<span style="margin-right:6px;">{icon}</span>'
        f'<span style="white-space:pre-wrap;">{_esc(text)}</span>{cur}</div>'
    )


def _ref(v):
    """把 [1]、[1,2]、[1、2] 引用标记渲染为上标 <sup>, 用于正文引用指南"""
    s = html.escape(str(v if v is not None else ""), quote=False)
    s = re.sub(r"(\[\d+(?:[,，、]\s*\d+)*\])\1+", r"\1", s)
    return re.sub(r"\[(\d+(?:[,，、]\s*\d+)*)\]", r"<sup>[\1]</sup>", s)


def _split_list_items(text: str):
    """把含编号/换行的文本拆成列表项, 兼容 '1) ' '1、' '1. ' '1. ' '①②③' 及纯换行分隔"""
    t = str(text).strip()
    if not t:
        return []

    def strip_no(seg: str) -> str:
        return re.sub(r"^\s*\d+[\)、.)]\s*", "", seg).strip()

    # 编号项: 编号前必须是行首或空白
    # 顿号"1、"本身就是分隔符; 而 "1)" "1." 需后随空白, 避免误拆 "(5/64)" "6-8周"
    item_pat = re.compile(r"(?:(?<=^)|(?<=\s))(?:\d+、|\d+[.)](?=\s))")
    markers = [m.start() for m in item_pat.finditer(t)]
    if len(markers) > 1:
        items = []
        for i, pos in enumerate(markers):
            end = markers[i + 1] if i + 1 < len(markers) else len(t)
            items.append(strip_no(t[pos:end]))
        return items
    # 全角编号 ①②③
    circled = [re.sub(r"^\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", p).strip()
               for p in re.split(r"(?=[①②③④⑤⑥⑦⑧⑨⑩])", t) if p.strip()]
    if len(circled) > 1:
        return circled
    # 换行分隔
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    if len(lines) > 1:
        return lines
    return [t]


def _as_list(v):
    """把字段规范成列表: 已是list直接用, 字符串按编号拆分, 其余转单个元素"""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        items = _split_list_items(v)
        return items if items else [v]
    return [v]


def _card(title: str, body: str, tone: str = "default"):
    """带阴影的方框卡片"""
    tones = {
        "warn": (C("error_bg"), C("error")),
        "info": (C("surface_tint"), C("brand_main")),
        "ref": (C("surface_muted"), C("text_muted")),
        "ok": (C("success_bg"), C("success")),
        "default": (C("surface"), C("text_primary")),
    }
    bg, fg = tones.get(tone, tones["default"])
    return (
        f'<div style="border:1px solid {C("border_light")};border-radius:10px;'
        f'box-shadow:0 2px 10px rgba(20,52,96,0.06);background:{bg};'
        f'padding:16px 20px;margin:12px 0;">'
        f'<div style="font-weight:600;color:{fg};margin-bottom:8px;font-size:18px;">{title}</div>'
        f'{body}</div>'
    )


def _page_header(text: str):
    """页面级标题: 与导航栏统一风格，蓝色粗体 + 底部分割线"""
    st.markdown(
        f'<div style="font-size:22px;font-weight:800;color:{C("text_primary")};'
        f'padding:10px 0 8px;border-bottom:3px solid {C("brand_main")};'
        f'margin:8px 0 18px;">{_esc(text)}</div>',
        unsafe_allow_html=True,
    )


def _section_title(text: str):
    """小节标题: 21px semibold + 底部分割线"""
    st.markdown(
        f'<div style="font-size:21px;font-weight:600;color:{C("text_primary")};'
        f'padding:6px 0 6px;border-bottom:2px solid {C("border_light")};'
        f'margin:18px 0 12px;">{_esc(text)}</div>',
        unsafe_allow_html=True,
    )


_PART_CSS = """
<style>
div.st-key-part_nursing_pkg {
    border: 2px solid #B8D4F0 !important;
    border-radius: 12px;
    background: #F3F7FB;
    padding: 8px 16px 14px;
    margin: 2px 0 6px;
}
div.st-key-part_discharge_orders {
    border: 2px solid #B8D4F0 !important;
    border-radius: 12px;
    background: #F3F7FB;
    padding: 8px 16px 14px;
    margin: 2px 0 6px;
}
</style>
"""

_NP_STREAM_CSS = """
<style>
@keyframes npFadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
div.st-key-np_stream_0{animation:npFadeUp .45s ease-out both;animation-delay:.05s}
div.st-key-np_stream_1{animation:npFadeUp .45s ease-out both;animation-delay:.2s}
div.st-key-np_stream_2{animation:npFadeUp .45s ease-out both;animation-delay:.36s}
div.st-key-np_stream_3{animation:npFadeUp .45s ease-out both;animation-delay:.52s}
div.st-key-np_stream_4{animation:npFadeUp .45s ease-out both;animation-delay:.68s}
</style>
"""


def _stream_step_id() -> str:
    """当前流程步的 id, 作为该步流式作用域的基础"""
    return WORKFLOW_STEPS[st.session_state.get("current_step", 0)]["id"]


def _stream_scope() -> str:
    """当前流式展示作用域: 入院页按分段区分, 其余按流程步"""
    return st.session_state.get("_stream_scope") or _stream_step_id()


def _set_stream_scope(scope: str):
    """入院页各分段设置独立作用域, 保证切换分段时重新淡入"""
    st.session_state["_stream_scope"] = scope


def _stream_key(i: int) -> str:
    """当前作用域的流式容器 key: 作用域不同则容器重建, 从而重播淡入动画"""
    return f"qilu_stream_{_stream_scope()}_{i}"


def _stream_css(scope: str, n=12):
    """生成 qilu_stream_{scope}_0..n-1 的错峰淡入规则(进页首屏播一次, 由 main 在切步时清除标记重播)"""
    rules = "".join(
        f'div.st-key-qilu_stream_{scope}_{i}{{animation:qiluFadeUp .45s ease-out both;animation-delay:{0.06 + 0.14 * i:.2f}s}}'
        for i in range(n)
    )
    return (
        "<style>"
        "@keyframes qiluFadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}"
        f"{rules}"
        "</style>"
    )


def _ensure_stream_css(n=12):
    """每次渲染都发出当前作用域的流式CSS。动画只在块元素(重新)挂载时播放,
    重入分段/切步时块重建->自然重播, 同分段内重跑块未重建->不重复, 因此效果稳定一致"""
    st.markdown(_stream_css(_stream_scope(), n), unsafe_allow_html=True)


def _part_header(title: str, subtitle: str, color: str, tag: str) -> str:
    """跨区块标题: 左侧竖线 + 黑色加粗标题"""
    return (
        f'<div style="display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 10px;'
        f'border-left:4px solid {color};padding:4px 0 4px 12px;margin:20px 0 12px;">'
        f'<span style="font-size:20px;font-weight:700;color:{C("text_primary")};">{_esc(title)}</span>'
        f'<span style="font-size:16px;color:{C("text_muted")};">{_esc(subtitle)}</span>'
        f'</div>'
    )


def _sev_color(sev: str) -> str:
    # 高: 错误红；中/低: 统一用告警主色/琥珀色
    return {"高": C("error"), "中": C("warning"), "低": "#ca8a04"}.get(sev, "#ca8a04")


def render_warning_item(w):
    """渲染单条"发现的问题": 字符串或结构化字典(如S03遗漏医嘱/检查检验时效性)"""
    def _timeliness_badge(oday):
        oday = oday or 0
        if oday > 0:
            return f"已过期 {oday} 天", "#f59e0b"
        return "需重做", "#f59e0b"
    if isinstance(w, dict):
        if w.get("type") == "检查检验时效性":
            # S03 检查检验时效性: 已过期应重做(黄)
            name = w.get("项目") or w.get("检查项目") or "未命名检查"
            redo_reason = w.get("原因") or w.get("需重做原因") or w.get("建议") or ""
            date = w.get("报告日期")
            addon = ""
            if isinstance(w.get("距入院天数"), (int, float)):
                addon = f'<div style="margin-top:2px;color:#788292;font-size:16px;">报告日期: {_esc(date or "时间不详")} · 距入院 {_esc(str(w["距入院天数"]))} 天</div>'
            badge, badge_bg = _timeliness_badge(w.get("过期天数") or 0)
            return (
                f'<div style="border-left:4px solid {badge_bg};border-radius:6px;background:#fff;'
                f'padding:8px 12px;margin:6px 0;box-shadow:0 1px 3px rgba(20,52,96,0.05);">'
                f'<div style="font-weight:600;color:#222933;">'
                f'<span style="background:{badge_bg};color:#fff;border-radius:10px;padding:0 8px;'
                f'font-size:16px;margin-right:6px;">{_esc(badge)}</span>'
                f'{_esc(name)}</div>{addon}'
                f'<div style="color:#444A55;">{add_guideline_links(redo_reason)}</div></div>'
            )
        if w.get("type") == "遗漏医嘱":
            sev = w.get("优先级") or "中"
            c = _sev_color(sev)
            lines = []
            if w.get("类别"):
                lines.append(f'<div style="margin-top:2px;color:#444A55;"><b>类别:</b> {_esc(w["类别"])}</div>')
            if w.get("原因"):
                lines.append(f'<div style="color:#444A55;"><b>原因:</b> {add_guideline_links(w["原因"])}</div>')
            if w.get("依据"):
                lines.append(f'<div style="color:#444A55;"><b>依据:</b> {add_guideline_links(w["依据"])}</div>')
            badge = f'<span style="background:{c};color:#fff;border-radius:10px;padding:0 8px;font-size:16px;margin-right:6px;">{_esc(sev)}优先级</span>'
            if w.get("_merged_timeliness") or w.get("是否过期") == "是":
                oday = w.get("过期天数") or 0
                if oday > 0:
                    badge += f'<span style="background:#f59e0b;color:#fff;border-radius:10px;padding:0 8px;font-size:16px;margin-right:6px;">已过期 {oday} 天</span>'
                else:
                    badge += f'<span style="background:#f59e0b;color:#fff;border-radius:10px;padding:0 8px;font-size:16px;margin-right:6px;">需重做</span>'
                if w.get("报告日期"):
                    lines.append(f'<div style="margin-top:2px;color:#788292;font-size:16px;">报告日期: {_esc(w["报告日期"])} · 距入院 {_esc(str(w.get("距入院天数", 0)))} 天</div>')
            return (
                f'<div style="border-left:4px solid {c};border-radius:6px;background:#fff;'
                f'padding:8px 12px;margin:6px 0;box-shadow:0 1px 3px rgba(20,52,96,0.05);">'
                f'<div style="font-weight:600;color:#222933;">'
                f'{badge}'
                f'{_esc(w.get("项目") or "")}</div>{ "".join(lines) }</div>'
            )
        title = w.get("问题") or w.get("项目") or "问题"
        sev = w.get("严重度") or w.get("优先级") or "中"
        c = _sev_color(sev)
        return (
            f'<div style="border-left:4px solid {c};border-radius:6px;background:#fff;'
            f'padding:8px 12px;margin:6px 0;box-shadow:0 1px 3px rgba(20,52,96,0.05);">'
            f'<span style="color:{c};font-weight:600;">[{_esc(sev)}]</span> {_esc(title)}'
            f'{"<br><span style=color:#788292;font-size:16px;>建议: " + _esc(w.get("建议") or "") + "</span>" if w.get("建议") else ""}'
            f'</div>'
        )
    return (
        f'<div style="border-left:4px solid {C("warning")};border-radius:6px;background:#fff;'
        f'padding:8px 12px;margin:6px 0;box-shadow:0 1px 3px rgba(20,52,96,0.05);">'
        f'{_esc(w)}</div>'
    )


def render_result(result):
    """渲染技能结果: 状态横幅 + 各模块卡片(发现的问题/建议/参考依据), 各模块错峰淡入"""
    if not result:
        return
    _ensure_stream_css()
    if result.status == SkillStatus.SUCCESS or result.status == SkillStatus.PARTIAL:
        with st.container(key=_stream_key(0)):
            st.markdown(
                _alert_html("summary" if result.警告 else "success", result.总结),
                unsafe_allow_html=True,
            )
    elif result.status == SkillStatus.NOT_TRIGGERED:
        st.markdown(_alert_html("info", result.总结), unsafe_allow_html=True)
        return
    elif result.status == SkillStatus.NEED_MORE_DATA:
        st.markdown(_alert_html("warning", result.总结), unsafe_allow_html=True)
        return
    else:
        # FAILED: 真正执行失败才用红色
        st.markdown(_alert_html("error", result.总结), unsafe_allow_html=True)
        return

    if result.警告:
        body = "".join(render_warning_item(w) for w in result.警告)
        with st.container(key=_stream_key(1)):
            st.markdown(_card(_dot(C("error")) + "发现的问题", body, "warn"), unsafe_allow_html=True)

    if result.建议:
        body = "".join(
            f'<div style="padding:4px 0;color:{C("brand_dark")};">· {_esc(s)}</div>' for s in result.建议
        )
        with st.container(key=_stream_key(2)):
            st.markdown(_card(_dot(C("brand_main")) + "建议", body, "info"), unsafe_allow_html=True)

    if result.参考 and not (result.详情 or {}).get("遗漏医嘱"):
        # S07 治疗建议内含"依据"列表并在治疗建议下方统一展示, 顶部不再重复渲染参考依据
        tx = (result.详情 or {}).get("治疗建议", {})
        if not (getattr(result, "skill_id", "") == "S07" and tx.get("依据")):
            body = "".join(
                f'<div style="padding:4px 0;color:#444A55;">· {_esc(c.get("要点", c) if isinstance(c, dict) else c)}'
                f'{" <span style=color:#94a3b8;>(来源: " + add_guideline_links(c.get("来源")) + ")</span>" if isinstance(c, dict) and c.get("来源") else ""}</div>'
                for c in result.参考
            )
            with st.container(key=_stream_key(3)):
                st.markdown(_card(_dot(C("text_muted")) + "参考依据(指南)", body, "ref"), unsafe_allow_html=True)


def render_result_details(result):
    """渲染完整输出 - 已停用(不在主页展示)"""
    pass


def render_tail(result):
    """页面尾部: 病历原文标注"""
    render_annotations(result)


def _np_select_row(item):
    """专属/通用护理服务单选行: checkbox + 名称价格 + 描述"""
    key = f"npi_{item.get('id', '')}"
    price_txt = f"¥{item.get('价格', 0)}/次" if not item.get("起价") else f"¥{item.get('价格', 0)}起/次"
    c1, c2 = st.columns([0.46, 0.54], vertical_alignment="center")
    with c1:
        st.checkbox(
            f"**{_esc(item.get('名称', ''))}**　{price_txt}",
            key=key,
            help=item.get("说明", ""),
        )
    with c2:
        st.markdown(
            f'<div style="color:#788292;font-size:16px;padding:2px 0;">{_esc(item.get("描述", ""))}</div>',
            unsafe_allow_html=True,
        )


def _np_selected_ids():
    """当前勾选的服务项 id 集合"""
    return {k[4:] for k, v in st.session_state.items() if k.startswith("npi_") and v}


def _np_selected_items(common_items, disease, visit_price=None, visit_surcharge=0):
    """根据勾选返回 (明细列表, 单项合计, 匹配套餐, 调整后打包价)。
    visit_price: 护士上门按区域核算的价格覆盖; visit_surcharge: 上门区域相对市区的差价"""
    price_map = {it["id"]: it["价格"] for it in common_items}
    name_map = {it["id"]: it["名称"] for it in common_items}
    if visit_price is not None:
        price_map["common_visit"] = visit_price
    for it in disease["专属服务"]:
        price_map[it["id"]] = it["价格"]
        name_map[it["id"]] = it["名称"]
    sel_ids = _np_selected_ids()
    parts = [(name_map.get(i, i), price_map[i]) for i in sel_ids if i in price_map]
    total = sum(p for _, p in parts)
    plan = next((p for p in disease["服务包"] if set(p["包含"]) == sel_ids), None)
    plan_price = None
    if plan is not None:
        plan_price = _np_plan_price(plan, visit_surcharge)
    return parts, total, plan, plan_price


def _np_plan_price(plan, visit_surcharge=0):
    """套餐展示价: 含护士上门的套餐按所选区域附加上门差价(市郊/县域较市区+100)"""
    return plan.get("价格", 0) + (visit_surcharge if "common_visit" in plan.get("包含", []) else 0)


def _np_plan_button_label(plan, selected=False, recommended=False, price=None):
    """固定服务包卡片式按钮文案: 选中态带勾选标记, 推荐包带推荐徽记"""
    head_parts = []
    if selected:
        head_parts.append("✓")
    if recommended:
        head_parts.append("推荐")
    head_parts.append(f"**{_esc(plan.get('包名', ''))}**　¥{price if price is not None else plan.get('价格', 0)}/{plan.get('单位', '次')}")
    head = "　".join(head_parts)
    body = _esc(plan.get("内容", ""))
    return f"{head}\n\n{body}" if body else head


def _collect_texts(obj, out):
    """递归收集病历文本, 用于病种匹配"""
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_texts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_texts(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def _collect_diagnosis_texts(obj, out):
    """仅收集 key 含'诊断'的字段文本, 避免超声/化验等无关上下文(如'甲状腺超声')干扰病种判定"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "诊断" in str(k):
                _collect_texts(v, out)
            else:
                _collect_diagnosis_texts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_diagnosis_texts(v, out)


def match_nursing_disease(patient_data):
    """按诊断字段匹配病种服务包条目(全文仅兜底), 未匹配返回 None"""
    if not patient_data:
        return None
    pkg = load_nursing_package()
    if not pkg:
        return None

    def _first(blob):
        for dp in pkg.get("病种服务包", []):
            for kw in dp.get("匹配关键词", []):
                if kw and kw in blob:
                    return dp
        return None

    diag = []
    _collect_diagnosis_texts(patient_data, diag)
    hit = _first(" ".join(diag))
    if hit:
        return hit
    all_t = []
    _collect_texts(patient_data, all_t)
    return _first(" ".join(all_t))


def _np_disease_overview(dp):
    """病种一览小卡片(未匹配病种时展示)"""
    plans = dp.get("服务包", [])
    price = f'（¥{plans[0]["价格"]}/次 起）' if plans else ""
    packs = " · ".join(p.get("包名", "") for p in plans) if plans else "-"
    return (
        f'<div style="border:1px solid #e2e8f0;border-radius:10px;background:#fafafc;'
        f'padding:10px 14px;margin-bottom:8px;">'
        f'<div style="font-weight:700;color:#222933;">{_esc(dp.get("病种", ""))}{price}</div>'
        f'<div style="color:#788292;font-size:16px;margin-top:3px;">{_esc(dp.get("简介", ""))}</div>'
        f'<div style="color:{C("brand_main")};font-size:16px;margin-top:4px;">固定服务包: {_esc(packs)}</div>'
        f'</div>'
    )


def render_nursing_package(pkg, patient_data=None):
    """出院护理服务包展示(先于出院医嘱): 简介 -> 按病种专属服务包/一览 -> 通用服务 -> 费用结算 -> 价值人群 -> 免责。
    各区块错峰淡入模拟流式输出, 仅流程步首屏播放, 交互时不重复动画"""
    if not pkg:
        return
    st.markdown(_NP_STREAM_CSS, unsafe_allow_html=True)

    dlist = pkg.get("病种服务包", [])
    disease = match_nursing_disease(patient_data) if patient_data else None
    common = pkg.get("通用服务内容", [])
    fees = pkg.get("费用标准", {})

    with st.container(key="np_stream_0"):
        if pkg.get("简介"):
            st.markdown(
                f'<div style="color:#788292;font-size:16px;line-height:1.7;margin:4px 0 10px;">'
                f'{_esc(pkg.get("简介", ""))}</div>',
                unsafe_allow_html=True,
            )

    with st.container(key="np_stream_1"):
        if disease:
            # 套餐联动应用块: 必须在任何 checkbox 实例化之前执行, 否则修改 widget 状态会报错
            plans0 = disease.get("服务包", [])
            if plans0:
                sel_key = f"np_plan_select_{disease.get('病种', '')}"
                applied_key = f"np_plan_applied_{disease.get('病种', '')}"
                default0 = "标准包" if any(p.get('包名') == '标准包' for p in plans0) else plans0[-1].get('包名', '')
                st.session_state.setdefault(sel_key, default0)
                cur0 = st.session_state[sel_key]
                if st.session_state.get(applied_key) != cur0:
                    plan0 = next((p for p in plans0 if p.get('包名') == cur0), plans0[0])
                    for k in list(st.session_state.keys()):
                        if k.startswith("npi_"):
                            st.session_state[k] = False
                    for iid in plan0.get("包含", []):
                        st.session_state[f"npi_{iid}"] = True
                    st.session_state[applied_key] = cur0

            _section_title(f"{_esc(disease.get('病种', ''))} · 专属护理服务")
            st.markdown(
                f'<div style="border-left:4px solid {C("brand_main")};border-radius:8px;background:{C("surface_tint")};'
                f'padding:10px 14px;margin:2px 0 12px;color:{C("brand_dark")};font-size:16px;">'
                f'{_esc(disease.get("简介", ""))}　勾选下方项目可单独选购</div>',
                unsafe_allow_html=True,
            )
            for it in disease.get("专属服务", []):
                _np_select_row(it)
        elif dlist:
            _section_title("各病种服务包一览")
            st.markdown("".join(_np_disease_overview(dp) for dp in dlist), unsafe_allow_html=True)

    visit_rows = [r for r in fees.get("派护士上门收费", []) if r.get("价格", 0) > 0]
    visit_opts = [f"{r['区域']} · ¥{r['价格']}/次" for r in visit_rows]
    visit_price_map = dict(zip(visit_opts, [r["价格"] for r in visit_rows]))
    visit_base = next((r["价格"] for r in visit_rows if r.get("区域") == "济南市区"), 200)
    visit_sel = st.session_state.get("np_area_common_visit")
    visit_price = visit_price_map.get(visit_sel)
    visit_surcharge = (visit_price - visit_base) if visit_price else 0
    visit_region = (visit_sel or "济南市区").split(" · ")[0]

    with st.container(key="np_stream_2"):
        if common:
            _section_title("通用服务内容")
            st.markdown(
                f'<div style="color:#94a3b8;font-size:16px;margin:0 0 8px;">以下项目各病种通用，可按需勾选</div>',
                unsafe_allow_html=True,
            )
            for it in common:
                _np_select_row(it)
                if it.get("起价") and st.session_state.get(f"npi_{it.get('id', '')}") and visit_opts:
                    st.selectbox("上门服务区域", visit_opts, key=f"np_area_{it.get('id', '')}")

    with st.container(key="np_stream_3"):
        if disease:
            plans = disease.get("服务包", [])
            if plans:
                _section_title("固定服务包")
                st.markdown(
                    f'<div style="color:#94a3b8;font-size:16px;margin:0 0 8px;">点击套餐卡片即自动勾选所含服务并享打包价，也可在上方继续增减</div>',
                    unsafe_allow_html=True,
                )
                sel_key = f"np_plan_select_{disease.get('病种', '')}"
                applied_key = f"np_plan_applied_{disease.get('病种', '')}"
                cur = st.session_state.get(sel_key, "标准包" if any(p.get('包名') == '标准包' for p in plans) else plans[-1].get('包名', ''))
                st.markdown(
                    '<style>'
                    'div.st-key-nursing_pkg_plans div.stButton > button{height:auto;min-height:110px;'
                    'white-space:normal;text-align:left;border-radius:10px;padding:14px 16px;'
                    'line-height:1.6;box-shadow:0 2px 8px rgba(20,52,96,0.06);}'
                    'div.st-key-nursing_pkg_plans div.stButton > button[kind="secondary"]'
                    '{border:1px solid #B8D4F0;background:#ffffff;color:' + C("text_primary") + ';}'
                    'div.st-key-nursing_pkg_plans div.stButton > button[kind="primary"]'
                    '{border:2px solid ' + C("brand_main") + ';background:#E8F0FE;color:' + C("text_primary") + ';}'
                    '</style>',
                    unsafe_allow_html=True,
                )
                with st.container(key="nursing_pkg_plans"):
                    cols = st.columns(len(plans))
                    for i, (c, p) in enumerate(zip(cols, plans)):
                        with c:
                            lab = f"{p.get('包名', '')} · ¥{_np_plan_price(p, visit_surcharge)}/{p.get('单位', '次')}"
                            sel = (p.get('包名') == cur)
                            if st.button(
                                _np_plan_button_label(p, sel, recommended=(p.get('包名') == '标准包'), price=_np_plan_price(p, visit_surcharge)),
                                key=f"np_pick_{disease.get('病种', '')}_{p.get('包名', '')}",
                                use_container_width=True,
                                type="primary" if sel else "secondary",
                            ):
                                st.session_state[sel_key] = p.get('包名')
                                st.session_state.pop(applied_key, None)
                                st.rerun()

            _section_title("已选服务与费用")
            parts, total, plan, plan_price = _np_selected_items(common, disease, visit_price=visit_price, visit_surcharge=visit_surcharge)
            if parts:
                rows = "".join(
                    f'<div style="display:flex;justify-content:space-between;padding:3px 0;"><span>{_esc(n)}</span><span>¥{p}</span></div>'
                    for n, p in parts
                )
                st.markdown(_card("费用明细", f'<div style="margin:0 -16px 0 -16px;">{rows}</div>', "default"), unsafe_allow_html=True)
                if plan:
                    p_total = plan_price if plan_price is not None else plan["价格"]
                    save = total - p_total
                    note = f"（{_esc(visit_region)}上门附加 ¥{visit_surcharge}）" if visit_surcharge else ""
                    st.markdown(
                        f'<div style="border:2px solid {C("brand_secondary")};border-radius:10px;background:{C("surface_tint")};'
                        f'padding:12px 16px;margin:6px 0;color:{C("brand_dark")};font-size:16px;">'
                        f'已选内容与「{_esc(plan["包名"])}」完全匹配，按打包价 <b>¥{p_total}</b> 结算{note}'
                        f'（单项合计 ¥{total}，立省 <b>¥{save}</b>）</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="font-size:16px;color:#222933;padding:4px 0;">单项合计 '
                        f'<span style="font-size:24px;font-weight:700;color:{C("brand_main")};">¥{total}</span>'
                        f'<span style="color:#94a3b8;font-size:16px;">（勾选与固定服务包完全一致可享打包价）</span></div>',
                        unsafe_allow_html=True,
                    )
                ckey = f"np_confirm_{disease.get('病种', '')}"
                if st.button("确认并预约", key=f"np_confirm_btn_{disease.get('病种', '')}"):
                    st.session_state[ckey] = (plan["包名"] if plan else "自定义组合", plan_price if plan and plan_price is not None else (plan["价格"] if plan else total))
                if fees.get("服务包定价说明"):
                    st.markdown(
                        f'<div style="color:#94a3b8;font-size:16px;line-height:1.7;margin-top:6px;">'
                        f'{_esc(" · ".join(fees["服务包定价说明"]))}</div>',
                        unsafe_allow_html=True,
                    )
                if st.session_state.get(ckey):
                    pname, pprice = st.session_state[ckey]
                    st.success(f"已生成费用单并提交预约（{pname}，¥{pprice}），护理团队将在24小时内与您联系确认。")
            else:
                st.info("请在上方勾选所需护理服务，或直接选择固定服务包。")

    with st.container(key="np_stream_4"):
        if pkg.get("免责声明"):
            st.markdown(
                f'<div style="color:#94a3b8;font-size:16px;margin-top:8px;line-height:1.6;">{_esc(pkg["免责声明"])}</div>',
                unsafe_allow_html=True,
            )


def render_annotations(result):
    """病历原文高亮标注: 定位到患者病历原文, 高亮问题片段, 下方附问题说明"""
    if not result or not result.详情:
        return
    annotations = result.详情.get("标注") or []
    if not annotations:
        return
    blocks, unmatched = build_annotation_blocks(st.session_state.patient_data, annotations)

    with st.container(key=_stream_key(5)):
        _section_title("病历原文标注")
        st.markdown(
            '<div style="color:#788292;font-size:16px;margin:0 0 10px 2px;">高亮颜色: '
            f'<span style="background:{C("heat_high")};">红=高</span> · <span style="background:#ffe0b3;">橙=中</span> · '
            '<span style="background:#fff3b3;">黄=低</span>, 悬停可查看问题</div>',
            unsafe_allow_html=True,
        )

        for block in blocks:
            parts = []
            for line in block["lines"]:
                if line["label"]:
                    parts.append(f'<div style="margin:2px 0;"><b>{_esc(line["label"])}:</b> {line["html"]}</div>')
                else:
                    parts.append(f'<div style="margin:2px 0;">{line["html"]}</div>')
            for note in block["extras"]:
                sev = note.get("严重度", "低")
                parts.append(
                    f'<div style="color:#788292;font-size:16px;margin:2px 0;">'
                    f'<span style="color:{_sev_color(sev)};">[{sev}级]</span> {_esc(note.get("问题", ""))}'
                    f'{" —— 建议: " + _esc(note.get("建议", "")) if note.get("建议") else ""}</div>'
                )
            st.markdown(
                _card(_dot(C("brand_main")) + _esc(block['section']), "".join(parts), "default"),
                unsafe_allow_html=True,
            )

        if unmatched:
            parts = []
            for note in unmatched:
                sev = note.get("严重度", "低")
                parts.append(
                    f'<div style="color:#788292;font-size:16px;margin:2px 0;">'
                    f'<span style="color:{_sev_color(sev)};">[{sev}级]</span> '
                    f'[{_esc(note.get("所属部分", ""))}] {_esc(note.get("问题", ""))}</div>'
                )
            st.markdown(_card(_dot(C("error")) + "未能定位到原文的问题", "".join(parts), "danger"), unsafe_allow_html=True)


def _render_ocr_reports(result) -> None:
    """OCR结果写回患者病历(按文件名+文本内容去重, 兼容跨会话的持久化数据)并渲染识别报告"""
    reports = (result.详情 or {}).get("报告", []) if result else []
    if not reports:
        return
    ext_reports = st.session_state.patient_data.setdefault("外院报告", {})
    changed = False
    _section_title("识别报告")
    with st.container(key=_stream_key(4)):
        for rep in reports:
            fname = rep.get("文件名", "")
            text = rep.get("文本", "")
            is_dup = any(v.get("文件名") == fname and v.get("文本") == text for v in ext_reports.values())
            if not is_dup:
                ext_reports[f"报告_{len(ext_reports) + 1}_{fname}"] = {
                    "文件名": fname,
                    "报告类型": rep.get("报告类型", "待确认"),
                    "识别来源": rep.get("来源", "OCR"),
                    "文本": text,
                    "提取数据": rep.get("提取数据", {}),
                    "低置信度字段": rep.get("低置信度字段", []),
                }
                changed = True
            with st.expander(f"{fname} ({rep.get('报告类型', '待确认')})"):
                if rep.get("提取数据"):
                    st.markdown("**提取数据:**")
                    for k, v in rep["提取数据"].items():
                        st.markdown(f"- {k}: {v}")
                st.markdown("**OCR文本:**")
                st.text(rep.get("文本", ""))
                if rep.get("低置信度字段"):
                    st.markdown("**低置信度字段:** " + "、".join(rep["低置信度字段"]))
    if changed:
        folder = st.session_state.get("patient_folder")
        if folder:
            save_external_reports(folder, ext_reports)


def page_admission():
    # 入院子导航(与顶部风格统一)
    sec_items = [
        {"id": "ocr", "label": "1) 外院病历OCR"},
        {"id": "diag", "label": "2) 诊断不一致检测"},
        {"id": "order", "label": "3) 医嘱遗漏检测"},
    ]
    # 用URL参数 adsec 同步, 默认 ocr
    adsec = st.query_params.get("adsec") or "ocr"
    if adsec not in {"ocr", "diag", "order"}:
        adsec = "ocr"
    prev_sec = st.session_state.get("admission_section")
    st.session_state.admission_section = {"ocr": "外院病历OCR", "diag": "诊断不一致检测", "order": "医嘱遗漏检测"}[adsec]
    _render_tabs("admission", sec_items, adsec, param_key="adsec", active_px=18, inactive_px=16)

    section = st.session_state.admission_section
    prev = st.session_state.get("_admission_prev_section")
    if prev is not None and prev != section:
        # 切换入院页分段时重置流式标记, 保证重新进入该分段时(含缓存命中)块元素重新淡入
        for k in list(st.session_state.keys()):
            if k.startswith("qilu_streamed_") or k.startswith("np_streamed_"):
                del st.session_state[k]
    st.session_state._admission_prev_section = section

    _set_stream_scope({
        "外院病历OCR": "admission_ocr",
        "诊断不一致检测": "admission_diag",
        "医嘱遗漏检测": "admission_order",
    }[section])

    if adsec == "diag":
        _section_title("2. 病历与初步诊断不一致检测")
        st.write("检测入院诊断与病历资料之间的差异，如遗漏糖尿病等合并症")
        auto_run_skills(["S02"], step_id="admission")
        result = st.session_state.step_results.get("S02")
        if result:
            render_result(result)
            if result.详情:
                with st.container(key=_stream_key(4)):
                    st.markdown(f"**当前入院诊断:** {result.详情.get('入院诊断', '-')}")
                    merged = result.详情.get("检出合并症", [])
                    if merged:
                        _section_title("合并症检出")
                        for item in merged:
                            status = item.get("状态", "")
                            mark = _dot(C("warning")) if status == "遗漏" else _dot(C("support"))
                            st.markdown(f"{mark} **{item.get('疾病', '')}** ({status})", unsafe_allow_html=True)
                            if item.get("证据"):
                                st.markdown(
                                    f'<div style="color:#195296;font-size:17px;margin:-8px 0 12px 20px;">'
                                    f'证据: {_esc(item["证据"])}</div>',
                                    unsafe_allow_html=True,
                                )
            render_tail(result)
        if st.button("重新执行诊断检测", key="btn_diag"):
            ph = st.empty()
            result = run_skill("S02", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "admission"), _stream_placeholder=ph)
            ph.empty()
            st.session_state.step_results["S02"] = result
            st.rerun()

    elif adsec == "order":
        _section_title("3. 医嘱遗漏检测")
        st.write("检测入院后应开但未开的药物、检查、检验，并核查检查检验时效性(过期/外院医保重做)")
        auto_run_skills(["S03"], step_id="admission_order")
        result = st.session_state.step_results.get("S03")
        if result:
            render_result(result)
            render_tail(result)
        if st.button("重新执行医嘱检测", key="btn_order"):
            ph = st.empty()
            result = run_skill("S03", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "admission_order"), _stream_placeholder=ph)
            ph.empty()
            st.session_state.step_results["S03"] = result
            st.rerun()

    else:  # ocr
        _section_title("1. 外院病历录入")
        st.markdown(
            f'<div style="border:1px solid {C("border_light")};border-radius:10px;background:{C("surface_tint")};'
            f'padding:12px 16px;margin:0 0 14px;color:{C("text_secondary")};font-size:16px;line-height:1.6;">'
            f'支持上传图片（JPG/PNG/BMP）或 PDF 文件，系统将自动识别文字并提取关键病历信息。</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:18px;font-weight:600;color:{C("text_primary")};margin:0 0 8px;">'
            f'{_dot(C("brand_main"))}上传外院报告</div>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "点击或拖拽文件到此处上传",
            type=["jpg", "jpeg", "png", "bmp", "webp", "pdf"],
            accept_multiple_files=True,
            key="ocr_upload",
            label_visibility="collapsed",
        )
        images = st.session_state.patient_images
        if images:
            st.markdown(
                f'<div style="font-size:17px;font-weight:600;color:{C("text_primary")};margin:12px 0 8px;">'
                f'当前患者已有 {len(images)} 份外院报告</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(min(3, len(images)))
            for i, img_path in enumerate(images):
                with cols[i % 3]:
                    if str(img_path).lower().endswith(".pdf"):
                        st.markdown(
                            f'<div style="border:1px solid {C("border_light")};border-radius:8px;'
                            f'background:{C("surface")};padding:10px 14px;text-align:center;'
                            f'color:{C("text_secondary")};font-size:15px;">'
                            f'📄 {os.path.basename(img_path)}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.image(img_path, caption=os.path.basename(img_path), width=220)
        if uploaded:
            st.markdown(
                f'<div style="font-size:17px;font-weight:600;color:{C("text_primary")};margin:12px 0 8px;">'
                f'已上传 {len(uploaded)} 份文件</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(min(3, len(uploaded)))
            for i, f in enumerate(uploaded):
                with cols[i % 3]:
                    if f.name.lower().endswith(".pdf"):
                        st.markdown(
                            f'<div style="border:1px solid {C("border_brand")};border-radius:8px;'
                            f'background:{C("surface")};padding:10px 14px;text-align:center;'
                            f'color:{C("text_primary")};font-size:15px;">'
                            f'📄 {f.name}<br><span style="color:{C("text_muted")};font-size:13px;">'
                            f'{len(f.getvalue())//1024} KB</span></div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.image(f, caption=f.name, width=280)

        st.markdown("")
        if st.button("执行OCR识别", key="btn_ocr", type="primary"):
            img_sources = [{"path": p} for p in images]
            img_sources += [{"name": f.name, "data": f.getvalue()} for f in uploaded]
            ocr_ph = st.empty()
            result = run_skill(
                "S01",
                images=img_sources,
                context_data=filter_sections_for_step(st.session_state.patient_data, "admission"),
                _stream_placeholder=ocr_ph,
            )
            ocr_ph.empty()
            st.session_state.step_results["S01"] = result
            render_result(result)
            _render_ocr_reports(result)
            render_tail(result)


def page_first_record():
    _section_title("鉴别诊断与诊疗计划")
    st.write("根据外院初步诊断及检查检验结果，给出鉴别诊断和诊疗计划")
    auto_run_skills(["S04"], step_id="first_record")

    result = st.session_state.step_results.get("S04")
    if result:
        render_result(result)
        if result.详情:
            with st.container(key=_stream_key(4)):
                st.markdown(f"**主要诊断:** {result.详情.get('主要诊断', '-')}")

                # 内镜图片展示
                folder = st.session_state.get("patient_folder")
                if folder:
                    endo_candidates = [
                        os.path.join(folder, f) for f in ["电子喉镜.jpg", "电子喉镜.png", "电子喉镜.jpeg"]
                    ]
                    endo_img = next((p for p in endo_candidates if os.path.exists(p)), None)
                    if endo_img:
                        _section_title("电子喉镜")
                        # 从患者数据中读取内镜报告信息
                        pdata = st.session_state.get("patient_data", {})
                        endo_key = next((k for k in pdata if "电子喉镜报告单" in k), None)
                        endo_report = pdata.get(endo_key, {}) if endo_key else {}
                        finding = endo_report.get("检查所见", "")
                        diagnosis = endo_report.get("检查诊断", "")
                        # 提前取鉴别诊断列表, 供智能检索使用
                        diff_list = result.详情.get("鉴别诊断", [])
                        col_img, col_sim = st.columns([3, 2])
                        with col_img:
                            st.image(str(endo_img), width=500)
                            if finding:
                                st.markdown(f"**检查所见:** {finding}")
                            if diagnosis:
                                st.markdown(f"**检查诊断:** {diagnosis}")
                        with col_sim:
                            st.markdown("**专病库智能检索**")
                            mode = st.selectbox(
                                "检索范围",
                                options=["按内镜相似", "按鉴别诊断相似", "按患者特征"],
                                key="ai_sim_mode",
                            )
                            # 高级筛选(仅前端占位，后续接入画像/标签后生效)
                            with st.expander("高级筛选(示例)", expanded=False):
                                _age = st.slider("年龄范围", 0, 100, (30, 80), key="ai_sim_age")
                                _gender = st.radio("性别", ["不限", "男", "女"], index=0, horizontal=True, key="ai_sim_gender")
                                _region = st.radio("居住地区", ["不限", "农村", "城市"], index=0, horizontal=True, key="ai_sim_region")
                                _smoke = st.radio("吸烟", ["不限", "有", "无"], index=0, horizontal=True, key="ai_sim_smoke")
                                _drink = st.radio("饮酒", ["不限", "有", "无"], index=0, horizontal=True, key="ai_sim_drink")
                                _hpv = st.radio("HPV感染史", ["不限", "有", "无"], index=0, horizontal=True, key="ai_sim_hpv")
                            similar_cfg = _load_similar_cases(folder)
                            # 触发检索
                            if st.button("检索", key="btn_ai_reco", type="primary"):
                                # 简单打分：按关键词重合数
                                def _score_case(text, case):
                                    base = (case.get("检查所见", "") + " " + case.get("检查诊断", "")).lower()
                                    kws = [k for k in re.split(r"[^\w\u4e00-\u9fa5]+", text.lower()) if len(k) >= 2]
                                    return sum(1 for k in set(kws) if k and k in base)
                                results = {}
                                if mode == "按内镜相似":
                                    src_text = (finding or "") + " " + (diagnosis or "")
                                    scored = [
                                        (case, _score_case(src_text, case)) for case in similar_cfg.get("内镜相似", [])
                                    ]
                                    scored.sort(key=lambda x: x[1], reverse=True)
                                    results["endo"] = scored[:5]
                                else:
                                    if mode == "按鉴别诊断相似":
                                        # 按诊断逐个推荐
                                        diff_sim = similar_cfg.get("鉴别相似", {})
                                        group = {}
                                        for dx in diff_list:
                                            name = dx.get("诊断", "")
                                            matched = []
                                            for key, cases in diff_sim.items():
                                                if key in name or name in key:
                                                    matched.extend([(c, 1) for c in cases])
                                            group[name] = matched[:4]
                                        results["diff"] = group
                                    else:
                                        # 按患者特征(示例): 目前示例数据无年龄/性别/地区/吸烟/饮酒/HPV字段，这里仅演示返回前N条
                                        # 未来可根据 _age/_gender/_region/_smoke/_drink/_hpv 过滤/加权
                                        pool = similar_cfg.get("内镜相似", [])
                                        results["feature"] = [(c, 0) for c in pool[:6]]
                                st.session_state["ai_sim_results"] = results

                            # 展示结果
                            res = st.session_state.get("ai_sim_results")
                            if res:
                                if mode == "按内镜相似" and res.get("endo"):
                                    for case, _ in res["endo"]:
                                        img_path = os.path.join(folder, case["img"]) if case.get("img") else None
                                        row = st.columns([5, 1])
                                        with row[0]:
                                            st.markdown(
                                                f'<div style="border:1px solid {C("border_light")};border-radius:10px;'
                                                f'padding:10px 12px;margin:8px 0;">'
                                                f'<div style="font-weight:700;color:{C("text_primary")};">{_esc(case["name"])}</div>'
                                                f'<div style="color:{C("text_secondary")};font-size:14px;">{_esc(case.get("diag", ""))}</div>'
                                                f'</div>',
                                                unsafe_allow_html=True,
                                            )
                                        with row[1]:
                                            if st.button("查看内镜报告", key=f"ai_endo_{case['name']}", type="primary"):
                                                _show_similar_case_dialog(case["name"], case.get("diag", ""), img_path, case.get("url", "#"), case.get("检查所见", ""), case.get("检查诊断", ""))
                                if mode == "按鉴别诊断相似" and res.get("diff"):
                                    diff_results = res["diff"]

                                    for dx_name, items in diff_results.items():
                                        is_open = (st.session_state.get("ai_diff_selected_dx") == dx_name)
                                        arrow = "▾" if is_open else "▸"
                                        if st.button(
                                            f"{arrow} {dx_name}",
                                            key=f"ai_diff_hdr_{dx_name}",
                                            use_container_width=True,
                                            type="primary" if is_open else "secondary",
                                        ):
                                            st.session_state["ai_diff_selected_dx"] = "" if is_open else dx_name
                                            st.rerun()
                                        if is_open:
                                            for case, _ in items:
                                                img_path = os.path.join(folder, case["img"]) if case.get("img") else None
                                                c1, c2 = st.columns([5, 1])
                                                with c1:
                                                    st.markdown(
                                                        f'<span style="font-weight:600;color:{C("text_primary")};">{_esc(case["name"])}</span>'
                                                        f'<span style="color:{C("text_secondary")};font-size:14px;margin-left:8px;">{_esc(case.get("diag", ""))}</span>',
                                                        unsafe_allow_html=True,
                                                    )
                                                with c2:
                                                    if st.button("查看内镜报告", key=f"ai_diff_{dx_name}_{case['name']}", type="primary"):
                                                        _show_similar_case_dialog(case["name"], case.get("diag", ""), img_path, case.get("url", "#"), case.get("检查所见", ""), case.get("检查诊断", ""))
                                if mode == "按患者特征" and res.get("feature"):
                                    for case, _ in res["feature"]:
                                        img_path = os.path.join(folder, case["img"]) if case.get("img") else None
                                        row = st.columns([3, 1])
                                        with row[0]:
                                            st.markdown(f"{_esc(case['name'])} · {_esc(case.get('diag',''))}")
                                        with row[1]:
                                            if st.button("查看内镜报告", key=f"ai_feat_{case['name']}", type="primary"):
                                                _show_similar_case_dialog(case["name"], case.get("diag", ""), img_path, case.get("url", "#"), case.get("检查所见", ""), case.get("检查诊断", ""))

                diff_list = result.详情.get("鉴别诊断", [])
                if diff_list:
                    _section_title("鉴别诊断详情")
                    folder = st.session_state.get("patient_folder")
                    diff_similar = _load_similar_cases(folder).get("鉴别相似", {})
                    for dx in diff_list:
                        name = dx.get("诊断", "")
                        prob = dx.get("可能性", "")
                        features = dx.get("特点", "")
                        support = dx.get("支持点", "")
                        diff = dx.get("鉴别点", "")
                        body = (
                            f'<div style="padding:4px 0;"><b>{_esc(features)}</b></div>'
                            f'<div style="padding:4px 0;"><span style="color:{C("support")};">支持点:</span> '
                            f'{_esc(support)}</div>'
                            f'<div style="padding:4px 0;"><span style="color:{C("diff")};">鉴别点:</span> '
                            f'{_esc(diff)}</div>'
                        )
                        title = _esc(name) + (f" (可能性: {_esc(prob)})" if prob else "")
                        st.markdown(_card(title, body, "ref"), unsafe_allow_html=True)
                        # 相似病例按钮移除，统一由上方“AI 智能检索”输出
                further = result.详情.get("进一步检查", [])
                if further:
                    _section_title("进一步检查")
                    for c in further:
                        st.markdown(f"- {c}")
        render_tail(result)

    if st.button("重新生成鉴别诊断", key="btn_diff"):
        ph = st.empty()
        result = run_skill("S04", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "first_record"), _stream_placeholder=ph)
        ph.empty()
        st.session_state.step_results["S04"] = result
        st.rerun()


def page_supplement():
    _section_title("手术指征与禁忌评估")
    st.write("根据院内外检查检验结果，AI提示手术指征和禁忌")
    auto_run_skills(["S05"], step_id="supplement")

    result = st.session_state.step_results.get("S05")
    if result:
        render_result(result)
        if result.详情:
            with st.container(key=_stream_key(4)):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**手术指征评估:**")
                    for item in result.详情.get("指征评估", []):
                        st.markdown(f"- {item['项目']}: {item['状态']}")
                        if item.get("来源"):
                            st.markdown(f'<span style="color:#788292;font-size:16px;">来源: {add_guideline_links(item["来源"])}</span>', unsafe_allow_html=True)
                with col2:
                    st.markdown("**禁忌症检查:**")
                    for item in result.详情.get("禁忌检查", []):
                        st.markdown(f"- {item['项目']}: {item['状态']}")
                        if item.get("来源"):
                            st.markdown(f'<span style="color:#788292;font-size:16px;">来源: {add_guideline_links(item["来源"])}</span>', unsafe_allow_html=True)

                st.markdown("**术前准备清单:**")
                checklist = result.详情.get("术前准备清单", [])
                for item in checklist:
                    st.markdown(f"- [{item['状态']}] {item['项目']}")

                risks = result.详情.get("风险评估", [])
                if risks:
                    _section_title("风险评估")
                    for r in risks:
                        st.markdown(f"- **{r.get('风险', '')}** ({r.get('等级', '')}): {r.get('描述', '')}")
        render_tail(result)

    if st.button("重新评估手术指征", key="btn_indication"):
        ph = st.empty()
        result = run_skill("S05", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "supplement"), _stream_placeholder=ph)
        ph.empty()
        st.session_state.step_results["S05"] = result
        st.rerun()


def page_preop():
    _section_title("手术方案决策")
    st.write("根据院内外检查检验结果，AI给出手术指导及治疗决策")
    auto_run_skills(["S06"], step_id="preop")

    result = st.session_state.step_results.get("S06")
    if result:
        render_result(result)
        if result.详情:
            with st.container(key=_stream_key(4)):
                staging = result.详情.get("肿瘤分期", {})
                _section_title("肿瘤分期")
                _st = staging.get('状态') or ''
                status_icon = _dot(C('warning')) if _st == '待MDT复核' else ''
                st.markdown(
                    f"**T:** {staging.get('T', '-')}　　"
                    f"**N:** {staging.get('N', '-')}　　"
                    f"**M:** {staging.get('M', '-')}　　"
                    f"**分期:** {staging.get('分期', '-')}　　"
                    f"**状态:** {status_icon}{_st or '-'}",
                    unsafe_allow_html=True
                )
                if staging.get("T依据") or staging.get("N依据") or staging.get("M依据") or staging.get("分期体系"):
                    for label, key in (("T", "T依据"), ("N", "N依据"), ("M", "M依据")):
                        v = staging.get(key)
                        if v:
                            st.markdown(f"**{label} 依据:** {v}")
                    if staging.get("分期体系"):
                        st.markdown(f"**分期体系:** {staging['分期体系']}")

                _section_title("推荐手术方案")
                folder = st.session_state.get("patient_folder")
                surg_similar = _load_similar_cases(folder).get("手术相似", {})
                for i, proc in enumerate(result.详情.get("推荐术式", [])):
                    with st.expander(proc["名称"], expanded=(i == 0)):
                        st.markdown(f"**类型:** {proc['类型']}")
                        st.markdown(f"**依据:** {proc['依据']}")
                        if proc.get("来源"):
                            st.markdown(f"**来源:** {add_guideline_links(proc['来源'])}", unsafe_allow_html=True)
                        st.markdown(f"**优势:** {proc['优势']}")
                        st.markdown(f"**风险:** {proc['风险']}")
                        matched_surg = []
                        for key, cases in surg_similar.items():
                            if key in proc["名称"] or proc["名称"] in key:
                                matched_surg.extend(cases)
                        # 去重(按name)
                        seen = set()
                        matched_surg = [c for c in matched_surg if c["name"] not in seen and not seen.add(c["name"])]
                        if matched_surg:
                            st.markdown("**相似手术案例:**")
                            for sc in matched_surg:
                                st.markdown(f'- <a href="{sc.get("url", "#")}" target="_blank">{_esc(sc["name"])} — {_esc(sc.get("desc", ""))}</a>', unsafe_allow_html=True)

                alternates = result.详情.get("替代方案", [])
                if alternates:
                    _section_title("替代方案")
                    for alt in alternates:
                        st.markdown(f"- **{alt.get('名称', '')}** —— {alt.get('适应证', '')}")

                notes = result.详情.get("关键注意事项", [])
                if notes:
                    _section_title("关键注意事项")
                    for n in notes:
                        st.markdown(f"- {n}")
        render_tail(result)

    if st.button("重新生成手术方案", key="btn_plan"):
        ph = st.empty()
        result = run_skill("S06", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "preop"), _stream_placeholder=ph)
        ph.empty()
        st.session_state.step_results["S06"] = result
        st.rerun()


def page_postop():
    _section_title("病理解读")
    st.write("解读病理报告免疫组化，指导后续治疗建议")
    auto_run_skills(["S07"], step_id="postop")

    result = st.session_state.step_results.get("S07")
    if result:
        render_result(result)
        if result.详情:
            with st.container(key=_stream_key(4)):
                _section_title("病理小结")
                path = result.详情.get("病理小结", {})
                if path:
                    st.markdown(f"**诊断:** {path.get('诊断', '')}")
                    st.markdown(f"**分期:** {path.get('分期', '')}")
                    st.markdown(f"**切缘:** {path.get('切缘', '')}")
                    st.markdown(f"**淋巴结:** {path.get('淋巴结', '')}")

                _section_title("免疫组化解读")
                ihc = result.详情.get("免疫组化解读", [])
                for marker in ihc:
                    st.markdown(f"**{marker['指标']}** ({marker['结果']}): {marker['含义']}")

                _section_title("治疗建议")
                treatment = result.详情.get("治疗建议", {})
                if treatment:

                    def render_field(label: str, value, fmt=lambda it: it, ref=False):
                        items = _as_list(value)
                        if not items:
                            return
                        shown = (lambda it: _ref(fmt(it))) if ref else fmt
                        if len(items) == 1:
                            st.markdown(f"**{label}:** {shown(items[0])}", unsafe_allow_html=ref)
                            return
                        st.markdown(f"**{label}:**")
                        for i, it in enumerate(items, 1):
                            st.markdown(f"{i}. {shown(it)}", unsafe_allow_html=ref)

                    def fmt_plan(p):
                        if not isinstance(p, dict):
                            return str(p)
                        text = f"{p.get('措施', '')}"
                        if p.get("时机"):
                            text += f"（时机: {p['时机']}）"
                        if p.get("说明"):
                            text += f"　{p['说明']}"
                        refs = p.get("引用")
                        if refs is not None:
                            if isinstance(refs, list):
                                text += f"[{','.join(str(x) for x in refs)}]"
                            else:
                                text += f"[{refs}]"
                        return text

                    if treatment.get("方案"):
                        st.markdown(f"**总体方案:** {_ref(treatment['方案'])}", unsafe_allow_html=True)
                    render_field("辅助治疗", treatment.get("辅助治疗", []), fmt_plan, ref=True)
                    render_field("理由", treatment.get("理由", ""), ref=True)
                    render_field("随访", treatment.get("随访", ""), ref=True)

                    refs = _as_list(treatment.get("依据", []))
                    if refs:
                        st.markdown("**参考依据:**")
                        for i, r in enumerate(refs, 1):
                            txt = r.get("要点", "") if isinstance(r, dict) else str(r)
                            src = r.get("来源", "") if isinstance(r, dict) else ""
                            parts = [p.strip() for p in re.split(r"[；;]", str(txt)) if p.strip()]
                            if len(parts) > 1:
                                body = "".join(f'<div style="margin:1px 0;">{_esc(p)}</div>' for p in parts)
                            else:
                                body = _esc(txt)
                            st.markdown(f"{i}. {body}{f'（{add_guideline_links(src)}）' if src else ''}", unsafe_allow_html=True)

                # ── 药物推荐 ──
                drug_rec = result.详情.get("药物推荐", {})
                if drug_rec and drug_rec.get("组成"):
                    _section_title("推荐药物方案")
                    # 方案名称+类型
                    方案名 = drug_rec.get("方案名", "")
                    方案类型 = drug_rec.get("方案类型", "")
                    if 方案名:
                        st.markdown(
                            f'<div style="background:{C("brand_main")}10;border:1px solid {C("brand_main")}30;'
                            f'border-radius:8px;padding:12px 16px;margin:8px 0;">'
                            f'<div style="font-size:18px;font-weight:700;color:{C("brand_main")};">{_esc(方案名)}</div>'
                            f'<div style="font-size:14px;color:{C("text_secondary")};margin-top:4px;">{_esc(方案类型)}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    # 适用条件
                    if drug_rec.get("适用条件"):
                        st.markdown(f"**适用条件:** {_esc(drug_rec['适用条件'])}")
                    # 药物列表卡片
                    for med in drug_rec.get("组成", []):
                        分类 = med.get("分类", "")
                        国产 = med.get("国产or进口", "")
                        医保 = med.get("医保", "")
                        医保说明 = med.get("医保说明", "")
                        if 分类 == "免疫药":
                            tag_c, tag_bg = "#7c3aed", "#7c3aed18"
                        elif 分类 == "靶向药":
                            tag_c, tag_bg = "#0891b2", "#0891b218"
                        else:
                            tag_c, tag_bg = "#2563eb", "#2563eb18"
                        医保_color = "#16a34a" if "甲类" in 医保 else ("#d97706" if "乙类" in 医保 else "#dc2626")
                        医保_html = f'<div style="margin-top:4px;font-size:13px;color:{C("text_secondary")};">📋 {_esc(医保说明)}</div>' if 医保说明 else ""
                        参考单价 = med.get("参考单价", "")
                        单次费用 = med.get("单次费用估算", "")
                        价格_html = ""
                        if 参考单价 or 单次费用:
                            价格_parts = []
                            if 参考单价:
                                价格_parts.append(f"单价: ¥{_esc(参考单价)}")
                            if 单次费用:
                                价格_parts.append(f"单次费用: ¥{_esc(单次费用)}")
                            价格_html = f'<div style="margin-top:4px;font-size:13px;color:#16a34a;font-weight:600;">💰 {" | ".join(价格_parts)}</div>'
                        st.markdown(
                            f'<div style="border:1px solid {C("border_light")};border-radius:8px;'
                            f'padding:12px 16px;margin:6px 0;">'
                            f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
                            f'<span style="font-weight:700;font-size:16px;color:{C("text_primary")};">{_esc(med.get("药物", ""))}</span>'
                            f'<span style="background:{tag_bg};color:{tag_c};padding:2px 8px;border-radius:4px;font-size:13px;font-weight:600;">{_esc(分类)}</span>'
                            f'<span style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:4px;font-size:13px;">{_esc(med.get("亚类", ""))}</span>'
                            f'</div>'
                            f'<div style="margin-top:6px;font-size:14px;color:{C("text_secondary")};">'
                            f'剂量: {_esc(med.get("剂量", "-"))}'
                            f'</div>'
                            f'<div style="margin-top:4px;display:flex;gap:12px;font-size:13px;">'
                            f'<span>🏭 {_esc(国产)}</span>'
                            f'<span style="color:{医保_color};font-weight:600;">💰 {_esc(医保)}</span>'
                            f'</div>'
                            f'{医保_html}'
                            f'{价格_html}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    if drug_rec.get("指南依据"):
                        st.markdown(f"**指南依据:** {add_guideline_links(drug_rec['指南依据'])}", unsafe_allow_html=True)
        render_tail(result)

    if st.button("重新解读病理", key="btn_path"):
        ph = st.empty()
        result = run_skill("S07", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "postop"), _stream_placeholder=ph)
        ph.empty()
        st.session_state.step_results["S07"] = result
        st.rerun()


def page_discharge():
    st.markdown(_PART_CSS, unsafe_allow_html=True)

    st.markdown(
        _part_header("出院护理服务包", "居家延续护理 · 按病种选购 · 费用结算", C("brand_secondary"), "延续护理"),
        unsafe_allow_html=True,
    )
    with st.container(key="part_nursing_pkg"):
        render_nursing_package(load_nursing_package(), st.session_state.patient_data)

    st.markdown(
        _part_header("出院医嘱", "依据手术记录、病程记录与病理报告自动生成", C("brand_secondary"), "医嘱生成"),
        unsafe_allow_html=True,
    )
    with st.container(key="part_discharge_orders"):
        auto_run_skills(["S08"], step_id="discharge")

        result = st.session_state.step_results.get("S08")
        if result:
            render_result(result)
            if result.详情:
                with st.container(key=_stream_key(4)):
                    _section_title("药物医嘱")
                    for med in result.详情.get("药物", []):
                        st.markdown(f"- {med.get('项目', '')} ({med.get('疗程', '')}) - {med.get('备注', '')}")

                    _section_title("饮食建议")
                    for d in result.详情.get("饮食", []):
                        st.markdown(f"- {d}")

                    _section_title("活动建议")
                    for a in result.详情.get("活动", []):
                        st.markdown(f"- {a}")

                    _section_title("伤口护理")
                    for w in result.详情.get("伤口护理", []):
                        st.markdown(f"- {w}")

                    _section_title("随访安排")
                    for f in result.详情.get("随访", []):
                        st.markdown(f"- {f.get('时间', '')}: {f.get('项目', '')}")

                    _section_title("辅助治疗建议")
                    radio = result.详情.get("辅助治疗", {})
                    if radio:
                        st.markdown(f"- 建议: {radio.get('建议', '')}")
                        st.markdown(f"- 理由: {radio.get('理由', '')}")
                        st.markdown(f"- 时间: {radio.get('时机', '')}")

                    ps = result.详情.get("病理分期", {})
                    if ps:
                        _section_title("推断病理分期")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1:
                            st.markdown(f"**pT:** {ps.get('pT', '-')}")
                        with col2:
                            st.markdown(f"**pN:** {ps.get('pN', '-')}")
                        with col3:
                            st.markdown(f"**M:** {ps.get('M', '-')}")
                        with col4:
                            st.markdown(f"**Stage:** {ps.get('分期', '-')}")
                        with col5:
                            _st = ps.get('状态') or ''
                            st.markdown(f"**状态:** {_dot(C('warning')) if _st == '待MDT复核' else ''}{_st or '-'}", unsafe_allow_html=True)
                        if ps.get("依据"):
                            st.markdown(f"**推断依据:** {ps['依据']}")
                        if ps.get("分期体系"):
                            st.markdown(f"**分期体系:** {ps['分期体系']}")

                    _section_title("注意事项")
                    for p in result.详情.get("注意事项", []):
                        st.markdown(f"- {p}")

                    glossary = result.详情.get("术语解释", [])
                    if glossary:
                        _section_title("专业术语解释")
                        for item in glossary:
                            term = item.get("术语", "")
                            expl = item.get("解释", "")
                            src = item.get("来源", "")
                            if term and expl:
                                with st.expander(f"📖 {term}", expanded=False):
                                    st.markdown(f"{expl}")
                                    if src:
                                        st.caption(f"来源: {src}")
            render_tail(result)

        if st.button("重新生成出院医嘱", key="btn_discharge"):
            ph = st.empty()
            result = run_skill("S08", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "discharge"), _stream_placeholder=ph)
            ph.empty()
            st.session_state.step_results["S08"] = result
            st.rerun()


def page_frontsheet():
    _section_title("病案首页质检")
    auto_run_skills(["S09"], step_id="frontsheet")

    result = st.session_state.step_results.get("S09")
    if result:
        render_result(result)
        if result.详情:
            with st.container(key=_stream_key(4)):
                _section_title("DRG质控")
                st.write("输入诊断编码和手术操作编码，调用DRG分组器进行分组与费用测算")

                # ── 编码输入区 ──
                col_diag, col_surg = st.columns(2)
                with col_diag:
                    zd_input = st.text_area(
                        "诊断编码（医保版）",
                        value=st.session_state.get("drg_zd", "C09.900"),
                        height=120,
                        key="drg_zd_area",
                        help="一行一个编码，粘贴逗号列表自动拆分",
                    )
                    st.session_state["drg_zd"] = zd_input
                with col_surg:
                    ss_input = st.text_area(
                        "手术操作编码（医保版）",
                        value=st.session_state.get("drg_ss",
                            "28.9201\n25.1x04\n27.4900x020\n23.1900x003\n86.700x0013\n29.4x00x004"),
                        height=120,
                        key="drg_ss_area",
                        help="一行一个编码，粘贴逗号列表自动拆分",
                    )
                    st.session_state["drg_ss"] = ss_input

                show_msg = st.checkbox("显示分组过程", value=True, key="drg_show_msg")

                if st.button("DRG 分组", key="btn_drg_group", type="primary"):
                    # 自动拆分: 逗号/分号/换行 -> 逗号分隔字符串
                    def _parse_codes(text):
                        parts = re.split(r'[,;，；\n\r]+', text.strip())
                        return ','.join(p.strip() for p in parts if p.strip())
                    zd_codes = _parse_codes(zd_input)
                    ss_codes = _parse_codes(ss_input)
                    with st.spinner("正在调用DRG分组器..."):
                        group_result = drg_group(zd_codes, ss_codes, show_messages=show_msg)
                    st.session_state["drg_group_result"] = group_result

                # ── 分组结果 ──
                gr = st.session_state.get("drg_group_result")
                if gr:
                    if gr.get("statusCode") == 0 or gr.get("mdc"):
                        st.success(f"分组成功")
                        c1, c2, c3, c4 = st.columns(4)
                        for col, label, val in [
                            (c1, "MDC", gr.get("mdc", "-")),
                            (c2, "ADRG", gr.get("adrg", "-")),
                            (c3, "DRG", gr.get("drg", "-")),
                            (c4, "DRG名称", gr.get("drgName", "-")),
                        ]:
                            with col:
                                st.markdown(
                                    f'<div style="text-align:center;margin:4px 0;">'
                                    f'<div style="font-size:17px;font-weight:600;color:{C("text_secondary")};">{label}</div>'
                                    f'<div style="font-size:22px;font-weight:800;color:{C("brand_main")};margin-top:2px;">{_esc(val)}</div>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                        if gr.get("messages"):
                            with st.expander("分组过程详情", expanded=False):
                                for msg in gr["messages"]:
                                    st.markdown(f"- {msg}")
                    else:
                        st.error(f"分组失败: {gr.get('statusMsg', '未知错误')}")

                # ── 入院诊断漏诊提示 ──
                result_s09 = st.session_state.step_results.get("S09")
                if result_s09 and result_s09.详情:
                    diag_missed = False
                    for c in result_s09.详情.get("检查结果", []):
                        if "入院诊断" in c.get("项目", "") and c.get("状态") == "不通过":
                            diag_missed = True
                            break
                    if diag_missed:
                        st.markdown(
                            f'<div style="background:#fef3cd;border:1px solid #ffc107;border-radius:8px;'
                            f'padding:12px 16px;margin:12px 0;">'
                            f'<div style="font-size:16px;font-weight:700;color:#856404;margin-bottom:6px;">'
                            f'⚠️ 入院诊断遗漏合并症，影响DRG分组</div>'
                            f'<div style="font-size:14px;line-height:1.7;color:#856404;">'
                            f'当前分组 <b>{_esc(gr.get("drg", "-") if gr else "-")}</b> '
                            f'仅基于"扁桃体恶性肿瘤"入组。'
                            f'若补全入院诊断中的<b>高血压</b>和<b>腰间盘突出</b>，'
                            f'可能触发MCC/CC判定，DRG分组将发生变化，'
                            f'标准费用与医保结算金额也会相应调整。</div></div>',
                            unsafe_allow_html=True,
                        )

                st.markdown("---")

                # ── 费用测算区 ──
                _section_title("费用测算")
                fe_c1, fe_c2, fe_c3 = st.columns(3)
                with fe_c1:
                    fee_drg = st.text_input(
                        "DRG 编码",
                        value=gr.get("drg", "") if gr else st.session_state.get("fee_drg", "DG29"),
                        key="fee_drg_input",
                    )
                    st.session_state["fee_drg"] = fee_drg
                with fe_c2:
                    fee_level = st.selectbox(
                        "医院等级", ["A", "B", "C", "D"], index=0, key="fee_level_input",
                    )
                with fe_c3:
                    fee_insurance = st.selectbox(
                        "医保类型",
                        ["职工医保", "居民医保"],
                        index=0,
                        key="fee_insurance_input",
                    )
                # 映射医保类型到接口参数
                insurance_map = {"职工医保": "employee", "居民医保": "resident"}

                if st.button("测算费用", key="btn_drg_fee", type="primary"):
                    with st.spinner("正在测算费用..."):
                        fee_result = drg_calc_fee(
                            fee_drg,
                            hospital_level=fee_level,
                            medical_insurance_type=insurance_map.get(fee_insurance, "employee"),
                        )
                    st.session_state["drg_fee_result"] = fee_result

                fr = st.session_state.get("drg_fee_result")
                if fr and "error" not in fr:
                    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
                    for col, label, val, fmt in [
                        (fc1, "权重", fr.get("weight", 0), ".4f"),
                        (fc2, "费率", fr.get("fee_base", 0), ".2f"),
                        (fc3, "标准费用", fr.get("std_fee", 0), ".2f"),
                        (fc4, "高倍率费用", fr.get("high_fee", 0), ".2f"),
                        (fc5, "低倍率费用", fr.get("low_fee", 0), ".2f"),
                    ]:
                        with col:
                            st.markdown(
                                f'<div style="text-align:center;margin:4px 0;">'
                                f'<div style="font-size:17px;font-weight:600;color:{C("text_secondary")};">{label}</div>'
                                f'<div style="font-size:20px;font-weight:800;color:{C("brand_main")};margin-top:2px;">{format(val, fmt)}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                elif fr and "error" in fr:
                    st.error(f"费用测算失败: {fr['error']}")

                st.markdown("---")

                _section_title("检查结果")
                st.write("对比病案首页与病历内容")

                checks = result.详情.get("检查结果", [])
                consistency = result.详情.get("一致性检查", [])
                suggestions = result.详情.get("建议", [])

                # ── 统计条 ──
                n_pass = sum(1 for c in checks if c.get("状态") == "通过")
                n_fail = sum(1 for c in checks if c.get("状态") == "不通过")
                n_check = sum(1 for c in checks if c.get("状态") not in ("通过", "不通过"))
                sc1, sc2, sc3 = st.columns(3)
                for col, label, cnt, color in [
                    (sc1, "通过", n_pass, "#16a34a"),
                    (sc2, "不通过", n_fail, "#dc2626"),
                    (sc3, "待核查", n_check, "#d97706"),
                ]:
                    with col:
                        st.markdown(
                            f'<div style="text-align:center;padding:8px 0;border-radius:6px;'
                            f'background:{color}10;border:1px solid {color}30;">'
                            f'<span style="font-size:28px;font-weight:800;color:{color};">{cnt}</span>'
                            f'<span style="font-size:14px;color:{color};margin-left:6px;">{label}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # ── 检查项卡片 ──
                st.markdown(
                    '<style>'
                    'div[data-testid="stExpander"] summary p {'
                    'font-size:16px !important;font-weight:700 !important;}'
                    '</style>',
                    unsafe_allow_html=True,
                )
                for item in checks:
                    status = item.get("状态", "")
                    project = item.get("项目", "")
                    detail = item.get("详情", "")
                    if status == "通过":
                        border_c, bg_c, title_c, icon, default_exp = "#16a34a", "#16a34a08", "#16a34a", "✅", False
                    elif status == "不通过":
                        border_c, bg_c, title_c, icon, default_exp = "#dc2626", "#dc262608", "#dc2626", "❌", True
                    else:
                        border_c, bg_c, title_c, icon, default_exp = "#d97706", "#d9770608", "#d97706", "⚠️", True
                    with st.expander(f"{icon} [{status}] {project}", expanded=default_exp):
                        st.markdown(
                            f'<div style="font-size:15px;line-height:1.7;color:#1a1a1a;">'
                            f'{_esc(detail)}</div>' if detail else '',
                            unsafe_allow_html=True,
                        )

                # ── 一致性检查表格 ──
                if consistency:
                    _section_title("一致性检查")
                    rows_html = ""
                    for item in consistency:
                        s = item.get("状态", "")
                        p = item.get("项目", "")
                        if s == "一致":
                            tag_c, tag_bg = "#16a34a", "#16a34a18"
                        else:
                            tag_c, tag_bg = "#dc2626", "#dc262618"
                        rows_html += (
                            f'<tr>'
                            f'<td style="padding:8px 12px;border-bottom:1px solid {C("border_light")};font-size:15px;">{_esc(p)}</td>'
                            f'<td style="padding:8px 12px;border-bottom:1px solid {C("border_light")};text-align:center;">'
                            f'<span style="background:{tag_bg};color:{tag_c};padding:2px 10px;border-radius:4px;font-size:13px;font-weight:600;">{_esc(s)}</span></td>'
                            f'</tr>'
                        )
                    st.markdown(
                        f'<table style="width:100%;border-collapse:collapse;">'
                        f'<tr style="background:{C("surface_muted")};">'
                        f'<th style="padding:8px 12px;text-align:left;font-size:14px;font-weight:600;color:{C("text_secondary")};">检查项</th>'
                        f'<th style="padding:8px 12px;text-align:center;font-size:14px;font-weight:600;color:{C("text_secondary")};width:100px;">状态</th>'
                        f'</tr>{rows_html}</table>',
                        unsafe_allow_html=True,
                    )

                # ── 建议 ──
                if suggestions:
                    _section_title("整改建议")
                    for i, s in enumerate(suggestions, 1):
                        st.markdown(
                            f'<div style="display:flex;align-items:flex-start;gap:8px;padding:8px 12px;margin:4px 0;'
                            f'border-left:3px solid {C("brand_main")};background:{C("surface_muted")};border-radius:0 6px 6px 0;">'
                            f'<span style="font-size:14px;font-weight:700;color:{C("brand_main")};white-space:nowrap;">{i}.</span>'
                            f'<span style="font-size:14px;line-height:1.6;color:{C("text_primary")};">{_esc(s)}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
        render_tail(result)

    if st.button("重新执行质控检查", key="btn_drg"):
        ph = st.empty()
        result = run_skill("S09", force=True, context_data=filter_sections_for_step(st.session_state.patient_data, "frontsheet"), _stream_placeholder=ph)
        ph.empty()
        st.session_state.step_results["S09"] = result
        st.rerun()


STEP_PAGES = {
    "admission": page_admission,
    "first_record": page_first_record,
    "supplement": page_supplement,
    "preop": page_preop,
    "postop": page_postop,
    "discharge": page_discharge,
    "frontsheet": page_frontsheet,
}


def main():
    st.set_page_config(
        page_title="专病库AI辅助系统",
        page_icon="hospital",
        layout="wide",
    )

    init_session_state()
    _sync_patient_param()
    _sync_step_param()

    st.markdown(
        '<style>'
        'html,body,.stApp{font-size:17px;color:' + C("text_primary") + ';background:' + C("surface") + ';}'
        '.stButton button{font-size:17px;border-radius:8px;transition:all .15s ease;}'
        '.stButton button:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(20,52,96,0.18);}'
        '.stButton button:active{transform:translateY(0);}'
        # 流程导航radio → 仅放大字号，不做过度外观改造
        '[data-testid="stHorizontalBlock"] div[role="radiogroup"] label{'
        'font-size:24px !important;font-weight:800 !important;padding:12px 20px !important;}'
        '[data-testid="stHorizontalBlock"] div[role="radiogroup"] label span{'
        'font-size:24px !important;font-weight:800 !important;}'
        '.stCheckbox label p{font-size:17px;}'
        '[data-testid="stCaptionContainer"]{font-size:16px;color:' + C("text_caption") + ';}'
        '[data-testid="stSegmentedControl"] button{border-radius:8px;}'
        '.stMarkdown p{font-size:17px;line-height:1.7;}'
        '.stMarkdown li{font-size:17px;line-height:1.7;}'
        '.stMarkdown h1{font-size:28px;}'
        '.stMarkdown h2{font-size:24px;}'
        '.stMarkdown h3{font-size:20px;}'
        'h1,h2,h3,label,p,span,div{font-size:inherit;}'
        '.stExpander summary{font-size:17px;font-weight:600;}'
        '.stSelectbox label,.stMultiSelect label,.stRadio label,.stSlider label{font-size:17px;}'
        '.stTextArea label,.stTextInput label,.stNumberInput label{font-size:17px;}'
        '</style>',
        unsafe_allow_html=True,
    )

    info = st.session_state.patient_data.get("病案首页", {})
    ident = info.get("病案号", "") or os.path.basename(st.session_state.patient_folder or "") or "-"
    _name = info.get("姓名", "-")
    _mask = (_name[0] + "**") if _name and _name != "-" and len(_name) > 1 else (_name or "-")
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:14px;'
        f'background:linear-gradient(135deg,{C("brand_bar")},{C("brand_secondary")});'
        f'color:#fff;border-radius:12px;border:1px solid rgba(255,255,255,.15);'
        f'padding:16px 24px;margin:0 0 16px;box-shadow:0 4px 16px rgba(20,52,96,0.22);">'
        f'<div style="display:flex;align-items:center;gap:12px;min-width:0;">'
        f'<span style="font-size:28px;">🏥</span>'
        f'<span style="font-size:26px;font-weight:700;letter-spacing:.5px;white-space:nowrap;">专病库AI辅助系统</span>'
        f'<span style="font-size:16px;opacity:.85;white-space:nowrap;">耳鼻喉专科</span></div>'
        f'<div style="font-size:16px;text-align:right;white-space:nowrap;">'
        f'<b>{_esc(ident)}</b> · {_esc(_mask)} · {_esc(info.get("性别", "-"))} / '
        f'{_esc(str(info.get("年龄", "-")))}岁 · 住院号 {_esc(info.get("住院号", "-"))}</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("patient_param_unmatched"):
        st.warning(f"未找到患者参数「{st.session_state['patient_param_unmatched']}」，已展示默认患者")

    step = WORKFLOW_STEPS[st.session_state.current_step]

    last = st.session_state.get("_np_last_step")
    if last is not None and last != st.session_state.current_step:
        for k in list(st.session_state.keys()):
            if k.startswith("np_streamed_") or k.startswith("qilu_streamed_"):
                del st.session_state[k]
        st.session_state.pop("_stream_scope", None)
    st.session_state._np_last_step = st.session_state.current_step

    # 顶部大字号标签卡导航(HTML + QueryParam)，避免控件样式干扰
    _render_top_tabs()

    page_func = STEP_PAGES.get(step["id"])
    if page_func:
        page_func()

    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.session_state.current_step > 0:
            if st.button("上一步"):
                st.session_state.current_step -= 1
                # 同步URL参数
                st.query_params["step"] = WORKFLOW_STEPS[st.session_state.current_step]["id"]
                st.rerun()
    with col3:
        if st.session_state.current_step < len(WORKFLOW_STEPS) - 1:
            if st.button("下一步"):
                st.session_state.current_step += 1
                st.query_params["step"] = WORKFLOW_STEPS[st.session_state.current_step]["id"]
                st.rerun()


if __name__ == "__main__":
    main()
