. "$PSScriptRoot\Use-Environment.ps1"
$SqlAssistantPort = if ($env:SQL_ASSISTANT_PORT) { [int]$env:SQL_ASSISTANT_PORT } else { 8107 }
uv run --frozen uvicorn projects.p07_sql_assistant.app:app --host 127.0.0.1 --port $SqlAssistantPort
if ($LASTEXITCODE -ne 0) { throw 'SQL assistant service failed.' }
