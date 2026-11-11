# 매일 06:40 문구 작성 작업 등록(작업 스케줄러). 실행: 작업등록.bat 더블클릭
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Repo = Join-Path $env:USERPROFILE 'daily-briefing'
if (-not (Test-Path (Join-Path $Repo 'pc\write.py'))) { Write-Host "저장소가 없어요. 먼저 점검.bat 을 실행하세요."; exit 1 }
$py = (Get-Command python).Source
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
if (Test-Path $pyw) { $py = $pyw }      # 검은 창 안 뜨게
$name = 'daily-briefing-문구작성'
$act = New-ScheduledTaskAction -Execute $py -Argument "`"$Repo\pc\write.py`"" -WorkingDirectory $Repo
$trg = New-ScheduledTaskTrigger -Daily -At '06:40'
$prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$set = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $name -Action $act -Trigger $trg -Principal $prn -Settings $set -Force | Out-Null
Write-Host ""
Write-Host "등록 완료: 매일 06:40 '$name'"
Write-Host " - 로그: $env:USERPROFILE\daily-briefing-logs\날짜.txt"
Write-Host " - 지금 한 번 시험하려면: 작업 스케줄러 > $name > 마우스 오른쪽 > 실행"
Write-Host " - PC는 잠금(Win+L)은 괜찮지만 '로그아웃'하면 안 돌아가요."
