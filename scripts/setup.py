"""
Open WebUI 一键配置脚本
通过 API 自动配置：火山引擎模型、Seedream 图片生成工具、Skill、全局 Prompt
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

API_BASE = os.environ.get("OWUI_API_BASE", "http://localhost:8080")

def _csv(key, default):
    v = os.environ.get(key, "")
    return [x.strip() for x in v.split(",") if x.strip()] if v else default

ARK_CHAT_MODELS = _csv("OWUI_ARK_CHAT_MODELS", [
    "doubao-seed-2.0-code", "doubao-seed-2.0-pro",
    "doubao-seed-2.0-lite", "doubao-seed-2.0-mini",
    "minimax-m2.7", "glm-5.1", "kimi-k2.6",
    "deepseek-v4-pro", "deepseek-v4-flash",
])
ARK_VISION_MODELS = _csv("OWUI_ARK_VISION_MODELS", [
    "doubao-seed-2.0-code",
])
ARK_IMAGE_MODEL = os.environ.get("OWUI_ARK_IMAGE_MODEL", "doubao-seedream-5.0-lite")
ARK_EMBEDDING_MODEL = os.environ.get("OWUI_ARK_EMBEDDING_MODEL", "doubao-embedding-vision")

def _with_tool(mid):
    return mid not in (ARK_IMAGE_MODEL, ARK_EMBEDDING_MODEL)

def api(method, path, token=None, data=None):
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        print(f"  [ERROR] {method} {path} -> HTTP {e.code}: {detail}")
        return None
    except Exception as e:
        print(f"  [ERROR] {method} {path} -> {e}")
        return None

def wait_for_ready():
    print("等待 Open WebUI 启动...")
    for i in range(120):
        try:
            req = urllib.request.Request(f"{API_BASE}/api/v1/auths/signin", method="POST")
            req.add_header("Content-Type", "application/json")
            _ = urllib.request.urlopen(req, data=b'{}', timeout=5)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 422:
                return True
            time.sleep(2)
        except Exception:
            time.sleep(2)
    print("启动超时")
    return False

def login_or_signup():
    email = os.environ["OWUI_ADMIN_EMAIL"]
    password = os.environ["OWUI_ADMIN_PASSWORD"]

    r = api("POST", "/api/v1/auths/signin", data={"email": email, "password": password})
    if r and "token" in r:
        print(f"  登录成功: {r.get('name', email)}")
        return r["token"]

    print("  管理员账户不存在，正在注册...")
    r = api("POST", "/api/v1/auths/signup", data={
        "name": "admin", "email": email, "password": password,
        "profile_image_url": "", "role": "admin"
    })
    if r and "token" in r:
        print(f"  注册成功")
        return r["token"]

    # Try the signup body without optional fields
    r = api("POST", "/api/v1/auths/signup", data={"email": email, "password": password})
    if r and "token" in r:
        print(f"  注册成功 (minimal)")
        return r["token"]

    print("  [ERROR] 无法登录或注册")
    return None

def configure_openai(token):
    print("配置火山引擎模型连接...")
    ark_key = os.environ.get("OWUI_ARK_API_KEY", "")

    payload = {
        "ENABLE_OPENAI_API": True,
        "OPENAI_API_BASE_URLS": [
            "https://ark.cn-beijing.volces.com/api/plan/v3",
        ],
        "OPENAI_API_KEYS": [ark_key],
        "OPENAI_API_CONFIGS": {
            "0": {
                "url": "https://ark.cn-beijing.volces.com/api/plan/v3",
                "api_key": ark_key,
                "title": "火山引擎",
                "model_ids": _build_model_ids(),
            },
        }
    }
    r = api("POST", "/openai/config/update", token=token, data=payload)
    if r is not None:
        print("  OpenAI 连接配置完成")
    else:
        print("  [WARN] OpenAI 配置失败")

def configure_image_gen(token):
    print("配置图片生成引擎...")
    ark_key = os.environ.get("OWUI_ARK_API_KEY", "")

    payload = {
        "ENABLE_IMAGE_GENERATION": True,
        "ENABLE_IMAGE_PROMPT_GENERATION": False,
        "IMAGE_GENERATION_ENGINE": "openai",
        "IMAGE_GENERATION_MODEL": ARK_IMAGE_MODEL,
        "IMAGE_SIZE": "1024x1024",
        "IMAGE_STEPS": 50,
        "IMAGES_OPENAI_API_BASE_URL": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "IMAGES_OPENAI_API_KEY": ark_key,
        "IMAGES_OPENAI_API_PARAMS": {
            "size": "2k",
            "response_format": "url",
            "watermark": False,
            "output_format": "jpeg"
        },
        "ENABLE_IMAGE_EDIT": True,
        "IMAGE_EDIT_ENGINE": "openai",
        "IMAGE_EDIT_MODEL": ARK_IMAGE_MODEL,
        "IMAGES_EDIT_OPENAI_API_BASE_URL": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "IMAGES_EDIT_OPENAI_API_KEY": ark_key,
    }

    # Try the images config endpoint
    endpoints = [
        "POST /api/v1/images/config/update",
        "POST /api/v1/images/config",
    ]
    for method, ep in [("POST", "/api/v1/images/config/update"),
                        ("POST", "/api/v1/configs")]:
        r = api("POST", ep, token=token, data=payload)
        if r is not None:
            print(f"  图片生成配置完成")
            return

    print("  [WARN] 图片生成配置可能需要手动设置")

def create_tool(token):
    print("创建 Seedream 工具...")

    tool_path = os.path.join(os.path.dirname(__file__), "..", "tools", "seedream_image_generation.py")
    with open(tool_path) as f:
        content = f.read()

    ark_key = os.environ.get("OWUI_ARK_API_KEY", "")

    payload = {
        "id": "seedream_image_generation",
        "name": "Seedream 图片生成",
        "content": content,
        "meta": {
            "description": "豆包 Seedream AI 图片生成，支持文生图、图生图、连贯组图、联网搜索",
            "manifest": {}
        }
    }
    r = api("POST", "/api/v1/tools/create", token=token, data=payload)
    if r and "id" in r:
        print(f"  工具创建成功: {r['id']}")

        valve_payload = {
            "api_base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "model": ARK_IMAGE_MODEL,
            "api_key": ark_key,
            "prompt_optimization": True,
            "watermark": True,
            "output_format": "jpeg",
            "timeout_seconds": 120,
        }
        vr = api("POST", f"/api/v1/tools/id/{r['id']}/valves/update", token=token, data=valve_payload)
        if vr is not None:
            print("  工具 Valves 配置完成")
    elif r is not None and "id" not in r:
        print(f"  工具响应: {json.dumps(r, ensure_ascii=False)[:200]}")
    else:
        # Maybe it already exists, try update
        ur = api("POST", f"/api/v1/tools/id/seedream_image_generation/update", token=token, data=payload)
        if ur and "id" in ur:
            print(f"  工具已存在，已更新")
        else:
            print("  [WARN] 工具创建失败")

def configure_models(token):
    print("配置模型元数据（toolIds、capabilities）...")

    global_prompt = (
        "当用户上传了图片，而你是非视觉模型（不支持直接看图片）时：\n"
        "1. 消息中可能会包含 <file type=\"image\" uuid=\"xxx\"/> 或 <attached_files> 标签\n"
        "2. 从这些标签中提取 file uuid\n"
        "3. 在调用 generate_image 工具时，将 uuid 传入 reference_images 参数（JSON 数组字符串格式）\n"
        "4. 不要尝试描述图片内容，直接调用工具进行图生图编辑\n"
    )

    # 先尝试 API 方式设置全局 Prompt
    r = api("POST", "/api/v1/configs/models", token=token, data={
        "DEFAULT_MODELS": "",
        "DEFAULT_PINNED_MODELS": "",
        "MODEL_ORDER_LIST": [],
    })
    if r is not None:
        print("  全局配置完成")
    else:
        print("  [WARN] 全局配置接口调用失败")

    # 通过 docker exec 在容器内写库（避免主机-容器并发导致 database is locked）
    script = r'''
import json, time

chat_ids = _CHAT_IDS_
vision_ids = _VISION_IDS_
image_model = _IMAGE_MODEL_
embedding_model = _EMBEDDING_MODEL_

global_prompt = _GLOBAL_PROMPT_

import sqlite3
conn = sqlite3.connect("/app/backend/data/webui.db")
cur = conn.cursor()

for m_id in chat_ids:
    vision = m_id in vision_ids
    meta = json.dumps({
        "description": f"火山引擎 {m_id}",
        "capabilities": {"vision": vision},
        "toolIds": ["seedream_image_generation"] if True else [],
    }, ensure_ascii=False)
    params = json.dumps({"system_prompt": global_prompt} if not vision else {}, ensure_ascii=False)

    cur.execute("SELECT id FROM model WHERE id = ?", (m_id,))
    exists = cur.fetchone()
    if exists:
        cur.execute("UPDATE model SET meta = ?, params = ?, is_active = 1 WHERE id = ?", (meta, params, m_id))
    else:
        cur.execute(
            "INSERT INTO model (id, user_id, name, meta, params, is_active, created_at, updated_at) "
            "VALUES (?, '', ?, ?, ?, 1, ?, ?)",
            (m_id, m_id, meta, params, int(time.time()), int(time.time())),
        )
    print(f"  {m_id}: vision={vision}")

for extra_id, label in [(image_model, "ImageGen"), (embedding_model, "Embedding")]:
    if extra_id and extra_id not in chat_ids:
        cur.execute("SELECT id FROM model WHERE id = ?", (extra_id,))
        if not cur.fetchone():
            meta = json.dumps({"description": f"火山引擎 {extra_id}", "capabilities": {}}, ensure_ascii=False)
            cur.execute(
                "INSERT INTO model (id, user_id, name, meta, params, is_active, created_at, updated_at) "
                "VALUES (?, '', ?, ?, '{}', 1, ?, ?)",
                (extra_id, extra_id, meta, int(time.time()), int(time.time())),
            )
            print(f"  {extra_id}: {label}")

all_ids = list(chat_ids)
for extra_id in [image_model, embedding_model]:
    if extra_id and extra_id not in all_ids:
        all_ids.append(extra_id)
for m_id in all_ids:
    cur.execute("SELECT id FROM access_grant WHERE resource_type='model' AND resource_id=?", (m_id,))
    if not cur.fetchone():
        import uuid
        cur.execute(
            "INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at) "
            "VALUES (?, 'model', ?, 'user', '*', 'read', ?)",
            (str(uuid.uuid4()), m_id, int(time.time())),
        )

conn.commit()
conn.close()
print("  模型配置完成")
'''

    import subprocess
    script = (
        script
        .replace("_CHAT_IDS_", json.dumps(ARK_CHAT_MODELS))
        .replace("_VISION_IDS_", json.dumps(ARK_VISION_MODELS))
        .replace("_IMAGE_MODEL_", json.dumps(ARK_IMAGE_MODEL))
        .replace("_EMBEDDING_MODEL_", json.dumps(ARK_EMBEDDING_MODEL))
        .replace("_GLOBAL_PROMPT_", json.dumps(global_prompt))
    )

    result = subprocess.run(
        ["docker", "exec", "-i", "open-webui", "python3"],
        input=script,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            print(line)
    else:
        print(f"  [ERROR] docker exec 写入模型数据失败:")
        print(f"    stdout: {result.stdout[:500]}")
        print(f"    stderr: {result.stderr[:500]}")
        # 回退：用户需要手动重启容器
        print("  [INFO] 请尝试: docker restart open-webui")

def create_skill(token):
    print("创建 Seedream Skill...")

    skill_path = os.path.join(os.path.dirname(__file__), "..", "skills", "byted-ark-seedream-skill", "SKILL.md")
    with open(skill_path) as f:
        content = f.read()

    payload = {
        "id": "seedream-image-generation",
        "name": "Seedream 图片生成",
        "description": "豆包 Seedream AI 图片生成 Skill - 火山方舟 Agent Plan 专属版本",
        "content": content,
        "meta": {"tags": ["image-generation", "seedream", "volcengine"]},
        "is_active": True,
    }
    r = api("POST", "/api/v1/skills/create", token=token, data=payload)
    if r and "id" in r:
        print(f"  Skill 创建成功: {r['id']}")
    elif r is not None:
        print(f"  Skill 响应: {json.dumps(r, ensure_ascii=False)[:200]}")
    else:
        ur = api("POST", f"/api/v1/skills/id/seedream-image-generation/update", token=token, data=payload)
        if ur and "id" in ur:
            print(f"  Skill 已存在，已更新")
        else:
            print("  [WARN] Skill 创建失败")

def _build_model_ids():
    ids = list(ARK_CHAT_MODELS)
    for extra in [ARK_EMBEDDING_MODEL, ARK_IMAGE_MODEL]:
        if extra and extra not in ids:
            ids.append(extra)
    return ids

CONFIG_TEMPLATE = {
    "version": 0,
    "ui": {"enable_signup": False},
    "openai": {
        "enable": True,
        "api_base_urls": [
            "https://ark.cn-beijing.volces.com/api/plan/v3",
        ],
        "api_keys": ["__ARK_KEY__"],
        "api_configs": {
            "0": {
                "enable": True, "tags": [], "prefix_id": "",
                "model_ids": _build_model_ids(),
                "connection_type": "external", "auth_type": "bearer",
            },
        }
    },
    "image_generation": {
        "enable": True, "prompt": {"enable": False},
        "engine": "openai", "model": ARK_IMAGE_MODEL,
        "size": "1024x1024", "steps": 50,
        "openai": {
            "api_base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "api_key": "__ARK_KEY__", "api_version": "",
            "params": {"size": "2k", "response_format": "url", "watermark": False, "output_format": "jpeg"},
        },
        "automatic1111": {"base_url": "", "api_auth": "", "api_params": {}},
        "comfyui": {"base_url": "", "api_key": "", "workflow": "", "nodes": []},
        "gemini": {"api_base_url": "", "api_key": "", "endpoint_method": ""},
    },
    "images": {
        "edit": {
            "enable": True, "engine": "openai", "model": ARK_IMAGE_MODEL,
            "size": "",
            "openai": {
                "api_base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
                "api_key": "__ARK_KEY__", "api_version": "",
            },
            "gemini": {"api_base_url": "", "api_key": ""},
            "comfyui": {"base_url": "", "api_key": "", "workflow": "", "nodes": []},
        }
    },
    "ollama": {"enable": False, "base_urls": ["http://localhost:11434"], "api_configs": {"0": {}}},
    "direct": {"enable": True},
    "models": {"base_models_cache": True},
}

def import_full_config(token):
    print("导入完整配置...")
    ark_key = os.environ.get("OWUI_ARK_API_KEY", "")

    config = json.loads(json.dumps(CONFIG_TEMPLATE))
    config["openai"]["api_keys"] = [ark_key]
    config["image_generation"]["openai"]["api_key"] = ark_key
    config["images"]["edit"]["openai"]["api_key"] = ark_key

    r = api("POST", "/api/v1/configs/import", token=token, data={"config": config})
    if r is not None:
        print("  配置导入成功")
        return True
    else:
        print("  [INFO] 配置导入接口不可用，将通过逐个 API 配置")
        return False

def main():
    if not wait_for_ready():
        sys.exit(1)

    token = login_or_signup()
    if not token:
        sys.exit(1)

    print()
    config_ok = import_full_config(token)
    print()

    if not config_ok:
        configure_openai(token)
        print()
        configure_image_gen(token)
        print()

    create_tool(token)
    print()

    configure_models(token)
    print()

    create_skill(token)
    print()

    print("=" * 50)
    print("配置完成！")
    print(f"  访问地址: {API_BASE}")
    print(f"  管理邮箱: {os.environ.get('OWUI_ADMIN_EMAIL', '')}")
    print(f"  登录后可用模型:")
    for m_id in ARK_CHAT_MODELS:
        tags = []
        if m_id in ARK_VISION_MODELS:
            tags.append("视觉")
        if _with_tool(m_id):
            tags.append("工具")
        tag = f" ({', '.join(tags)})" if tags else ""
        print(f"    - {m_id}{tag}")
    specials = []
    if ARK_IMAGE_MODEL not in ARK_CHAT_MODELS:
        specials.append(f"{ARK_IMAGE_MODEL} (图片生成)")
    if ARK_EMBEDDING_MODEL not in ARK_CHAT_MODELS:
        specials.append(f"{ARK_EMBEDDING_MODEL} (Embedding)")
    for s in specials:
        print(f"    - {s}")
    print("  Seedream 图片生成工具已配置完毕，可直接对话使用")
    print("=" * 50)

if __name__ == "__main__":
    missing = [v for v in ["OWUI_ADMIN_EMAIL", "OWUI_ADMIN_PASSWORD", "OWUI_ARK_API_KEY"] if v not in os.environ]
    if missing:
        print(f"缺少环境变量: {', '.join(missing)}")
        print("请确保在 .env 中设置了: OWUI_ADMIN_EMAIL, OWUI_ADMIN_PASSWORD, OWUI_ARK_API_KEY")
        sys.exit(1)
    main()
