. "$PSScriptRoot\Use-Environment.ps1"
uv run --frozen python scripts/start-code-session.py
if ($LASTEXITCODE -ne 0) { throw 'Run Setup-AppBuilder.ps1 first.' }
uv run --frozen python scripts/probe-code-isolation.py --ensure
if ($LASTEXITCODE -ne 0) { throw 'Native container session proof failed.' }
uv run --frozen python scripts/probe-app-isolation.py --ensure
if ($LASTEXITCODE -ne 0) { throw 'App-specific isolation controls failed.' }
$BuilderPython=Join-Path $PortfolioRoot '.venv\Scripts\python.exe'
$PreviewProcess=Start-Process -FilePath $BuilderPython -ArgumentList @('-m','uvicorn','projects.p08_app_builder.preview:app','--host','127.0.0.1','--port','8118') -WorkingDirectory $PortfolioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PortfolioRoot '.runtime\app-preview.out.log') -RedirectStandardError (Join-Path $PortfolioRoot '.runtime\app-preview.err.log') -PassThru
try {
    & $BuilderPython -m uvicorn projects.p08_app_builder.app:app --host 127.0.0.1 --port 8108
    if ($LASTEXITCODE -ne 0) { throw 'App builder service failed.' }
} finally {
    if (-not $PreviewProcess.HasExited) { $PreviewProcess.Kill($true) }
}
