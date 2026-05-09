# llm-live2d 快速启动脚本（PowerShell）
# 用法：.\start-server.ps1

# 设置环境变量
$env:OPENAI_API_KEY="sk-86618e8d1c1f4d2bb0783849480a398a"

# DeepSeek V4 Flash 配置
$env:OPENAI_BASE_URL="https://api.deepseek.com/v1"
$env:OPENAI_MODEL="deepseek-v4-flash"

# 可选：自定义 TTS 声音
# $env:TTS_VOICE="zh-CN-XiaoxiaoNeural"

Write-Host "启动 llm-live2d 服务器..." -ForegroundColor Green
Write-Host "API Key: ${env:OPENAI_API_KEY}" -ForegroundColor Yellow
Write-Host "Base URL: ${env:OPENAI_BASE_URL}" -ForegroundColor Yellow
Write-Host "Model: ${env:OPENAI_MODEL}" -ForegroundColor Yellow

# 启动服务器
python examples/run_server.py
