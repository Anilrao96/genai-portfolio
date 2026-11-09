. "$PSScriptRoot\Use-Environment.ps1"
& "$PSScriptRoot\Setup-CodeAssistant.ps1"
uv run --frozen python scripts/setup-app-toolchain.py
if ($LASTEXITCODE -ne 0) { throw 'Trusted app toolchain build failed.' }
uv run --frozen python scripts/probe-app-isolation.py --ensure
if ($LASTEXITCODE -ne 0) { throw 'App-specific isolation controls failed; generation is blocked.' }
