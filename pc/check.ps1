# 회사 PC 점검: claude -p / git / python 이 작업 스케줄러에서도 돌아가는지 확인
# 실행: 점검.bat 더블클릭 (결과는 메모장으로 열림)
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$RepoUrl = 'https://github.com/choongheekim/daily-briefing.git'
$Repo    = Join-Path $env:USERPROFILE 'daily-briefing'
$LogDir  = Join-Path $env:USERPROFILE 'daily-briefing-logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Report  = Join-Path $LogDir '점검결과.txt'
$lines = New-Object System.Collections.Generic.List[string]
$bad = 0
function Say($m)  { Write-Host $m; $lines.Add($m) }
function Ok($m)   { Say "  [OK]   $m" }
function Bad($m)  { Say "  [문제] $m"; $script:bad++ }
function Warn($m) { Say "  [주의] $m" }

Say "회사 PC 점검  $(Get-Date -Format 'yyyy-MM-dd HH:mm')  장치: $env:COMPUTERNAME  사용자: $env:USERNAME"
Say ""

# 1) 프로그램
Say "1. 프로그램 설치"
$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) { Ok "claude: $($claude.Source)  ($(& claude --version 2>$null))" } else { Bad "claude 명령 없음 → Claude Code 설치/PATH 확인" }
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Ok "git: $(& git --version)" } else { Bad "git 없음 → https://git-scm.com 에서 설치" }
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and $py.Source -notmatch 'WindowsApps') { Ok "python: $($py.Source)  ($(& python --version 2>&1))" }
elseif ($py) { Bad "python이 '스토어 바로가기'(WindowsApps)만 있음 → python.org 에서 설치(PATH 추가 체크)" }
else { Bad "python 없음 → python.org 에서 설치(설치 화면에서 'Add python.exe to PATH' 체크)" }

# 2) API 요금 위험 변수
Say ""
Say "2. API 요금이 나갈 수 있는 환경변수"
foreach ($n in 'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN') {
  $u = [Environment]::GetEnvironmentVariable($n, 'User'); $m = [Environment]::GetEnvironmentVariable($n, 'Machine')
  if ($u -or $m) { Warn "$n 가 PC에 설정돼 있음(사용자:$([bool]$u) 시스템:$([bool]$m)). 봇은 실행할 때 지우고 돌리지만, 안 쓰면 삭제 권장" }
  else { Ok "$n 없음" }
}

# 3) claude -p (구독) 시험
Say ""
Say "3. claude -p 구독 로그인 시험"
if ($claude) {
  $saveKey = $env:ANTHROPIC_API_KEY; $saveTok = $env:ANTHROPIC_AUTH_TOKEN
  Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
  $tmp = Join-Path $env:TEMP 'db-claude-test'; New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Push-Location $tmp
  $raw = 'Reply with exactly: OK' | & claude -p --model haiku --output-format json --no-session-persistence 2>&1 | Out-String
  Pop-Location
  if ($saveKey) { $env:ANTHROPIC_API_KEY = $saveKey }; if ($saveTok) { $env:ANTHROPIC_AUTH_TOKEN = $saveTok }
  try {
    $j = $raw | ConvertFrom-Json
    if (-not $j.is_error -and "$($j.result)" -match 'OK') { Ok "claude -p 응답 정상 ('$($j.result)')" }
    else { Bad "claude -p 오류: $($j.result)" }
  } catch { Bad "claude -p 실행 실패: $($raw.Trim() | Select-Object -First 1)  → 'claude' 실행 후 /login 으로 구독 계정 로그인" }
}

# 4) GitHub 연결 + 저장소 받기
Say ""
Say "4. GitHub"
if ($git) {
  $ls = & git ls-remote $RepoUrl HEAD 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Ok "github.com 접속 가능" } else { Bad "github.com 접속 실패: $($ls.Trim())" }
  if (-not (Test-Path (Join-Path $Repo '.git'))) {
    & git clone -q $RepoUrl $Repo 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "저장소 받음 → $Repo" } else { Bad "저장소 받기 실패" }
  } else {
    & git -C $Repo pull -q --rebase --autostash 2>&1 | Out-Null
    Ok "저장소 있음 → $Repo (최신으로 갱신)"
  }
  Say "     (GitHub 로그인 창이 뜨면 choongheekim 계정으로 로그인하세요 — 처음 한 번만)"
  $pr = & git -C $Repo push --dry-run 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) { Ok "GitHub에 올리기(push) 권한 있음" } else { Bad "push 권한 확인 실패: $($pr.Trim())" }
}

# 5) 파이썬 패키지 + 뉴스·텔레그램 접속
Say ""
Say "5. 파이썬 패키지 / 뉴스 사이트 접속"
if ($py -and (Test-Path (Join-Path $Repo 'requirements.txt'))) {
  & python -m pip install -q --disable-pip-version-check -r (Join-Path $Repo 'requirements.txt') 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { Ok "패키지 설치 완료" } else { Bad "pip 설치 실패(회사망이 pypi.org를 막는지 확인)" }
  Push-Location $Repo
  $probe = & python -c "from bot.news import fetch_articles; import json; a=fetch_articles(json.load(open('channels/right.json',encoding='utf-8'))['feeds']); print(len(a))" 2>&1 | Select-Object -Last 1
  Pop-Location
  if ("$probe" -match '^\d+$' -and [int]$probe -ge 10) { Ok "뉴스 RSS 수집 정상 ($probe건)" } else { Bad "뉴스 RSS 수집 실패: $probe" }
}
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 'https://api.telegram.org' | Out-Null; Ok "텔레그램 접속 가능" }
catch { if ($_.Exception.Response) { Ok "텔레그램 접속 가능" } else { Warn "텔레그램 접속 안 됨(실패 알림은 GitHub 쪽에서만 감)" } }

# 6) 작업 스케줄러에서 같은 시험(1분 뒤 1회 실행)
Say ""
Say "6. 작업 스케줄러 실행 시험 (약 1~2분 걸려요, 창을 닫지 마세요)"
$taskLog = Join-Path $LogDir '스케줄러시험.txt'
Remove-Item $taskLog -ErrorAction SilentlyContinue
$probeScript = Join-Path $LogDir 'scheduler_probe.ps1'
@"
`$ErrorActionPreference='Continue'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
`$o = @()
`$o += 'claude=' + [bool](Get-Command claude -ErrorAction SilentlyContinue)
`$o += 'git=' + [bool](Get-Command git -ErrorAction SilentlyContinue)
`$o += 'python=' + (& python --version 2>&1)
Set-Location `$env:TEMP
`$r = 'Reply with exactly: OK' | & claude -p --model haiku --output-format json --no-session-persistence 2>&1 | Out-String
try { `$j = `$r | ConvertFrom-Json; `$o += 'claude_p=' + `$j.result } catch { `$o += 'claude_p_fail=' + `$r.Trim() }
& git ls-remote $RepoUrl HEAD *> `$null; `$o += 'github=' + (`$LASTEXITCODE -eq 0)
`$o | Out-File -Encoding utf8 '$taskLog'
"@ | Out-File -Encoding utf8 $probeScript
$name = 'daily-briefing-점검(임시)'
try {
  $act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$probeScript`""
  $trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(65)
  $prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
  Register-ScheduledTask -TaskName $name -Action $act -Trigger $trg -Principal $prn -Force | Out-Null
  $ok = $false
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep 6; if (Test-Path $taskLog) { $ok = $true; break } }
  Start-Sleep 2
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  if ($ok) {
    $t = Get-Content $taskLog -Encoding UTF8
    $t | ForEach-Object { Say "     $_" }
    if (($t -join ' ') -match 'claude_p=.*OK' -and ($t -join ' ') -match 'github=True') { Ok "작업 스케줄러에서도 claude -p · GitHub 정상" }
    else { Bad "작업 스케줄러 환경에서 일부 실패(위 내용 확인)" }
  } else { Bad "작업 스케줄러 시험 결과가 3분 안에 안 나옴" }
} catch { Bad "작업 등록 실패(회사 정책으로 막혔을 수 있음): $($_.Exception.Message)" }

Say ""
if ($bad -eq 0) { Say "결과: 모두 정상 ✅  → 다음 단계(작업등록.bat) 진행 가능" }
else { Say "결과: 문제 $bad 건 ❌  → 이 파일 내용을 그대로 Claude 대화창에 붙여넣어 주세요" }
$lines | Out-File -Encoding utf8 $Report
Start-Process notepad.exe $Report
