# Open WebUI + 火山引擎 Seedream 图片生成

基于 [Open WebUI](https://github.com/open-webui/open-webui) 搭建的 AI 对话平台，集成火山方舟 [Seedream](https://www.volcengine.com/docs/82379/1541523) 图片生成能力，支持非视觉模型（如 DeepSeek）通过工具调用实现图生图编辑。

## 特性

- 🎨 **文生图**：文字描述直接生成图片
- 🖼️ **图生图**：上传图片后编辑（去背景、换天空、改风格等）
- 🔗 **连贯组图**：生成一组风格一致的系列图片
- 🔍 **联网搜索**：结合实时信息生成图片
- 🤖 **非视觉模型支持**：DeepSeek 等纯文本模型也能调用图片工具

## 已集成的模型

| 模型 | 类型 | 视觉能力 | 工具调用 |
|------|------|----------|----------|
| `deepseek-v4-pro` | 对话 | ❌ | ✅ |
| `deepseek-v4-flash` | 对话 | ❌ | ✅ |
| `doubao-seed-2.0-pro` | 对话 | ❌ | ✅ |
| `doubao-seed-2.0-lite` | 对话 | ❌ | ✅ |
| `doubao-seed-2.0-mini` | 对话 | ❌ | ✅ |
| `doubao-seed-2.0-code` | 对话 | ✅ | ✅ |
| `minimax-m2.7` | 对话 | ❌ | ✅ |
| `glm-5.1` | 对话 | ❌ | ✅ |
| `kimi-k2.6` | 对话 | ❌ | ✅ |
| `doubao-embedding-vision` | Embedding | ✅ | ❌ |
| `doubao-seedream-5.0-lite` | 图片生成 | - | - |

## 前提条件

1. 已开通 [火山方舟 Agent Plan](https://www.volcengine.com/docs/82379/2375486)
2. 已获取 Agent Plan API Key（以 `ark-` 开头）
3. 已安装 Docker 和 Docker Compose
4. Python 3（用于执行自动配置脚本）

## 一键部署

```bash
# 克隆本项目
git clone <your-repo-url>
cd open-webui

# 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填入：
#   - WEBUI_SECRET_KEY: 任意随机字符串
#   - OWUI_ADMIN_EMAIL: 管理员邮箱
#   - OWUI_ADMIN_PASSWORD: 管理员密码
#   - OWUI_ARK_API_KEY: 火山方舟 API Key（以 ark- 开头）

# 首次部署（自动创建数据目录 ~/open-webui/data）
bash start.sh

# 后续启动（已有数据，跳过自动配置）
bash start.sh

# 强制重置（清空所有数据重新配置）
bash start.sh --reset
```

启动后访问 `http://localhost:8081`，使用设置的邮箱和密码登录即可使用。

> **数据目录**：默认 `~/open-webui/data`，可通过 `.env` 中的 `OWUI_DATA_DIR` 修改。
>
> **已有数据**：检测到 `webui.db` 已存在时跳过自动配置，直接启动服务。
>
> **--reset**：清空数据目录并重新执行完整自动配置。

## 文件结构

```
├── start.sh                           # 一键部署脚本
├── docker-compose.yml                 # Docker Compose 配置
├── .env.example                       # 环境变量模板
├── README.md                          # 本文档
├── scripts/
│   ├── setup.py                       # 自动配置脚本（通过 API 配置模型、工具、全局 Prompt）
│   └── middleware.py                  # 打过 patch 的 middleware，启动时替换容器原版
├── tools/
│   └── seedream_image_generation.py   # Seedream 图片生成 Tool
├── skills/
│   └── byted-ark-seedream-skill/      # Agent Plan Skill 文件
│       ├── SKILL.md
│       ├── package.json
│       ├── references/
│       │   ├── CONFIG.md
│       │   ├── DEVELOPER.md
│       │   ├── EXAMPLES.md
│       │   └── INSTALL.md
│       └── scripts/
│           └── generate.js
```

## 手动配置

如果需要手动配置，按以下步骤操作：

### 1. 启动 Open WebUI

```bash
docker compose up -d
```

访问 `http://localhost:8080`，注册管理员账号。

### 2. 配置火山方舟 API

登录 Open WebUI → **管理员面板** → **设置** → **外部连接**：
- **OpenAI API**: 启用
- **API URL**: `https://ark.cn-beijing.volces.com/api/plan/v3`
- **API Key**: 你的火山方舟 API Key
- **模型列表**: `doubao-seed-2.0-code`, `doubao-seed-2.0-pro`, `doubao-seed-2.0-lite`, `doubao-seed-2.0-mini`, `minimax-m2.7`, `glm-5.1`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `doubao-embedding-vision`, `doubao-seedream-5.0-lite`

### 3. 配置图片生成

**管理员面板** → **设置** → **图片生成**：
- 启用图片生成
- 引擎: OpenAI
- 模型: `doubao-seedream-5.0-lite`
- API URL: `https://ark.cn-beijing.volces.com/api/plan/v3`
- API Key: 你的火山方舟 API Key

### 4. 配置 Seedream 工具

**Workspace** → **Tools** → **+ 创建 Tool**：
- 粘贴 `tools/seedream_image_generation.py` 内容
- 保存后设置 Valves 中的 `api_key`

### 5. 配置模型系统提示词

为非视觉模型（DeepSeek 等）设置系统提示词，让模型知道如何处理上传的图片：

**Workspace** → **Models** → 选择模型 → **Params** → **System Prompt**：
```
当用户上传了图片，而你是非视觉模型（不支持直接看图片）时：
1. 消息中可能会包含 <file type="image" uuid="xxx"/> 或 <attached_files> 标签
2. 从这些标签中提取 file uuid
3. 在调用 generate_image 工具时，将 uuid 传入 reference_images 参数
4. 不要尝试描述图片内容，直接调用工具进行图生图编辑
```

同时在 **Tools** 中勾选 "Seedream 图片生成"。

## 工作原理

### 图生图流程

```
用户上传图片
    │
    ▼
Open WebUI 将图片保存到文件系统并分配 UUID
    │
    ▼
非视觉模型（如 DeepSeek）收到含 <attached_files> 标签的消息
    │
    ▼
模型根据 System Prompt 的指示，从标签中提取 UUID
    │
    ▼
模型调用 generate_image(reference_images=["uuid"])
    │
    ▼
Seedream Tool
  ├── 从 SQLite 查询文件路径
  ├── 从磁盘读取文件 → base64 编码
  └── 调用火山方舟 API /images/generations
    │
    ▼
火山方舟 Seedream 模型
  ├── 分析参考图
  ├── 根据 prompt 编辑图片
  └── 返回生成结果
    │
    ▼
用户看到生成的新图片
```

### 关键修复

- **工具图片读取**：内部通过文件系统直接读取图片（而非 HTTP 自请求），避免在同一进程内请求 `localhost:8080` 导致的死锁超时问题。
- **非视觉模型中间件 Patch**：`scripts/middleware.py` 是对 Open WebUI 官方 `middleware.py` 的修改版本，包含两个 patch：
  - **DB 消息加载**：由聊天历史重建消息时，对非视觉模型不会注入 `image_url` 数据块，而是改为 `<file type="image">` 文本引用，避免 API 报 "Model do not support image input" 错误
  - **Base64 转换前过滤**：在前端传来的消息中，对非视觉模型剥离已有的 `image_url` 内容块，仅保留文本部分，防止图片数据被发送到不支持的模型
- **自动应用机制**：`scripts/middleware.py` 不会被持久化到容器镜像，每次容器启动后通过 `docker cp` 替换（详见 `start.sh` 步骤 6）

## 配置参考

### API 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `api_base_url` | `https://ark.cn-beijing.volces.com/api/plan/v3` | 火山方舟 API 地址 |
| `model` | `doubao-seedream-5.0-lite` | Seedream 模型 |
| `prompt_optimization` | `true` | 自动优化提示词 |
| `watermark` | `true` | 添加水印 |
| `output_format` | `jpeg` | 输出格式 |
| `timeout_seconds` | `120` | API 超时时间 |

### 支持的生成模式

| 模式 | 说明 | 必需参数 |
|------|------|----------|
| `text-to-image` | 文生图 | `prompt` |
| `image-to-image` | 图生图 | `prompt`, `reference_images` |

## 常见问题

### Q: DeepSeek 报 "Model do not support image input"
检查该模型的 System Prompt 是否已配置图片 UUID 处理指令。非视觉模型需要通过 System Prompt 告知如何处理图片 UUID。

### Q: 图片生成质量不理想
- 提示词越详细效果越好
- 可以尝试关闭 `optimize` 参数使用原始提示词
- 尝试 `size: "3K"` 获得更高分辨率

### Q: 如何获取 API Key？
登录[火山方舟控制台](https://console.volcengine.com/ark/region:ark+cn-beijing/) → API Key 管理 → 创建 API Key

## 参考链接

- [Open WebUI](https://github.com/open-webui/open-webui)
- [火山方舟 Seedream API 文档](https://www.volcengine.com/docs/82379/1541523)
- [火山方舟 Agent Plan](https://www.volcengine.com/docs/82379/2375486)
