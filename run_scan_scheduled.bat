@echo off
cd /d "d:\ANTIGRAVITY Stock REPORT\Page Content Scans"
"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run_scan.py > task_log.log 2>&1
"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" auto_compile_api.py >> task_log.log 2>&1
"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" distribute_report.py >> task_log.log 2>&1

