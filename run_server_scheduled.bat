@echo off
cd /d "d:\ANTIGRAVITY Stock REPORT\Page Content Scans"
"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -u dashboard_server.py > server_log.log 2>&1
