# QQ 群聊总结机器人

一个帮你**自动捕捉并总结 QQ 群聊消息**的机器人。

它像一个安静的旁观者，把群里的消息悄悄存下来，然后：

- 📊 **定时日报**：每天固定时间自动生成「今天大家都在聊什么」的摘要，**私聊只发给你一个人**；
- 💬 **按需总结**：在群里发一句 `总结 2小时`，结果**私聊发给你**；
- 🔒 **群里零输出**：机器人从不在群里发任何消息，群里其他人既看不到摘要，也无法触发命令；
- 🤫 **只读模式（可选）**：上线时自动对指定群开启全体禁言，纯收集不打扰。

摘要由任意 **OpenAI 兼容** 的大模型生成（OpenAI / DeepSeek / 月之暗面 / 通义千问 / 本地 Ollama 等）。

> **隐私保证**：所有日报、总结、进度提示都通过 `send_private_msg` 发给配置的 `OWNER_QQ`（你的 QQ 号），不经过任何群聊；只有 `OWNER_QQ` 本人发的命令才会被响应，其他群成员发 `总结`/`日报` 会被静默忽略。

---

## 工作原理

```
┌─────────┐  OneBot 11 (正向 WebSocket)  ┌──────────────┐      ┌──────────────┐
│  NapCat  │ ───────────────────────────▶ │  本机器人      │ ───▶ │  大模型 (LLM) │
│ (QQ 协议端)│ ◀─────────────────────────── │ (nonebot2)   │      │  OpenAI 兼容  │
└─────────┘        发送日报/总结           │  SQLite 存储  │      └──────────────┘
                                          └──────────────┘
```

- **NapCat** 负责把 QQ 协议翻译成标准的 OneBot 11 接口（你需要自己准备并登录一个 QQ 号）；
- 本机器人以 **WebSocket 客户端** 身份连接 NapCat，收到群消息后写入本地 **SQLite**；
- 到达定时时间、或有人发 `总结`/`日报` 命令时，把最近的消息整理成文本交给大模型，生成 Markdown 摘要发回群里。

> ⚠️ 使用第三方 QQ 协议端（NapCat 等）属于非官方方式，存在一定**账号风控风险**，请用小号或可承受风险的账号，并遵守相关法律法规与平台协议。

---

## 快速开始

### 1. 准备 NapCat

1. 下载并安装 [NapCat](https://napneko.github.io/)（支持 NapCat Shell / Docker / QQ 本体插件等方式）；
2. 登录你的 QQ 号；
3. 打开 NapCat 的 **WebUI → 网络配置**，新建一个 **正向 WebSocket（websocketServer）**：
   - 端口（示例用 `3001`），记下它；
   - 如果设置了 `token`，也记下来；

参考配置文件见 [`napcat_config_example.json`](./napcat_config_example.json)。

### 2. 安装依赖

需要 Python 3.10+。

```bash
cd 本仓库目录
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置

复制示例配置并按需修改：

```bash
cp .env.example .env
```

打开 `.env`，至少改这几项：

| 变量 | 说明 |
| --- | --- |
| `OWNER_QQ` | **你的 QQ 号（必填）**。所有日报/总结只私聊发给这个号 |
| `ONEBOT_WS_URLS` | NapCat 的正向 WebSocket 地址，如 `["ws://127.0.0.1:3001"]` |
| `ONEBOT_ACCESS_TOKEN` | NapCat 里设的 token，没设就留空 |
| `LLM_API_KEY` | 大模型的 API Key |
| `LLM_BASE_URL` | OpenAI 官方留空；DeepSeek 填 `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名，如 `gpt-4o-mini`、`deepseek-chat` |
| `DIGEST_CRON_HOUR` / `DIGEST_CRON_MINUTE` | 日报生成时间（默认 22:00，时区见 `DIGEST_TIMEZONE`） |

> 💡 为确保私聊能送达，建议让机器人 QQ 号与你的 `OWNER_QQ` 号**互为好友**（或对方账号允许接收陌生人私聊消息）。

> 用 **DeepSeek** 的完整示例：`LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_MODEL=deepseek-chat`。
> 用 **本地 Ollama**：`LLM_BASE_URL=http://127.0.0.1:11434/v1`、`LLM_API_KEY=ollama`、`LLM_MODEL=qwen2.5:7b`。

完整变量说明见 [`.env.example`](./.env.example) 里的注释。

### 4. 运行

```bash
source .venv/bin/activate
python bot.py
```

看到类似日志说明连接成功：

```
[SUCCESS] OneBot V11 | Bot <你的QQ号> connected
[INFO] 群聊总结机器人已加载：每天 22:00 发送日报 ...
```

### 5. 把机器人拉进群

将登录的那个 QQ 号加入要总结的群即可。机器人会**自动开始收集**这些群的消息（`TRACK_GROUPS=*` 时收集所有群）。

---

## 使用方法

### 定时日报（默认开启）

到点（默认每天 22:00）自动总结过去 `DIGEST_LOOKBACK_HOURS` 小时的聊天，**私聊**发给你（`OWNER_QQ`），每个群一条私聊消息，格式类似：

> 📊 群聊日报 · 2026-09-29 · 群「技术交流群」（123456）
>
> # 📋 群聊摘要（09-29 22:00 ~ 09-30 22:00）
> ## 主要话题 …
> ## 结论与决定 …

- `DIGEST_GROUPS=[]`（留空）→ 总结**所有有消息的群**；
- `DIGEST_GROUPS=[群号1, 群号2]` → 只总结这几个群。

### 按需总结（仅主人可用）

**只有 `OWNER_QQ` 本人**在群里发送命令才会生效（其他人发了也没反应），结果私聊发给你：

| 命令 | 效果 |
| --- | --- |
| `总结` | 总结最近 `DEFAULT_WINDOW_MINUTES` 分钟（默认 120）|
| `总结 2小时` | 总结最近 2 小时 |
| `总结 30分钟` | 总结最近 30 分钟 |
| `总结 今天` | 总结今天 0 点到现在 |
| `总结 昨天` | 总结昨天全天 |
| `总结 100条` | 总结最近 100 条消息 |
| `/总结 2小时` | 同上（带斜杠也可以）|

### 立即生成日报

在群里发送 `日报`，不等定时，立刻生成并**私聊**发给你。

### 只读旁观模式（可选）

在 `.env` 里设置：

```
ON_CONNECT_GROUP_IDS=[群号1, 群号2]
```

机器人上线后会自动对这些群**开启全体禁言**并发一条说明，只安静收集消息。需要发言时让管理员手动关闭禁言即可。

---

## 配置参考

所有配置都通过 `.env`（环境变量）设置，字段名大写。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OWNER_QQ` | 无（**必填**）| 你的 QQ 号；日报/总结只私聊发给它，且只有它能触发命令 |
| `ONEBOT_WS_URLS` | `["ws://127.0.0.1:3001"]` | NapCat 正向 WebSocket 地址（列表）|
| `ONEBOT_ACCESS_TOKEN` | 空 | NapCat 的 token |
| `TRACK_GROUPS` | `*` | 收集哪些群；`*` 全部，或 `[群号,...]` |
| `ON_CONNECT_GROUP_IDS` | `[]` | 上线后自动全体禁言的群 |
| `LLM_API_KEY` | 空 | 大模型 API Key |
| `LLM_BASE_URL` | 空 | OpenAI 兼容接口地址，OpenAI 官方留空 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名 |
| `LLM_MAX_MESSAGES` | `2000` | 单次最多喂给模型的消息条数（取最近）|
| `LLM_MAX_CHARS_PER_MESSAGE` | `500` | 单条消息超长时的截断长度 |
| `SUMMARY_FOCUS` | 考研主题 | 摘要「🎯 重点关注速览」要盯的话题，按群主题自定义，留空关闭该板块 |
| `DIGEST_CRON_HOUR` / `DIGEST_CRON_MINUTE` | `22` / `0` | 日报生成时间 |
| `DIGEST_TIMEZONE` | `Asia/Shanghai` | 日报时区 |
| `DIGEST_LOOKBACK_HOURS` | `24` | 日报回看多少小时 |
| `DIGEST_GROUPS` | `[]` | 日报要总结的群；空=所有有消息的群（结果私聊发给 `OWNER_QQ`）|
| `DEFAULT_WINDOW_MINUTES` | `120` | 裸 `总结` 命令的默认窗口 |
| `DB_PATH` | `data/messages.db` | 消息数据库文件路径 |
| `DRIVER` | `~fastapi+~websockets` | 不要改（websockets 用于连接 NapCat）|

---

## 目录结构

```
.
├── bot.py                    # 入口
├── requirements.txt
├── .env.example              # 配置模板
├── napcat_config_example.json# NapCat 网络配置示例
├── plugins/
│   └── qq_summarizer/
│       ├── __init__.py       # 消息收集、命令、定时任务
│       ├── config.py         # 配置模型
│       ├── db.py             # SQLite 存储
│       ├── summarizer.py     # 调用大模型生成摘要
│       └── timeutil.py       # 「2小时/今天」等时间解析
└── tests/
    ├── test_core.py          # 时间解析/存储/截断 单元测试
    └── test_integration.py   # 端到端（模拟 NapCat + 模拟大模型）
```

---

## 运行测试

```bash
source .venv/bin/activate

# 核心逻辑单元测试
python tests/test_core.py

# 端到端集成测试：会自动起一个「假 NapCat」和一个「假大模型」，
# 完整验证 连接→收消息→入库→总结命令→日报命令
python tests/test_integration.py
```

---

## 常见问题

**Q: 日志里一直报 `Connection refused` / 连不上？**
检查 `ONEBOT_WS_URLS` 的地址端口是否和 NapCat 的正向 WebSocket 一致，NapCat 是否已启动并登录。

**Q: 提示 `does not support websocket client connections`？**
确认 `.env` 里有 `DRIVER=~fastapi+~websockets`，并且装了 `websockets`（`requirements.txt` 已包含）。

**Q: 日报/总结没有私聊收到？**
- 确认 `.env` 里 `OWNER_QQ` 填的是你自己的 QQ 号；
- 让机器人 QQ 号和你的号互为好友（或你的号允许陌生人私聊），否则私聊可能被拦截；
- 看运行日志里有没有「未配置 OWNER_QQ」「私聊发送日报失败」之类的警告。

**Q: 收不到群消息 / 不总结？**
- 确认机器人 QQ 号在群里；
- `TRACK_GROUPS` 是否包含该群（`*` 为全部）；
- 群里如果刚被禁言过，先等机器人上线动作完成。

**Q: 摘要内容不理想？**
- 改 `SUMMARY_FOCUS`：告诉模型你的群核心话题（如「考研调剂/院校信息」），摘要开头会有「🎯 重点关注速览」逐条提取；
- 换更强的模型（如 `deepseek-chat`、`gpt-4o`）；
- 调大 `LLM_MAX_MESSAGES` / `LLM_MAX_CHARS_PER_MESSAGE`（注意 token 上限）；
- 提示词结构在 `plugins/qq_summarizer/summarizer.py` 的 `build_system_prompt`，可自行调整。

**Q: 消息存哪里？怎么清理？**
存在 `DB_PATH`（默认 `data/messages.db`）的 SQLite 文件里。删除该文件即清空（机器人重启会自动重建）。

---

## 安全与合规

- 请遵守 QQ 平台协议与相关法律法规，仅在自己拥有管理权限或已获授权的群中使用；
- `.env` 中包含 API Key，已在 `.gitignore` 中，**不要提交到仓库**；
- 群聊内容涉及他人隐私，请妥善处理收集到的数据。
