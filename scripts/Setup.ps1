param([string]$Python)

. "$PSScriptRoot\Use-Environment.ps1"
$SyncArguments = @('sync', '--locked')
if ($Python) { $SyncArguments += @('--python', $Python) }
uv @SyncArguments
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
