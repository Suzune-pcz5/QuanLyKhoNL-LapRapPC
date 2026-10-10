param(
    [ValidateSet('Inspect', 'Stop')][string]$Action = 'Inspect',
    [Parameter(Mandatory = $true)][string]$ServerPath,
    [int]$RecordedPid = 0
)
$ErrorActionPreference = 'Stop'
$taskPath = [IO.Path]::GetFullPath($ServerPath)
$taskPattern = '(^|\s|")' + [regex]::Escape($taskPath) + '(\s|"|$)'
function Test-TaskServer($taskProcess) {
    return $taskProcess -and $taskProcess.CommandLine -and
        [regex]::IsMatch($taskProcess.CommandLine, $taskPattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
}
$taskServers = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { Test-TaskServer $_ })
$taskListeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
$taskRecorded = $null
if ($RecordedPid -gt 0) { $taskRecorded = Get-CimInstance Win32_Process -Filter "ProcessId=$RecordedPid" }
if ($Action -eq 'Inspect') {
    [pscustomobject]@{
        processes = @($taskServers | ForEach-Object { @{ pid = [int]$_.ProcessId; parent = [int]$_.ParentProcessId } })
        listeners = @($taskListeners | ForEach-Object { [int]$_ })
        recorded_present = [bool]$taskRecorded
        recorded_owned = [bool](Test-TaskServer $taskRecorded)
    } | ConvertTo-Json -Depth 4 -Compress
    exit 0
}
if ($taskRecorded -and -not (Test-TaskServer $taskRecorded)) {
    throw 'PID da ghi thuoc ung dung hoac thu muc khac. Khong dung tien trinh.'
}
$taskOwnedIds = @($taskServers | ForEach-Object { [int]$_.ProcessId })
foreach ($taskListener in $taskListeners) {
    if ($taskListener -notin $taskOwnedIds) { throw 'Cong 8765 thuoc ung dung hoac thu muc khac. Khong dung tien trinh.' }
}
foreach ($taskPid in $taskOwnedIds) {
    $taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$taskPid"
    if (-not $taskProcess) { continue }
    if (-not (Test-TaskServer $taskProcess)) { throw 'PID da thay doi chu so huu. Khong dung tien trinh.' }
    Stop-Process -Id $taskPid -ErrorAction Stop
}
