Write-Host 'TexTailor BACKEND' -ForegroundColor Cyan
Write-Host 'Docs: http://localhost:8000/docs' -ForegroundColor Gray
Write-Host '---------------------------------' -ForegroundColor DarkGray
Set-Location 'D:\AI resume automater'
python -m uvicorn src.api:app --reload --reload-dir src --reload-exclude "*.db" --reload-exclude "*.db-*" --port 8000 --log-level info
