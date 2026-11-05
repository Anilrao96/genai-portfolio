. "$PSScriptRoot\Use-Environment.ps1"
$LocalAIPort = if ($env:LOCAL_AI_PORT) { [int]$env:LOCAL_AI_PORT } else { 8104 }
uv run --frozen uvicorn projects.p04_local_ai.app:app --host 127.0.0.1 --port $LocalAIPort
if ($LASTEXITCODE -ne 0) { throw 'Local AI service failed.' }
