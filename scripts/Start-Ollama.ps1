. "$PSScriptRoot\Use-Environment.ps1"
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $PortfolioRoot '.models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
New-Item -ItemType Directory -Path $env:OLLAMA_MODELS -Force | Out-Null
Write-Output "Starting portfolio Ollama on $env:OLLAMA_HOST; weights: $env:OLLAMA_MODELS"
ollama serve
if ($LASTEXITCODE -ne 0) { throw 'Ollama service failed. Check whether port 11435 is already occupied.' }
