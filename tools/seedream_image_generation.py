"""
title: Seedream 图片生成
author: starry
version: 0.3.0
required_open_webui_version: 0.3.17
description: 豆包 Seedream AI 图片生成，支持文生图、图生图（输入图片编辑）、连贯组图、联网搜索
"""

from pydantic import BaseModel
from typing import Optional, Callable, Any
import requests
import json
import time
import re
import base64
import mimetypes
import logging
import os
import uuid

log = logging.getLogger(__name__)


class Tools:
    class Valves(BaseModel):
        api_base_url: str = "https://ark.cn-beijing.volces.com/api/plan/v3"
        model: str = "doubao-seedream-5.0-lite"
        api_key: str = ""
        prompt_optimization: bool = True
        watermark: bool = True
        output_format: str = "jpeg"
        timeout_seconds: int = 120
        pass

    def __init__(self):
        self.valves = self.Valves()

    STYLE_PRESETS = {
        "电影风": "好莱坞大片质感, 电影级光影, 杜比视界, 宽画幅, 极致细节",
        "二次元": "新海诚风格, 日系动漫, 精美原画, 高饱和度, 清澈光影",
        "插画风": "扁平插画风格, 莫兰迪色系, 简洁线条, 矢量感, 艺术设计",
        "写实风": "专业摄影, 索尼A7R5, f/1.8大光圈, RAW格式, 超写实, 细节锐利",
        "国潮风": "国潮插画风格, 中国传统元素, 金色点缀, 工笔画质感, 精致线条",
        "赛博朋克": "赛博朋克2077风格, 霓虹灯光, 高科技低生活, 雨天, 未来感",
        "水彩风": "水彩画风格, 透明质感, 晕染效果, 艺术纸张纹理, 清新",
        "3D渲染": "Octane渲染, 3D立体, 光线追踪, 次表面散射, PBR材质, 极致写实",
        "暗黑风": "暗黑美学, 高对比度, 暗色调, 神秘氛围, 电影质感",
        "治愈系": "治愈系风格, 温暖明亮, 可爱, 吉卜力质感, 柔和光线",
    }

    STYLE_KEYWORDS = {
        "电影风": ["电影", "大片", "cinematic", "好莱坞"],
        "二次元": ["二次元", "动漫", "anime", "漫画"],
        "插画风": ["插画", "手绘", "illustration", "扁平"],
        "写实风": ["照片", "写实", "photograph", "摄影"],
        "国潮风": ["国潮", "国风", "中国风", "传统"],
        "赛博朋克": ["赛博", "cyberpunk", "朋克", "霓虹"],
        "水彩风": ["水彩", "watercolor"],
        "3D渲染": ["3d", "oc", "渲染", "octane", "三维"],
        "暗黑风": ["暗黑", "哥特", "dark", "黑暗"],
        "治愈系": ["治愈", "温馨", "可爱", "cute", "温暖"],
    }

    BASE_ENHANCEMENTS = "电影质感, 高分辨率, 细节丰富, 专业摄影, 构图精美, 色彩协调"

    UUID_PATTERN = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def _detect_style(self, prompt: str) -> Optional[str]:
        lower = prompt.lower()
        for style, keywords in self.STYLE_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return style
        return None

    def _optimize_prompt(
        self, prompt: str, enable: bool = True, is_sequential: bool = False
    ) -> dict:
        if not enable:
            return {
                "original": prompt,
                "optimized": prompt,
                "style": None,
                "enabled": False,
                "mode": "sequential" if is_sequential else "single",
                "applied": [],
            }

        detected_style = self._detect_style(prompt)
        optimized = prompt
        applied = []

        if is_sequential:
            optimized += ", 统一画风, 相同角色, 系列插画, 风格一致, 色彩协调"
            applied.append("连贯图：统一风格约束")
            if detected_style:
                optimized += f", {self.STYLE_PRESETS[detected_style]}"
                applied.append(f"风格: {detected_style}")
        else:
            optimized += f", {self.BASE_ENHANCEMENTS}"
            applied.append("基础画质增强")
            if detected_style:
                optimized += f", {self.STYLE_PRESETS[detected_style]}"
                applied.append(f"风格: {detected_style}")
            else:
                optimized += ", 柔和自然光线, 构图平衡, 主体突出"
                applied.append("通用光影构图")

        return {
            "original": prompt,
            "optimized": optimized,
            "style": detected_style,
            "enabled": True,
            "mode": "sequential" if is_sequential else "single",
            "applied": applied,
        }

    def _resolve_to_base64(self, ref: str, request: Any = None) -> Optional[str]:
        try:
            if ref.startswith("data:image/"):
                return ref

            if not isinstance(ref, str) or not ref.strip():
                return None

            ref = ref.strip()

            api_base = "http://localhost:8080"
            headers = {}
            auth_token = None

            if request is not None:
                try:
                    auth_header = request.headers.get("authorization", "")
                    if auth_header:
                        headers["Authorization"] = auth_header
                        auth_token = auth_header
                except Exception:
                    pass

            file_uuid = None

            if self.UUID_PATTERN.match(ref):
                file_uuid = ref
            elif "/api/v1/files/" in ref:
                parts = ref.split("/api/v1/files/")
                if len(parts) > 1:
                    candidate = parts[1].split("/")[0].split("?")[0]
                    if self.UUID_PATTERN.match(candidate):
                        file_uuid = candidate

            if file_uuid:
                try:
                    import os as _os
                    data_dir = _os.environ.get("DATA_DIR", "/app/backend/data")
                    db_path = _os.path.join(data_dir, "webui.db")
                    conn = __import__("sqlite3").connect(db_path)
                    cur = conn.cursor()
                    cur.execute("SELECT path, meta FROM file WHERE id = ?", (file_uuid,))
                    row = cur.fetchone()
                    conn.close()
                    if row and row[0] and _os.path.isfile(row[0]):
                        with open(row[0], "rb") as f:
                            raw = f.read()
                        meta = __import__("json").loads(row[1]) if row[1] else {}
                        ct = meta.get("content_type", "image/jpeg")
                        b64 = base64.b64encode(raw).decode("utf-8")
                        log.info(f"Resolved {file_uuid} via direct filesystem read")
                        return f"data:{ct};base64,{b64}"
                except Exception as e:
                    log.warning(f"Direct file read for {file_uuid} failed: {e}")

                fetch_url = f"{api_base}/api/v1/files/{file_uuid}/content"
                resp = requests.get(fetch_url, headers=headers, timeout=30)
                if resp.status_code == 401 and auth_token is None:
                    log.warning(f"File {file_uuid} needs auth but no token available")
                    return None
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "image/jpeg")
                    b64 = base64.b64encode(resp.content).decode("utf-8")
                    return f"data:{ct};base64,{b64}"

                log.warning(f"Failed to fetch file {file_uuid}: HTTP {resp.status_code}")
                return None

            if ref.startswith("http://") or ref.startswith("https://"):
                resp = requests.get(ref, headers=headers, timeout=30)
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "image/jpeg")
                    b64 = base64.b64encode(resp.content).decode("utf-8")
                    return f"data:{ct};base64,{b64}"
                log.warning(f"Failed to fetch URL {ref}: HTTP {resp.status_code}")
                return None

            return ref
        except Exception as e:
            log.warning(f"Error resolving reference '{ref}': {e}")
            return None

    async def generate_image(
        self,
        prompt: str,
        mode: str = "text-to-image",
        size: str = "2K",
        sequential: bool = False,
        count: int = 4,
        reference_images: Optional[str] = None,
        reference_strength: float = 0.7,
        enable_web_search: bool = False,
        optimize: bool = True,
        __event_emitter__: Callable[[dict], Any] = None,
        __request__: Any = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """
        生成图片。
        使用豆包 Seedream AI 模型生成图片。
        支持：
        - 文生图（text-to-image）：仅文字描述即可生成
        - 图生图（image-to-image）：参考已有图片生成新图片，如去背景、换天空、改风格
        - 连贯组图（sequential）：生成一组风格一致的系列图片
        - 联网搜索：结合实时信息生成图片

        Args:
            prompt: 图片描述提示词，越详细效果越好
            mode: 生成模式，text-to-image（文生图）或 image-to-image（图生图/图片编辑，需提供 reference_images）
            size: 图片分辨率，支持 2K 或 3K
            sequential: 是否生成一组连贯图片（风格保持一致），设为 true 时 prompt 需包含组图语义
            count: 连贯图数量，sequential=true 时有效，1~15 张
            reference_images: 参考图 URL 列表（JSON 数组字符串），支持 Open WebUI 内部文件 UUID、HTTP(S) URL 或 data URI
            reference_strength: 参考图影响强度，0~1 之间，默认 0.7
            enable_web_search: 是否开启联网搜索
            optimize: 是否自动优化提示词
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "🎨 正在生成图片...", "done": False},
                }
            )

        api_key = self.valves.api_key
        if not api_key:
            return (
                "❌ 未配置 API Key。请在 Tools > Valves 中设置 api_key。"
                "（使用火山方舟 Agent Plan 专属 Key，以 ark- 开头）"
            )

        final_prompt = prompt
        style_info = None
        if optimize and self.valves.prompt_optimization:
            result = self._optimize_prompt(prompt, True, sequential)
            final_prompt = result["optimized"]
            style_info = result["style"]
            if result["applied"]:
                applied_text = ", ".join(result["applied"])
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": f"✨ 提示词优化: {applied_text}",
                                "done": False,
                            },
                        }
                    )

        body = {
            "model": self.valves.model,
            "prompt": final_prompt,
            "size": size.lower() if size in ["2K", "3K", "2k", "3k"] else size,
            "response_format": "url",
            "output_format": self.valves.output_format,
            "watermark": self.valves.watermark,
            "stream": False,
        }

        if sequential:
            body["sequential_image_generation"] = "auto"

        if enable_web_search:
            body["tools"] = [{"type": "web_search"}]

        if mode == "image-to-image" and reference_images:
            try:
                refs = json.loads(reference_images)
                if isinstance(refs, list) and len(refs) > 0:
                    resolved_refs = []
                    for ref in refs:
                        if isinstance(ref, str):
                            b64 = self._resolve_to_base64(ref, request=__request__)
                            if b64:
                                resolved_refs.append(b64)
                            else:
                                log.warning(
                                    f"Cannot resolve reference, keeping original: {ref[:60]}"
                                )
                                resolved_refs.append(ref)

                    if resolved_refs:
                        body["image"] = (
                            resolved_refs[0]
                            if len(resolved_refs) == 1
                            else resolved_refs
                        )
                        body["reference_strength"] = max(
                            0.0, min(1.0, float(reference_strength))
                        )
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                return (
                    f"❌ reference_images 格式无效: {e}"
                    "（必须是 JSON 数组字符串，如 '[\"uuid\"]'）"
                )

        api_url = f"{self.valves.api_base_url}/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=body,
                timeout=self.valves.timeout_seconds,
            )

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_detail = json.dumps(response.json(), ensure_ascii=False)
                except Exception:
                    pass
                return f"❌ API 调用失败 (HTTP {response.status_code}): {error_detail}"

            data = response.json()
            output_images = data.get("data", [])

            if not output_images:
                return "❌ API 返回成功但未包含图片数据"

            result_lines = []
            result_lines.append("🎉 图片生成成功！")
            if style_info:
                result_lines.append(f"🎨 检测风格: {style_info}")
            result_lines.append(f"🖼️  共 {len(output_images)} 张")
            result_lines.append("")

            for i, img in enumerate(output_images):
                url = img.get("url", "")
                if url:
                    result_lines.append(f"### 第 {i+1} 张")
                    result_lines.append(f"![生成图片]({url})")
                    result_lines.append(f"[打开原图]({url})")
                    result_lines.append("")

            result_lines.append(
                f"🤖 模型: {self.valves.model}  |  📐 尺寸: {size}"
            )

            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "✅ 图片生成完成", "done": True},
                    }
                )

            return "\n".join(result_lines)

        except requests.exceptions.Timeout:
            return f"❌ API 请求超时（{self.valves.timeout_seconds}s）"
        except requests.exceptions.ConnectionError:
            return "❌ 网络连接失败，请检查网络和 API 地址"
        except Exception as e:
            return f"❌ 生成失败: {str(e)}"
