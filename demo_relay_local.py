"""
Demo Relay — runs on Neo's laptop during live demo.

SEND on demo.html -> relay does 3 things:
  1. Deletes live.html from GitHub (fresh start)
  2. Queues @trinity task on VM
  3. Sends message to Neo's WhatsApp (audience sees it on phone)

Then Trinity (Opus) picks it up, talks to Lobo, builds live.html, pushes.
demo.html polls for live.html and reveals the link when it appears.

Start before the meeting:
    python demo_relay_local.py
"""

import http.server
import json
import subprocess
import os
import tempfile

PORT = 8889
VM = "opc@80.225.205.232"
KEY = os.path.expanduser("~") + "\\.ssh\\oracle_cloud_nopass"
CHAT_JID = "919867782241@s.whatsapp.net"
SENDER = "919867782241"
SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))


def ssh_run(command):
    return subprocess.run(
        ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", VM, command],
        capture_output=True, text=True, timeout=20
    )


def scp_and_run(script_content):
    tmp = os.path.join(tempfile.gettempdir(), "demo_send.py")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(script_content)
    subprocess.run(
        ["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no", tmp, f"{VM}:/tmp/demo_send.py"],
        capture_output=True, text=True, timeout=15
    )
    return ssh_run("python3 /tmp/demo_send.py")


def delete_live_html():
    """Delete live.html from GitHub so the poll starts fresh."""
    live_path = os.path.join(SITE_DIR, "live.html")
    if os.path.exists(live_path):
        os.remove(live_path)
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, text=True, cwd=SITE_DIR
        )
        result = subprocess.run(
            ["git", "commit", "-m", "Demo: remove live.html for fresh build"],
            capture_output=True, text=True, cwd=SITE_DIR
        )
        result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=SITE_DIR, timeout=30
        )
        if result.returncode == 0:
            print("[RELAY] live.html deleted from GitHub")
        else:
            print("[RELAY] git push failed:", result.stderr)
    else:
        print("[RELAY] live.html already absent, skipping delete")


class RelayHandler(http.server.BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        message = body.get("message", "")

        # Step 1: Delete live.html from GitHub (fresh start for poll)
        print("[RELAY] Step 1: Deleting live.html from GitHub...")
        delete_live_html()

        # Step 2: Queue @trinity task on VM
        safe_msg = message.replace("'", "'\\''")
        queue_result = ssh_run(
            f"python3 /home/opc/PROJECT/ZION/trinity_queue.py add "
            f"'{CHAT_JID}' '{safe_msg}' '{SENDER}'"
        )
        if queue_result.returncode != 0:
            self._reply(False, "Queue failed: " + queue_result.stderr)
            print("[RELAY] Step 2 FAILED:", queue_result.stderr)
            return

        task_info = queue_result.stdout.strip()
        print(f"[RELAY] Step 2: Task queued: {task_info}")

        # Step 3: Send message to Neo's WhatsApp (audience sees it)
        send_script = (
            "import urllib.request, json\n"
            f"data = json.dumps({{'recipient': {repr(CHAT_JID)}, 'message': {repr(message)}}}).encode()\n"
            "req = urllib.request.Request('http://localhost:8080/api/send', data=data,\n"
            "    headers={'Content-Type': 'application/json; charset=utf-8'})\n"
            "resp = urllib.request.urlopen(req)\n"
            "print(resp.read().decode())\n"
        )
        wa_result = scp_and_run(send_script)
        if wa_result.returncode == 0:
            print("[RELAY] Step 3: WhatsApp message sent")
        else:
            print("[RELAY] Step 3: WhatsApp failed (task still queued)")

        self._reply(True, task_info)

    def _reply(self, success, msg):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"success": success, "info": msg}).encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), RelayHandler)
    print(f"[RELAY] Demo relay on http://localhost:{PORT}")
    print("[RELAY] SEND flow: delete live.html -> queue task -> send WhatsApp")
    print("[RELAY] Open demo.html -> type anything -> SEND")
    server.serve_forever()
