@echo off
rem QQ 群聊总结机器人启动脚本（Windows）
rem 双击即可运行；也可把它的快捷方式放进 shell:startup 实现开机自启
cd /d %~dp0
.venv\Scripts\python.exe bot.py
pause
