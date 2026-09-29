from nonebot import get_plugin_config
from pydantic import BaseModel
from typing import Union


class SummarizerConfig(BaseModel):
    """QQ 群聊总结机器人配置（通过 .env 或环境变量设置，字段名大写即可）。"""

    # ---- OneBot / NapCat ----
    # 连接配置由 onebot 适配器直接读取环境变量：
    #   ONEBOT_WS_URLS=["ws://127.0.0.1:3001"]  正向 WebSocket 地址
    #   ONEBOT_ACCESS_TOKEN=xxx                 与 NapCat 的 token 一致
    # ---- 收集范围 ----
    track_groups: Union[str, list[int]] = "*"
    on_connect_group_ids: list[int] = []

    # ---- 接收人 ----
    # 你的 QQ 号：所有日报/总结结果只通过私聊发给你，
    # 且只有你能触发 总结/日报 命令
    owner_qq: int | None = None

    # ---- 大模型 ----
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_max_messages: int = 2000
    llm_max_chars_per_message: int = 500

    # ---- 定时日报 ----
    digest_cron_hour: int = 22
    digest_cron_minute: int = 0
    digest_timezone: str = "Asia/Shanghai"
    digest_lookback_hours: float = 24.0
    # 日报要总结哪些群；留空 [] 则总结所有有消息的群
    # （结果统一私聊发给 OWNER_QQ，不会发到群里）
    digest_groups: list[int] = []

    # ---- 其它 ----
    default_window_minutes: int = 120
    db_path: str = "data/messages.db"
    # 只注册「总结」；配合 COMMAND_START=["", "/"]，「总结」和「/总结」都能触发
    command_triggers: list[str] = ["总结"]

    @property
    def track_all(self) -> bool:
        return self.track_groups == "*" or self.track_groups == ["*"]

    def should_track(self, group_id: int) -> bool:
        if self.track_all:
            return True
        return group_id in self.track_groups


config = get_plugin_config(SummarizerConfig)
