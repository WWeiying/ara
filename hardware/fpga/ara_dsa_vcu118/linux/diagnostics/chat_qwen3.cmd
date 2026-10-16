@echo off
chcp 65001 >nul
title Ara FPGA Chat
py -3 -X utf8 "%~dp0chat_qwen3.py"
if errorlevel 1 pause
