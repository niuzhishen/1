#!/usr/bin/env python3
"""QQ 群聊总结机器人入口。

用法：
    python bot.py

配置见 .env（可复制 .env.example 修改）。
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
