$names = 'daily-briefing-0717','daily-briefing-1230','daily-briefing-1830','daily-briefing-문구작성'
foreach ($n in $names) { Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue }
Write-Host "자동 실행을 모두 해제했어요."
