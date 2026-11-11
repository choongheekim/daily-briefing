# 정치 계정 자동 실행 등록(하루 3번). 실행: 2_자동실행_등록.bat 더블클릭
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Repo = Join-Path $env:USERPROFILE 'daily-briefing'
if (-not (Test-Path (Join-Path $Repo 'pc\run.py'))) { Write-Host "저장소에 새 파일(pc\run.py)이 없어요. 먼저 git pull 하세요."; exit 1 }
$py = $null
foreach ($c in 'py', 'python') {
  if (-not $py -and (Get-Command $c -ErrorAction SilentlyContinue)) {
    $p = & $c -c "import sys;print(sys.executable)" 2>$null | Select-Object -Last 1
    if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path $p)) { $py = $p.Trim() }
  }
}
if (-not $py) { Write-Host "python을 찾지 못했어요."; exit 1 }
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
if (Test-Path $pyw) { $py = $pyw }      # 검은 창 안 뜨게

# 예전 방식 작업은 지움
Unregister-ScheduledTask -TaskName 'daily-briefing-문구작성' -Confirm:$false -ErrorAction SilentlyContinue

$prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$set = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 80)
$jobs = @(@('06:15','07:17'), @('11:35','12:30'), @('17:35','18:30'))
foreach ($j in $jobs) {
  $name = "daily-briefing-$($j[1].Replace(':',''))"
  $act = New-ScheduledTaskAction -Execute $py -Argument "`"$Repo\pc\run.py`" --slot $($j[1])" -WorkingDirectory $Repo
  $trg = New-ScheduledTaskTrigger -Daily -At $j[0]
  Register-ScheduledTask -TaskName $name -Action $act -Trigger $trg -Principal $prn -Settings $set -Force | Out-Null
  Write-Host "등록: 매일 $($j[0]) 작성 시작 → $($j[1]) 게시  ($name)"
}
Write-Host ""
Write-Host " - 로그: $env:USERPROFILE\daily-briefing-logs\날짜.txt"
Write-Host " - PC는 잠금(Win+L)은 괜찮지만 '로그아웃'하면 안 돌아가요."
