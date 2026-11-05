. "$PSScriptRoot\Use-Environment.ps1"
uv run --frozen pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Portfolio verification failed.' }
