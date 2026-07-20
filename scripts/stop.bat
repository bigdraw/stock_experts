@echo off
REM Windows 一键停止 — 调用 PowerShell 脚本
powershell -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
