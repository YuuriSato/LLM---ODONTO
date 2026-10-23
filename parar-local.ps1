$ErrorActionPreference = 'Stop'
$taskListeners = Get-NetTCPConnection -State Listen -LocalPort 9090 -ErrorAction SilentlyContinue
foreach ($taskProcessId in ($taskListeners.OwningProcess | Sort-Object -Unique)) {
    $taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $taskProcessId"
    if (-not $taskProcess.CommandLine -or
        $taskProcess.CommandLine.IndexOf($PSScriptRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $taskProcess.CommandLine -notmatch 'web_alteracao\.py') {
        throw "A porta 9090 pertence a outro processo. Nenhum processo foi encerrado."
    }
    Stop-Process -Id $taskProcessId
    Write-Output "Backend do projeto encerrado (PID $taskProcessId)."
}
