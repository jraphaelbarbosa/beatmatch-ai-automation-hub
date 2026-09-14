import os
import subprocess
import sys
from threading import Thread

from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Load environment variables from parent folder
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(PROJECT_DIR, ".env"))

app = Flask(__name__)

# Security Token (Must be set via HOST_RUNNER_TOKEN env var)
API_TOKEN = os.getenv("HOST_RUNNER_TOKEN", "")
if not API_TOKEN:
    print("⚠️  WARNING: HOST_RUNNER_TOKEN not set in .env. All requests will be rejected.")
    API_TOKEN = "UNCONFIGURED_TOKEN_CHANGE_ME"

# Resolve python binary path from host virtual environment
PYTHON_BIN = os.path.join(PROJECT_DIR, "venv", "bin", "python")
if not os.path.exists(PYTHON_BIN):
    PYTHON_BIN = sys.executable

SCRIPTS = {
    "youtube_scraper": os.path.join(PROJECT_DIR, "src", "scrapers", "youtube_scraper.py"),
    "apify_twitter": os.path.join(PROJECT_DIR, "src", "scrapers", "apify_twitter.py"),
    "spotify_miner": os.path.join(PROJECT_DIR, "src", "scrapers", "spotify_miner.py"),
    "spotify_resolver": os.path.join(PROJECT_DIR, "src", "enrichers", "spotify_resolver.py"),
    "instagram_finder": os.path.join(PROJECT_DIR, "src", "enrichers", "instagram_finder.py"),
    "sipa_cleaner": os.path.join(PROJECT_DIR, "src", "quality", "sipa_cleaner.py"),
    "export_to_monday": os.path.join(PROJECT_DIR, "src", "utils", "export_to_monday.py"),
    "reconciler": os.path.join(PROJECT_DIR, "src", "reconciler.py"),
}

def run_script_async(script_name, script_path, args=None):
    cmd = [PYTHON_BIN, script_path]
    if args:
        cmd.extend(args)
    
    # Logs folder
    log_dir = os.path.join(PROJECT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"{script_name}.log")
    
    # Get current timestamp for logging
    try:
        timestamp = subprocess.check_output(["date"]).decode().strip()
    except Exception:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    with open(log_file_path, "a") as log_file:
        log_file.write(f"\n--- Execution triggered at {timestamp} ---\n")
        log_file.flush()
        
        # Execute using subprocess.Popen to run in background
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            cwd=PROJECT_DIR
        )

@app.before_request
def verify_token():
    # Exclude status check from authentication
    if request.path == "/status":
        return None
        
    token = request.headers.get("Authorization")
    if not token or token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "running",
        "project_dir": PROJECT_DIR,
        "python_bin": PYTHON_BIN
    }), 200

@app.route("/run/<script_name>", methods=["POST"])
def run_script(script_name):
    if script_name not in SCRIPTS:
        return jsonify({
            "error": "Script not found",
            "available_scripts": list(SCRIPTS.keys())
        }), 400
        
    script_path = SCRIPTS[script_name]
    if not os.path.exists(script_path):
        return jsonify({
            "error": f"Script file does not exist locally at {script_path}"
        }), 500
        
    req_data = request.get_json(silent=True) or {}
    args = req_data.get("args", [])
    
    # Run script asynchronously in the background
    Thread(target=run_script_async, args=(script_name, script_path, args)).start()
    
    return jsonify({
        "status": "queued",
        "script": script_name,
        "log_file": f"logs/{script_name}.log"
    }), 202

if __name__ == "__main__":
    # Bind to 0.0.0.0 internally, port 5000. 
    # External access is blocked by default by GCP VM Firewall, ensuring security.
    app.run(host="0.0.0.0", port=5000, debug=False)
