# -*- coding: utf-8 -*-
"""
临床指南链接 - 指南名/文件名 → 可点击 PDF 链接映射
链接指向: https://io.cares-copilot.com/caca-pdfs/qilu/<文件名>.pdf
前端"参考依据(指南)"卡片据此把来源文本中的指南名渲染为可点击链接。
"""
import html
import re
import urllib.parse

MINIO_BASE = "https://io.cares-copilot.com/caca-pdfs"

# 文件名(不含 .pdf) → 匹配关键词(含别名)
# 匹配时取"来源"文本中包含的关键词, 命中即替换为对应PDF链接
_GUIDELINE_ALIASES = [
    # (pdf文件名, [匹配关键词])
    ("2025-american-thyroid-associati", [
        "2025-american-thyroid-associati",
        "american-thyroid-associati",
    ]),
    ("2025CSCO滤泡上皮来源甲", [
        "2025CSCO滤泡上皮来源甲",
        "CSCO滤泡上皮来源甲",
        "滤泡上皮来源甲状腺癌CSCO",
        "滤泡上皮来源甲状腺癌诊疗指南",
        "滤泡上皮来源甲状腺癌",
    ]),
    ("2025甲状腺癌ATA指南", [
        "2025甲状腺癌ATA指南",
        "甲状腺癌ATA指南",
        "ATA指南",
        "ATA 2025 DTC",
        "ATA 2025",
    ]),
    ("CSCO头颈肿瘤指南", [
        "CSCO头颈肿瘤指南",
        "CSCO头颈部肿瘤诊疗指南",
        "CSCO头颈部肿瘤",
        "CSCO口咽癌指南",
        "CSCO口咽癌诊疗要点",
        "CSCO口咽癌",
        "口咽癌指南",
        "口咽癌诊疗要点",
        "口咽癌CSCO",
        "口咽癌诊疗",
    ]),
    ("NCCN头颈肿瘤指南", [
        "NCCN头颈肿瘤指南",
        "NCCN头颈部肿瘤",
    ]),
    ("下咽与食管多原发癌筛查诊治中国专家共识", [
        "下咽与食管多原发癌筛查诊治中国专家共识",
    ]),
    ("下咽癌外科手术及综合治疗专家共识", [
        "下咽癌外科手术及综合治疗专家共识",
    ]),
    ("原发灶不明的颈部转移性鳞状细胞癌诊治专家", [
        "原发灶不明的颈部转移性鳞状细胞癌",
    ]),
    ("咽喉内镜专家共识", [
        "咽喉内镜专家共识",
        "咽喉内镜检查专家共识",
    ]),
    ("喉癌外科手术及综合治疗专家共识", [
        "喉癌外科手术及综合治疗专家共识",
    ]),
    ("复发头颈鳞癌ASCO指南", [
        "复发头颈鳞癌ASCO指南",
        "复发头颈鳞癌",
    ]),
    ("头颈原发鳞癌ASCO指南", [
        "头颈原发鳞癌ASCO指南",
        "头颈原发鳞癌",
    ]),
    ("甲状腺癌ASCO", [
        "甲状腺癌ASCO",
        "ASCO甲状腺癌",
        "ASCO 2026",
        "甲状腺癌系统治疗指南",
    ]),
    ("甲状腺癌CSCO指南", [
        "甲状腺癌CSCO指南",
        "CSCO甲状腺癌",
    ]),
    ("甲状腺癌NCCN指南", [
        "甲状腺癌NCCN指南",
        "NCCN甲状腺癌",
        "NCCN 1.2025",
        "NCCN Guidelines Insights",
    ]),
    ("颈段食管癌诊疗专家共识（2026版）", [
        "颈段食管癌诊疗专家共识（2026版）",
        "颈段食管癌诊疗专家共识",
    ]),
]


def _pdf_url(filename: str) -> str:
    """拼成 https://io.cares-copilot.com/caca-pdfs/qilu/<文件名>.pdf 链接(文件名URL编码)"""
    encoded = urllib.parse.quote(filename, safe="")
    return f"{MINIO_BASE}/qilu/{encoded}.pdf"


def find_guideline_pdf(source_text: str) -> tuple:
    """
    在来源文本中匹配指南名
    返回: (pdf文件名, 匹配到的指南名) 或 (None, None)
    """
    if not source_text:
        return None, None
    text = source_text
    for filename, aliases in _GUIDELINE_ALIASES:
        for alias in aliases:
            if alias in text:
                return filename, alias
    return None, None


def add_guideline_links(source_text: str) -> str:
    """
    把来源文本中匹配到的指南名替换为可点击链接
    - 优先把完整的 《指南名》 书名号整体作为链接文本
    - 无书名号时回退为只链接指南名
    - 非链接部分做 HTML 转义(安全), 仅保留 <a> 标签
    未匹配时原样返回(已转义)
    """
    if not source_text:
        return ""

    def _link(alias: str) -> str:
        filename, _ = find_guideline_pdf(alias)
        if not filename:
            return None
        url = _pdf_url(filename)
        return f'<a href="{url}" target="_blank" rel="noopener">{html.escape(alias)}</a>'

    escaped = html.escape(source_text, quote=False)

    def _repl_braced(m):
        inner = m.group(1)
        link = _link(inner)
        if link:
            return f"《{link}》"
        return m.group(0)

    out = re.sub(r"《([^》]+)》", _repl_braced, escaped)
    if out != escaped:
        return out

    # 无书名号: 直接替换首次匹配到的指南名
    filename, alias = find_guideline_pdf(escaped)
    if not filename:
        return escaped
    url = _pdf_url(filename)
    linked = f'<a href="{url}" target="_blank" rel="noopener">{html.escape(alias)}</a>'
    return escaped.replace(html.escape(alias), linked, 1)


def guideline_links_sidebar() -> list:
    """返回全部指南链接 [(书名, url)], 供侧边栏/列表页展示"""
    return [
        (name, _pdf_url(name))
        for name, _ in _GUIDELINE_ALIASES
    ]
