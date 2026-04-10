# 创建项目

创建一个新的视频生成项目。

## 用户交互（非常重要）

在调用创建项目的接口前，必须向用户确认以下偏好信息：
1. **故事内容/主线想法** (`idea`)：如果不填，模型会自由发散。
2. **是否提供参考剧本文档**：明确告知用户支持上传本地文档（支持格式：`.doc`, `.docx`, `.pdf`, `.txt`, `.md`）。如果用户发送了文件，请先参考 `upload_file.md` 进行上传处理，获取到 `file_path`。
3. **集数** (`episodes`)：默认 4 集。
4. **视频比例** (`video_ratio`)：默认 9:16。

## 请求与响应

### 请求

```bash
curl -X POST "http://localhost:8000/api/project/start" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "", 
    "idea": "故事内容 (若有 file_path 则会与文档内容自动合并)",
    "style": "realistic",
    "video_ratio": "9:16",
    "episodes": 4,
    "llm_model": "qwen3.5-plus",
    "vlm_model": "qwen-vl-plus",
    "image_t2i_model": "doubao-seedream-5-0",
    "image_it2i_model": "doubao-seedream-5-0",
    "video_model": "wan2.6-i2v-flash",
    "enable_concurrency": true,
    "web_search": false
  }'
```

### 响应

```json
{
  "session_id": "xxx",
  "status": "completed",
  "params": {
    "idea": "故事内容",
    "style": "realistic",
    "llm_model": "qwen3.5-plus",
    "vlm_model": "qwen-vl-plus",
    "episodes": 4
  }
}
```

---

## 阶段流程与停点

本项目采用 **Agent 驱动的 6 阶段流水线**。系统在第一阶段配置完成后，后续的各生成阶段均有对应的 **停点 (Stop Event)**。

由于最初的项目沟通需要确认多种配置，第一阶段的前置分为两个停点：
- **停点0**：确认剧情/集剧设置
- **停点1**：确认项目生成参数

随后的流水线遵循如下规则：

| 阶段 | 停点 ID | 阶段内部步骤 (Phase) | 说明 |
|------|---------|-----------------------|------|
| 1 | 2 | script_generation | 剧本生成：产出全剧本、人物设定、环境设定 |
| 2 | 3 | character_design | 角色/场景设计：为每个角色/场景生成参考图 |
| 3 | 4 | storyboard | 分镜设计：将剧本拆分为具体镜头 (segments) |
| 4 | 5 | reference_generation | 参考图生成：根据分镜生成首帧控制图 |
| 5 | 6 | video_generation | 视频生成：根据参考图生成动态视频片段 |
| 6 | - | post_production | 后期剪辑：按剧集拼接视频并生成最终成片 |

---

## 全局监听：SSE 进度流

启动项目后，**必须** 立即连接 SSE 端点以接收实时反馈：

```bash
# 执行第一阶段并获取进度
curl -N "http://localhost:8000/api/project/{session_id}/execute/script_generation"
```

SSE 每个事件为一行 JSON：

- `{"type": "progress", "percent": 10, "message": "正在生成剧本..."}`
- `{"type": "stage_complete", "stage": "script_generation", "requires_intervention": true}`
- `{"type": "error", "content": "..."}`

---

## 查看项目状态

随时可以查看当前剧本、分镜或视频的状态：

```bash
curl "http://localhost:8000/api/project/{session_id}/status"
```

---

## 停点0：项目配置说明

在停点0和用户沟通配置时，可以参考以下可供选择的模型和参数列表：

1. **故事创意 (idea)**: 自由文本输入
2. **参考剧本上传 (file_path)**: 支持 .doc, .docx, .pdf, .txt, .md
3. **剧集数量 (episodes)**: 正整数，默认 4
4. **视频风格 (style)**: 默认 realistic（可选 anime, 3d, pixel_art, 等）
5. **视频比例 (video_ratio)**: 默认 9:16（可选 16:9, 1:1, 4:3 等）

> **注意**：
> - **以上参数为第一步核心剧情与表现形式选项，必须在停点0展示给用户确认**
> - 确认无误后，再进入下方的停点1交流生成参数

### 展示停点0配置

根据用户提供的idea和选择，生成剧情配置表格：

| 配置项 | 当前值 |
|--------|--------|
| 故事创意 (idea) | [用户的创意内容，选填] |
| 参考文档 (file_path) | [文档名，如无则为"未上传"] |
| 剧集数量 (episodes)| 4（默认值）或其他用户选择 |
| 视频风格 (style) | realistic（默认值）或其他用户选择 |
| 视频比例 (video_ratio) | 9:16（默认值）或其他用户选择 |

### 询问用户停点0

> 当前剧情与视觉表现配置如上，请确认是否有需要调整的地方？
> - 如需调整创意、集数、风格或比例，请告知
> - 如果就按上面来规划，请回复“确认”

---

## 停点1：模型参数选项说明

确认完剧情和表现形式后，在停点1和用户沟通具体的模型和控制参数：

1. **LLM 模型**: qwen3.5-plus（默认值）
   - 可选：qwen3.5-plus, deepseek-chat, gpt-4o, gemini-2.5-flash
4. **VLM 模型**: qwen-vl-plus（默认值）
   - 可选：qwen-vl-plus, gemini-2.5-flash-image
5. **T2I 模型** (文生图): doubao-seedream-5-0（默认值）
   - 可选：doubao-seedream-5-0, wan2.6-t2i, jimeng_t2i_v40
6. **I2I 模型** (图生图): doubao-seedream-5-0（默认值）
   - 可选：doubao-seedream-5-0, wan2.6-image
7. **Video 模型**: wan2.6-i2v-flash（默认值）
   - 可选：wan2.6-i2v-flash, kling-v3, jimeng_ti2v_v30_pro
8. **联网搜索**: false（默认值）
   - 可选：true, false
9. **并发生成**: true（默认值）
   - 可选：true, false

> **注意**：
> - **所有参数必须都展示给用户确认**
> - 根据用户消息渠道选择格式：
>   - 飞书：使用 Markdown 表格
>   - 微信：使用编号列表（微信不支持 Markdown 表格）

### 展示停点1配置

| 配置项 | 当前值 |
|--------|--------|
| LLM 模型 | qwen3.5-plus（默认值）|
| VLM 模型 | qwen-vl-plus（默认值）|
| T2I 模型 | doubao-seedream-5-0（默认值）|
| I2I 模型 | doubao-seedream-5-0（默认值）|
| Video 模型 | wan2.6-i2v-flash（默认值）|
| 联网搜索 | false（默认值）|
| 并发生成 | true（默认值）|

### 询问用户停点1

> 当前项目的生成技术参数配置如上，请问是否有需要修改的？
> - 如需修改，请告知具体要修改的项目和新值
> - 如无需修改，请回复"确认"或"确定"

### 循环确认

- 如果用户提出修改 → 记录修改项 → 重新展示更新后的配置 → 再次询问确认
- 直到用户确认全部流程（停点0/停点1）均无修改 → 才能调用 API 创建项目

---

## 下一步

创建成功后，跳转到 [1. 生成剧本 (script_generation)](create_script.md)。

---

## 注意事项

1. **必须询问用户**：在创建项目前，一定要询问用户项目的配置，用户没有提及的选项则使用默认值
2. **检查 API Key**：在创建项目前，必须检查用户选择的模型对应的 API Key 是否已配置

### API Key 检查步骤

```bash
# 1. 读取 .env 文件
cat aigc-claw/backend/.env

# 2. 根据用户选择的模型检查对应 API Key
#    - LLM 模型：检查 DASHSCOPE_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
#    - 图片模型：检查 ARK_API_KEY / DASHSCOPE_API_KEY / VOLC_ACCESS_KEY/VOLC_SECRET_KEY
#    - 视频模型：检查 DASHSCOPE_API_KEY / VOLC_ACCESS_KEY/VOLC_SECRET_KEY / KLING_ACCESS_KEY/KLING_SECRET_KEY

# 3. 如果缺少 API Key，提醒用户配置
```

### 缺少 API Key 时的处理

如果检测到缺少必要的 API Key，需要告知用户：
1. 缺少哪个平台的 API Key
2. 如何获取（官方链接）
3. 配置位置（`aigc-claw/backend/.env` 文件）
4. 等待用户配置完成后才能继续创建项目

| 平台 | API Key 变量 | 获取链接 |
|------|--------------|----------|
| DeepSeek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys |
| 阿里云 DashScope | `DASHSCOPE_API_KEY` | https://bailian.console.aliyun.com/cn-beijing/?tab=home#/home |
| 字节火山方舟 | `ARK_API_KEY` 或 `VOLC_ACCESS_KEY`/`VOLC_SECRET_KEY` | https://www.volcengine.com/product/ark |
| 快手可灵 Kling | `KLING_ACCESS_KEY`/`KLING_SECRET_KEY` | https://klingai.com/cn/dev |

---

## 常见问题

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| `curl: (7) Failed to connect` | 后端未运行 | 启动后端服务 |
| `500 Internal Server Error` | API Key 缺失或配置错误 | 检查 `backend/.env` 文件 |
| `404 Not Found` | API 路径错误 | 确认 URL 为 `http://localhost:8000/api/project/start` |
