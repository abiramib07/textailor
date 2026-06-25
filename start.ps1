# TexTailor launcher — opens Windows Terminal with two tabs
$backend  = 'D:\AI resume automater\start-backend.ps1'
$frontend = 'D:\AI resume automater\start-frontend.ps1'

$wtArgs = 'new-tab --title "BACKEND :8000" powershell -NoExit -File "' + $backend + '" ' +
          '; new-tab --title "FRONTEND :4200" powershell -NoExit -File "' + $frontend + '"'

Start-Process wt -ArgumentList $wtArgs

Write-Host ''
Write-Host 'Windows Terminal opened with 2 tabs:' -ForegroundColor Cyan
Write-Host '  Tab 1 [BACKEND :8000]   <- pipeline logs live here' -ForegroundColor Green
Write-Host '  Tab 2 [FRONTEND :4200]  <- Angular dev server' -ForegroundColor Magenta
Write-Host ''
Write-Host 'Browser opens automatically once Angular compiles (~10s).' -ForegroundColor Gray
