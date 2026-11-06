. "$PSScriptRoot\Use-Environment.ps1"
uv run --frozen python scripts/setup-wslc-sdk.py
if ($LASTEXITCODE -ne 0) { throw 'Project-local SDK setup failed.' }
uv run --frozen python scripts/start-code-session.py
if ($LASTEXITCODE -ne 0) { throw 'Container session failed; no Windows component installation was attempted.' }
uv run --frozen python scripts/prepare-code-image.py
if ($LASTEXITCODE -ne 0) { throw 'Container image preparation failed.' }
uv run --frozen python scripts/probe-code-isolation.py --ensure
if ($LASTEXITCODE -ne 0) { throw 'Isolation controls failed; generated execution remains disabled.' }
