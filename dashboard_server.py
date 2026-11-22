import http.server
import socketserver
import json
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone, timedelta
import threading
import time

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # Disable caching for API development
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        # Enable CORS for file:// protocol support
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/data':
            self.handle_get_data()
        else:
            super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/scan':
            self.handle_run_scan()
        elif parsed_url.path == '/api/distribute':
            self.handle_run_distribute()
        elif parsed_url.path == '/api/save_env':
            self.handle_save_env()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_get_data(self):
        data = {
            "status": "ready",
            "cron_time": "12:00 PM IST (Daily)",
            "env_status": {},
            "candidates": [],
            "history": [],
            "latest_report": ""
        }

        # 1. Check ENV status (which variables are configured)
        env_keys = ["NOTION_TOKEN", "NOTION_DATABASE_ID", "GOOGLE_DOCS_FOLDER_ID", "GOOGLE_SHEETS_SPREADSHEET_ID"]
        env_file = os.path.join(DIRECTORY, ".env")
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if k in env_keys:
                        data["env_status"][k] = {
                            "configured": len(v) > 0,
                            "masked": v[:4] + "..." + v[-4:] if len(v) > 8 else "****"
                        }
        
        for k in env_keys:
            if k not in data["env_status"]:
                data["env_status"][k] = {"configured": False, "masked": ""}

        # 2. Read candidates.json
        candidates_file = os.path.join(DIRECTORY, "candidates.json")
        if os.path.exists(candidates_file):
            try:
                with open(candidates_file, 'r', encoding='utf-8') as f:
                    data["candidates"] = json.load(f)
            except Exception as e:
                data["candidates_error"] = str(e)

        # 3. Read history.json
        history_file = os.path.join(DIRECTORY, "history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data["history"] = json.load(f)
            except Exception as e:
                data["history_error"] = str(e)

        # 4. Read latest report
        reports_dir = os.path.join(DIRECTORY, "reports")
        if os.path.exists(reports_dir):
            files = [f for f in os.listdir(reports_dir) if f.startswith("report_") and f.endswith(".md")]
            if files:
                files.sort(reverse=True)
                latest_report_file = os.path.join(reports_dir, files[0])
                try:
                    with open(latest_report_file, 'r', encoding='utf-8') as f:
                        data["latest_report"] = f.read()
                        data["latest_report_name"] = files[0]
                except Exception as e:
                    data["latest_report_error"] = str(e)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def handle_run_scan(self):
        try:
            # Find python runtime
            python_path = r"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
            if not os.path.exists(python_path):
                python_path = "python"
                
            script_path = os.path.join(DIRECTORY, "run_scan.py")
            result = subprocess.run([python_path, script_path], capture_output=True, text=True, check=True)
            
            response = {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.CalledProcessError as e:
            response = {
                "success": False,
                "error": f"Process exited with code {e.returncode}",
                "stdout": e.stdout,
                "stderr": e.stderr
            }
        except Exception as e:
            response = {
                "success": False,
                "error": str(e)
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_run_distribute(self):
        try:
            # Find python runtime
            python_path = r"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
            if not os.path.exists(python_path):
                python_path = "python"
                
            script_path = os.path.join(DIRECTORY, "distribute_report.py")
            result = subprocess.run([python_path, script_path], capture_output=True, text=True, check=True)
            
            response = {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.CalledProcessError as e:
            response = {
                "success": False,
                "error": f"Process exited with code {e.returncode}",
                "stdout": e.stdout,
                "stderr": e.stderr
            }
        except Exception as e:
            response = {
                "success": False,
                "error": str(e)
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_save_env(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        try:
            params = json.loads(post_data)
            
            # Read current env to preserve comments or other keys
            env_file = os.path.join(DIRECTORY, ".env")
            current_env = {}
            if os.path.exists(env_file):
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                for line in lines:
                    if '=' in line and not line.strip().startswith('#'):
                        k, v = line.split('=', 1)
                        current_env[k.strip()] = v.strip()
            
            # Merge new params
            for k, v in params.items():
                current_env[k] = v
                
            # Write back
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write("# Generated by DSB Command Center\n")
                for k, v in current_env.items():
                    f.write(f"{k}={v}\n")
            
            # Update local data.js script for file:// protocol support
            update_data_js()
                    
            response = {"success": True}
        except Exception as e:
            response = {"success": False, "error": str(e)}

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

def update_data_js():
    import json
    directory = DIRECTORY
    data = {
        "status": "ready",
        "cron_time": "12:00 PM IST (Daily)",
        "env_status": {},
        "candidates": [],
        "history": [],
        "latest_report": "",
        "latest_report_name": ""
    }
    
    # Read Env Status
    env_keys = ["NOTION_TOKEN", "NOTION_DATABASE_ID", "GOOGLE_DOCS_FOLDER_ID", "GOOGLE_SHEETS_SPREADSHEET_ID"]
    env_file = os.path.join(directory, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if k in env_keys:
                        data["env_status"][k] = {
                            "configured": len(v) > 0,
                            "masked": v[:4] + "..." + v[-4:] if len(v) > 8 else "****"
                        }
        except Exception:
            pass
            
    for k in env_keys:
        if k not in data["env_status"]:
            data["env_status"][k] = {"configured": False, "masked": ""}
            
    # Read candidates.json
    candidates_file = os.path.join(directory, "candidates.json")
    if os.path.exists(candidates_file):
        try:
            with open(candidates_file, 'r', encoding='utf-8') as f:
                data["candidates"] = json.load(f)
        except Exception:
            pass
            
    # Read history.json
    history_file = os.path.join(directory, "history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data["history"] = json.load(f)
        except Exception:
            pass
            
    # Read latest report
    reports_dir = os.path.join(directory, "reports")
    if os.path.exists(reports_dir):
        try:
            files = [f for f in os.listdir(reports_dir) if f.startswith("report_") and f.endswith(".md")]
            if files:
                files.sort(reverse=True)
                latest_report_file = os.path.join(reports_dir, files[0])
                with open(latest_report_file, 'r', encoding='utf-8') as f:
                    data["latest_report"] = f.read()
                    data["latest_report_name"] = files[0]
        except Exception:
            pass
            
    data_js_path = os.path.join(directory, "data.js")
    try:
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(f"window.DSB_DATA = {json.dumps(data, indent=2, ensure_ascii=False)};\n")
        print(f"Successfully updated local data script: {data_js_path}")
    except Exception as e:
        print(f"Error updating data.js: {e}")

def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def start_scheduler():
    def scheduler_loop():
        print("[Scheduler] Started background daily scan scheduler thread.")
        while True:
            try:
                # Get current time in IST (UTC + 5:30)
                now_utc = datetime.now(timezone.utc)
                ist_offset = timedelta(hours=5, minutes=30)
                now_ist = now_utc + ist_offset
                
                today_str = now_ist.strftime("%Y-%m-%d")
                last_run_file = os.path.join(DIRECTORY, "last_scan_date.txt")
                
                already_run = False
                if os.path.exists(last_run_file):
                    try:
                        with open(last_run_file, "r") as f:
                            if f.read().strip() == today_str:
                                already_run = True
                    except Exception:
                        pass
                
                # Trigger the scan if it's 6:00 PM IST (18:00) or later, and it hasn't run yet today
                if not already_run and now_ist.hour >= 18:
                    print(f"[Scheduler] Triggering daily scan automatically (current time: {now_ist.strftime('%I:%M %p')} IST)")
                    python_path = r"C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
                    if not os.path.exists(python_path):
                        python_path = "python"
                    script_path = os.path.join(DIRECTORY, "run_scan.py")
                    
                    result = subprocess.run([python_path, script_path], capture_output=True, text=True)
                    if result.returncode == 0:
                        try:
                            with open(last_run_file, "w") as f:
                                f.write(today_str)
                            print(f"[Scheduler] Daily scan completed successfully and logged for {today_str}.")
                        except Exception as write_err:
                            print(f"[Scheduler] Error saving last scan date: {write_err}")
                    else:
                        print(f"[Scheduler] Daily scan process failed: {result.stderr}")
            except Exception as e:
                print(f"[Scheduler] Error in scheduler loop: {e}")
            time.sleep(30) # check every 30 seconds

    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

def main():
    # Start the background scheduler for automatic daily scans
    start_scheduler()
    
    handler = DashboardHandler
    # Allow port reuse to avoid 'Address already in use' errors
    socketserver.TCPServer.allow_reuse_address = True
    local_ip = get_local_ip()
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print("==========================================================")
        print(" DSB Command Center Server is Running!")
        print(f" Local Access: http://localhost:{PORT}")
        if local_ip != "127.0.0.1":
            print(f" LAN Access:   http://{local_ip}:{PORT}")
        print("==========================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    main()
