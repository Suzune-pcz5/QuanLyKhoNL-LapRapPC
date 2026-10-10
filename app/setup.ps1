param([switch]$Stop)
$ErrorActionPreference = 'Stop'
$taskRuntime = Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo'
$taskPython = Join-Path $taskRuntime 'venv/Scripts/python.exe'
if ($Stop) {
    if (Test-Path -LiteralPath $taskPython) { & $taskPython (Join-Path $PSScriptRoot 'manage.py') stop }
    exit $LASTEXITCODE
}
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskSystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $taskSystemPython) { throw 'Can Python 3.11+ de cai demo.' }
    & $taskSystemPython -m venv (Join-Path $taskRuntime 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc Python venv.' }
}
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Cai thu vien that bai.' }
$taskMysql = Join-Path $taskRuntime 'mysql-8.4.11-winx64/bin/mysqld.exe'
if (-not (Test-Path -LiteralPath $taskMysql)) {
    $taskZip = Join-Path $taskRuntime 'mysql-8.4.11-winx64.zip'
    if (-not (Test-Path -LiteralPath $taskZip)) {
        Invoke-WebRequest 'https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip' -OutFile $taskZip
    }
    if ((Get-FileHash -LiteralPath $taskZip -Algorithm MD5).Hash -ne '2e833921898a9a030ea6bfe81bd811bc') { throw 'Checksum MySQL khong dung.' }
    Expand-Archive -LiteralPath $taskZip -DestinationPath $taskRuntime
}
& $taskPython (Join-Path $PSScriptRoot 'manage.py') start
if ($LASTEXITCODE -ne 0) { throw 'Khoi dong demo that bai.' }
