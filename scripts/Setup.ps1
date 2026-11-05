. "$PSScriptRoot\Use-Environment.ps1"
uv sync
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
