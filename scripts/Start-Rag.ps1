. "$PSScriptRoot\Use-Environment.ps1"
$RagPort = if ($env:RAG_PORT) { [int]$env:RAG_PORT } else { 8103 }
uv run --frozen uvicorn projects.p03_agentic_rag.app:app --host 127.0.0.1 --port $RagPort
if ($LASTEXITCODE -ne 0) { throw 'RAG service failed.' }
