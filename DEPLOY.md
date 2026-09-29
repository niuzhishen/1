# 从零部署指南

本教程带你从零开始部署「QQ 群聊总结机器人」。以 **Windows** 为主线（Linux/Docker 见文末附录），全程大约 30 分钟。

## 总体架构（先看懂再动手）

```
你的 QQ 主号 ──好友私聊──▶ 机器人小号（登录在 NapCat 里）
                                  │ 正向 WebSocket (ws://127.0.0.1:3001)
                                  ▼
                          本项目机器人程序 (bot.py)
                                  │ HTTPS
                                  ▼
                          大模型 (DeepSeek / OpenAI / ...)
```

- **NapCat**：把 QQ 协议翻译成标准接口（OneBot 11）的"协议端"，需要登录一个 QQ 号；
- **bot.py**：本项目，连接 NapCat 收群消息、存库、调大模型、私聊发日报给你；
- **两个账号**：机器人小号 + 你的主号，**必须互为好友**（否则私聊送不到）。

---

## 第 0 步：准备两个 QQ 号

1. 一个**机器人小号**（用来登录 NapCat、进群潜水收集消息）；
2. 你的**主号**（接收日报和总结结果）；
3. 两个号**互加好友**；
4. 把小号拉进所有你想总结的群。

> ⚠️ 第三方协议端有轻微风控风险，务必用小号。

---

## 第 1 步：安装并登录 NapCat

1. 到 [NapCat 发布页](https://github.com/NapNeko/NapCatQQ/releases) 下载 `NapCatInstaller.zip`（Windows）；
2. 解压，运行 `NapCatInstaller.exe` 完成安装；
3. 启动 NapCat，黑色窗口会打印类似：
   ```
   [NapCat] [WebUi] WebUi Publish Panel Url: http://127.0.0.1:6099/webui?token=xxxxxx
   ```
4. 浏览器打开这个地址（Ctrl+点击也行），进入 NapCat 的 WebUI；
5. 在 WebUI 里**扫码登录机器人小号**（用小号的手机 QQ 扫码）。

> token 每次启动可能变化，直接从启动日志里的完整 URL 复制最省事。

---

## 第 2 步：在 NapCat 里开「正向 WebSocket」

在 WebUI 左侧进入 **网络配置**：

1. 点 **添加**，类型选 **WebSocket 服务器**（即正向 WS）；
2. 配置：
   - 名称：随便，如 `总结机器人`
   - 端口：`3001`
   - token：留空（若设置了，需与 `.env` 中 `ONEBOT_ACCESS_TOKEN` 完全一致）
3. 保存并确认已**启用**。

> 别选成「WebSocket 客户端」（那是反向 WS，方向相反）。

---

## 第 3 步：安装 Python

1. 到 [python.org](https://www.python.org/downloads/) 下载 Python **3.10 以上**版本；
2. 安装时**勾选 “Add Python to PATH”**（重要）；
3. 新开一个终端验证：
   ```
   python --version
   ```
   显示 `Python 3.1x.x` 即可。

---

## 第 4 步：下载本项目

有 git：

```
git clone -b arena/01a0ecfd-1 https://github.com/niuzhishen/1.git
cd 1
```

没有 git：在仓库页面点 **Code → Download ZIP**，解压后进入目录。

---

## 第 5 步：安装依赖

在项目目录的终端里：

```
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

国内网络慢的话，最后一行加镜像：

```
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

看到 `Successfully installed ...` 即成功。

---

## 第 6 步：配置 .env

```
copy .env.example .env        # Linux/macOS: cp .env.example .env
```

用记事本/VSCode 打开 `.env`，**最少**改这三处：

```ini
# 你的 QQ 主号（日报/总结私聊发给它，也只有它能触发命令）
OWNER_QQ=123456789

# 大模型（以 DeepSeek 为例）
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

其它常用可选配置：

```ini
DIGEST_CRON_HOUR=22          # 日报时间：22
DIGEST_CRON_MINUTE=0         #           ：00
DIGEST_LOOKBACK_HOURS=24     # 日报回看 24 小时
ONEBOT_WS_URLS=["ws://127.0.0.1:3001"]   # 已默认，与第 2 步端口一致即可
```

各家大模型的 `LLM_BASE_URL` 参考：

| 提供商 | LLM_BASE_URL | LLM_MODEL 示例 |
| --- | --- | --- |
| OpenAI | （留空） | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 月之暗面 | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 本地 Ollama | `http://127.0.0.1:11434/v1`（KEY 随便填）| `qwen2.5:7b` |

---

## 第 7 步：启动机器人

确保 NapCat 已启动且小号已登录，然后在项目目录：

```
.venv\Scripts\activate
python bot.py
```

看到这两行日志就是成功了：

```
[SUCCESS] OneBot V11 | Bot <小号QQ号> connected
[INFO] 群聊总结机器人已加载：每天 22:00 生成日报并私聊发送给 OWNER_QQ=<你的QQ号> ...
```

如果一直刷 `Connection refused`：NapCat 没启动、或没开正向 WS、或端口对不上，回第 1、2 步检查。

---

## 第 8 步：验证全流程

1. 在目标群里随便聊几句（用主号或拉个人配合）；
2. 用**你的主号**在群里发送：`总结`
3. 稍等几秒，你的主号会收到**机器人小号的私聊**：
   - 先是一条 `⏳ 正在总结…`
   - 接着是完整的 Markdown 摘要
4. 验证隐私：让群里**其他人**发一句 `总结`，应当毫无反应；群里也不会出现任何机器人消息。
5. 验证日报：在群里（主号）发 `日报`，会私聊收到一份日报。定时日报到点自动执行，无需手动。

---

## 第 9 步（可选）：后台常驻

**Windows**
- 最简单：保持终端窗口开着（最小化即可）；
- 想开机自启/后台运行：用 [WinSW](https://github.com/winsw/winsw) 或任务计划程序把
  `.venv\Scripts\python.exe bot.py` 注册为服务/计划任务。

**Linux（systemd 示例）**

```ini
# /etc/systemd/system/qq-summarizer.service
[Unit]
Description=QQ Group Chat Summarizer Bot
After=network.target

[Service]
WorkingDirectory=/path/to/1
ExecStart=/path/to/1/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl enable --now qq-summarizer
journalctl -u qq-summarizer -f     # 看日志
```

> NapCat 本身也要保持运行（Linux 可用其官方 shell 安装脚本 + launcher 常驻）。

---

## 常见问题排查

| 现象 | 原因与处理 |
| --- | --- |
| 日志刷 `Connection refused` | NapCat 没启动 / 没开正向 WS / 端口或地址不一致 |
| 提示 `does not support websocket client` | `.env` 里 `DRIVER=~fastapi+~websockets` 被改了，恢复它 |
| 连上了但收不到群消息 | 小号不在那个群里；或 `TRACK_GROUPS` 没包含该群（默认 `*` 全部）|
| 收不到私聊日报/总结 | ① `OWNER_QQ` 填错；② 两个号没互加好友或隐私设置拦截；③ 看日志有无「未配置 OWNER_QQ」「发送失败」警告 |
| `摘要生成失败` | 检查 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`；日志里有具体报错 |
| 总结很慢 | 正常，取决于模型响应速度；消息多时可调小 `LLM_MAX_MESSAGES` |
| 想让机器人别收某个群 | `TRACK_GROUPS=[群号1, 群号2]` 只列需要的群 |

---

## 附录：Linux / Docker 方式安装 NapCat

**Linux 一键脚本**（含 Linux QQ，详见 [NapCat 文档](https://napneko.github.io/)）：

```
curl -o napcat.sh https://raw.githubusercontent.com/NapNeko/napcat-linux-installer/refs/heads/main/install.sh && sudo bash napcat.sh
```

**Docker**（适合有服务器经验的用户）：

```
docker run -d --name napcat \
  -p 6099:6099 -p 3001:3001 \
  mlikiowa/napcat-docker:latest
```

然后同样走「WebUI → 扫码登录小号 → 网络配置加正向 WS（端口 3001）」流程。
注意容器场景下机器人程序里的 `ONEBOT_WS_URLS` 要写成宿主机可达的地址
（同机 Docker 可用 `ws://host.docker.internal:3001` 或宿主机内网 IP）。
