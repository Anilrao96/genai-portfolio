$ErrorActionPreference = 'Stop'
$PortfolioRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $PortfolioRoot
$env:UV_CACHE_DIR = Join-Path $PortfolioRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PortfolioRoot '.tools\python'
$env:UV_PYTHON_BIN_DIR = Join-Path $PortfolioRoot '.tools\bin'
$env:UV_PYTHON_INSTALL_REGISTRY = '0'
$PortfolioTemp = Join-Path $PortfolioRoot '.runtime\temp'
New-Item -ItemType Directory -Force -Path $PortfolioTemp | Out-Null
$env:TEMP = $PortfolioTemp
$env:TMP = $PortfolioTemp
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = 'http://127.0.0.1:11435' }
