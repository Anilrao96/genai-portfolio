. "$PSScriptRoot\Use-Environment.ps1"
$CouncilPort = if ($env:MCP_PORT) { [int]$env:MCP_PORT } else { 8101 }
uv run --frozen uvicorn projects.p01_mcp_agents.app:app --host 127.0.0.1 --port $CouncilPort
if ($LASTEXITCODE -ne 0) { throw 'MCP council service failed.' }
