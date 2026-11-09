param(
    [switch]$Stop,
    [int]$Port = 8109,
    [int]$OllamaPort = 11435,
    [string]$Model = 'qwen3:4b'
)

. "$PSScriptRoot\Use-Environment.ps1"
if (-not $Stop) {
    uv run --frozen python scripts/setup-wslc-sdk.py
    if ($LASTEXITCODE -ne 0) { throw 'Native WSL SDK setup failed.' }
    uv run --frozen python scripts/start-code-session.py
    if ($LASTEXITCODE -ne 0) { throw 'Portfolio container session failed.' }
}
$Action = if ($Stop) { 'stop' } else { 'start' }
uv run --frozen python scripts/docker-agent.py $Action --port $Port --ollama-port $OllamaPort --model $Model
if ($LASTEXITCODE -ne 0) { throw 'Clearflow Docker launcher failed.' }
