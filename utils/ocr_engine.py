# -*- coding: utf-8 -*-
"""
本地OCR引擎 - 基于 RapidOCR (ONNX 模型, 无需API, 数据不出院)
图片: RapidOCR 直接识别; PDF: 文本型直接抽取, 扫描型渲染为图片后 OCR
"""
import os
import tempfile
from typing import Any, Dict, List, Optional

_ENGINE = None


def is_pdf(path: str) -> bool:
    """判断文件是否为 PDF"""
    return str(path).lower().endswith(".pdf")


def get_engine():
    """懒加载RapidOCR引擎"""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def is_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_image(image_path: str) -> Dict[str, Any]:
    """
    识别单张图片, 返回结构化结果
    {
        "文本": "按行拼接的识别文本",
        "文本行": [{"文字": str, "置信度": float, "位置": [x0,y0,x1,y1]}, ...],
    }
    """
    if not is_available():
        return {"文本": "[RapidOCR未安装, 请执行 pip install rapidocr_onnxruntime]", "文本行": []}
    engine = get_engine()
    result, _ = engine(image_path)
    lines = []
    text_parts = []
    if result:
        for item in result:
            box = item[0]
            x0 = min(p[0] for p in box)
            y0 = min(p[1] for p in box)
            x1 = max(p[0] for p in box)
            y1 = max(p[1] for p in box)
            conf = float(item[2])
            text = item[1]
            lines.append({"文字": text, "置信度": round(conf, 2), "位置": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})
            text_parts.append(text)
    return {"文本": "\n".join(text_parts), "文本行": lines}


def ocr_batch(image_paths: List[str]) -> List[Dict[str, Any]]:
    """批量识别多张图片/PDF"""
    results = []
    for p in image_paths:
        info = {"文件名": os.path.basename(p), "路径": p}
        if is_pdf(p):
            info.update(_ocr_pdf(p))
        else:
            info.update(ocr_image(p))
        results.append(info)
    return results


def _pdf_text(path: str) -> str:
    """抽取文本型PDF的文字 (每页标注页码)"""
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz
    doc = fitz.open(path)
    parts = []
    for i, page in enumerate(doc, 1):
        txt = page.get_text().strip()
        if txt:
            parts.append(f"—— 第{i}页 ——\n{txt}")
    doc.close()
    return "\n".join(parts)


def _pdf_render_pages(path: str) -> List[Dict[str, Any]]:
    """将PDF每页渲染为图片并OCR, 返回与 ocr_batch 单条一致的结果列表"""
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz
    doc = fitz.open(path)
    out = []
    tmp_files = []
    try:
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(pix.tobytes("png"))
            tmp.close()
            tmp_files.append(tmp.name)
            r = ocr_image(tmp.name)
            out.append({
                "文件名": os.path.basename(path),
                "路径": path,
                "页码": i,
                "文本": f"—— 第{i}页 ——\n{r['文本']}" if r["文本"] else f"—— 第{i}页 ——（无文字）",
                "文本行": r["文本行"],
            })
    finally:
        for f in tmp_files:
            try:
                os.remove(f)
            except OSError:
                pass
        doc.close()
    return out


def _ocr_pdf(path: str) -> Dict[str, Any]:
    """识别PDF: 优先抽取文本(文本型PDF), 无文本则逐页渲染OCR(扫描件)"""
    text = ""
    err = ""
    try:
        text = _pdf_text(path)
    except Exception as e:
        text = ""
        err = str(e)
    if text and len(text.strip()) >= 4:
        return {"文本": text, "文本行": [], "来源": "PDF文本抽取"}
    pages = _pdf_render_pages(path)
    if not pages:
        return {"文本": f"[PDF无法解析: {err}]", "文本行": []}
    if len(pages) == 1:
        r = pages[0]
        r["来源"] = "PDF渲染OCR"
        return r
    # 多页合并, 文本行带页码前缀
    lines = []
    text_parts = []
    for pg in pages:
        text_parts.append(pg["文本"])
        for ln in pg["文本行"]:
            ln = dict(ln)
            ln["文字"] = f"[第{pg['页码']}页] {ln['文字']}"
            lines.append(ln)
    return {"文本": "\n".join(text_parts), "文本行": lines, "来源": "PDF渲染OCR"}
