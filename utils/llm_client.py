# -*- coding: utf-8 -*-
"""
LLM客户端 - 统一的大模型调用接口
支持 OpenAI / DeepSeek / 本地模型
"""
import os
import json
import base64
import httpx
from dotenv import load_dotenv

# 自动读取项目里的.env文件变量(固定项目根目录, 不依赖启动时cwd)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)

# 配置 - 可通过环境变量或直接修改
LLM_CONFIG = {
    "provider": "openai",  # openai / deepseek / local
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.getenv("LLM_MODEL", "gpt-4o"),
    "temperature": 0,
    "max_tokens": 16384,  # 输出上限: 技能结果为大段结构化JSON(如OCR一次含多份报告), 4096易截断导致JSON解析失败
    "seed": 42,  # 固定采样种子, 保证相同输入结果可复现
}


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    调用LLM API
    返回原始文本响应
    """
    api_key = LLM_CONFIG["api_key"]
    base_url = LLM_CONFIG["base_url"]
    model = LLM_CONFIG["model"]

    if not api_key:
        return _mock_response(system_prompt, user_prompt)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": LLM_CONFIG["temperature"],
        "max_tokens": LLM_CONFIG["max_tokens"],
        "seed": LLM_CONFIG.get("seed", 42),
    }

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[LLM调用失败] {str(e)}\n\n" + _mock_response(system_prompt, user_prompt)


def call_llm_stream(system_prompt: str, user_prompt: str, on_chunk=None, timeout: int = 180) -> str:
    """
    流式调用LLM API (SSE)
    on_chunk: 每收到一段增量文本时回调(text: str)
    返回拼接后的完整文本
    """
    api_key = LLM_CONFIG["api_key"]
    base_url = LLM_CONFIG["base_url"]
    model = LLM_CONFIG["model"]

    if not api_key:
        mock = _mock_response(system_prompt, user_prompt)
        if on_chunk:
            on_chunk(mock)
        return mock

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": LLM_CONFIG["temperature"],
        "max_tokens": LLM_CONFIG["max_tokens"],
        "seed": LLM_CONFIG.get("seed", 42),
        "stream": True,
    }

    parts: list = []
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        parts.append(delta)
                        if on_chunk:
                            on_chunk(delta)
        return "".join(parts)
    except Exception as e:
        fallback = f"[LLM调用失败] {str(e)}\n\n" + _mock_response(system_prompt, user_prompt)
        if on_chunk:
            on_chunk(fallback)
        return fallback


def call_llm_json(system_prompt: str, user_prompt: str, on_chunk=None) -> dict:
    """
    调用LLM并解析JSON响应
    on_chunk 提供时走流式调用(SSE), 每段增量文本会回调
    """
    if on_chunk:
        raw = call_llm_stream(system_prompt, user_prompt, on_chunk=on_chunk)
    else:
        raw = call_llm(system_prompt, user_prompt)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except json.JSONDecodeError:
        pass
    return {"raw_response": raw}


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".bmp": "image/bmp", ".webp": "image/webp", ".gif": "image/gif",
    }
    return mime_map.get(ext, "image/jpeg")


def call_llm_vision(system_prompt: str, user_text: str, images: list = None) -> str:
    """
    调用多模态大模型(OCR/看图) - 支持OpenAI兼容的vision接口
    images: [{"path": "本地图片路径"} 或 {"name": "文件名", "data": bytes}]
    返回原始文本响应
    """
    api_key = LLM_CONFIG["api_key"]
    base_url = LLM_CONFIG["base_url"]
    model = LLM_CONFIG["model"]
    images = images or []

    if not api_key:
        return _mock_response(system_prompt, f"{user_text}\n[附 {len(images)} 张图片待识别]")

    content = [{"type": "text", "text": user_text}]
    for img in images:
        if isinstance(img, dict) and "data" in img:
            b64 = base64.b64encode(img["data"]).decode()
            mime = _guess_mime(img.get("name", "image.jpg"))
        else:
            path = img.get("path") if isinstance(img, dict) else img
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = _guess_mime(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": LLM_CONFIG["temperature"],
        "max_tokens": LLM_CONFIG["max_tokens"],
        "seed": LLM_CONFIG.get("seed", 42),
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[LLM调用失败] {str(e)}\n\n" + _mock_response(system_prompt, user_text)


def call_llm_vision_stream(system_prompt: str, user_text: str, images: list = None, on_chunk=None, timeout: int = 180) -> str:
    """
    流式调用多模态大模型(OCR/看图) - SSE
    images: [{"path": "本地图片路径"} 或 {"name": "文件名", "data": bytes}]
    on_chunk: 每收到一段增量文本时回调(text: str)
    返回拼接后的完整文本
    """
    api_key = LLM_CONFIG["api_key"]
    base_url = LLM_CONFIG["base_url"]
    model = LLM_CONFIG["model"]
    images = images or []

    if not api_key:
        mock = _mock_response(system_prompt, f"{user_text}\n[附 {len(images)} 张图片待识别]")
        if on_chunk:
            on_chunk(mock)
        return mock

    content = [{"type": "text", "text": user_text}]
    for img in images:
        if isinstance(img, dict) and "data" in img:
            b64 = base64.b64encode(img["data"]).decode()
            mime = _guess_mime(img.get("name", "image.jpg"))
        else:
            path = img.get("path") if isinstance(img, dict) else img
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = _guess_mime(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": LLM_CONFIG["temperature"],
        "max_tokens": LLM_CONFIG["max_tokens"],
        "seed": LLM_CONFIG.get("seed", 42),
        "stream": True,
    }

    parts: list = []
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        parts.append(delta)
                        if on_chunk:
                            on_chunk(delta)
        return "".join(parts)
    except Exception as e:
        fallback = f"[LLM调用失败] {str(e)}\n\n" + _mock_response(system_prompt, user_text)
        if on_chunk:
            on_chunk(fallback)
        return fallback


def call_llm_vision_json(system_prompt: str, user_text: str, images: list = None, on_chunk=None) -> dict:
    """
    调用多模态大模型并解析JSON响应
    on_chunk 提供时走流式调用(SSE), 每段增量文本会回调
    """
    if on_chunk:
        raw = call_llm_vision_stream(system_prompt, user_text, images, on_chunk=on_chunk)
    else:
        raw = call_llm_vision(system_prompt, user_text, images)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except json.JSONDecodeError:
        pass
    return {"raw_response": raw}


def _mock_response(system_prompt: str, user_prompt: str) -> str:
    """Mock响应 - 未配置API时使用"""
    return (
        "[Mock模式] 当前未配置LLM API密钥。\n"
        "请设置环境变量 OPENAI_API_KEY 后重新运行。\n\n"
        f"系统提示词长度: {len(system_prompt)} 字\n"
        f"用户提示词长度: {len(user_prompt)} 字"
    )


def build_patient_context(patient_data: dict) -> str:
    """将患者数据构建为LLM可读的上下文文本 - 全量输出所有sections"""
    sections = []

    for key, value in patient_data.items():
        if not isinstance(value, dict) or not value:
            continue
        items = "\n".join(f"  {k}: {v}" for k, v in value.items())
        sections.append(f"【{key}】\n{items}")

    return "\n\n".join(sections)
