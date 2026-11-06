. "$PSScriptRoot\Use-Environment.ps1"
$PipelinePort = if ($env:PIPELINE_PORT) { [int]$env:PIPELINE_PORT } else { 8105 }
uv run --frozen uvicorn projects.p05_self_healing_pipeline.app:app --host 127.0.0.1 --port $PipelinePort
if ($LASTEXITCODE -ne 0) { throw 'Pipeline service failed.' }
