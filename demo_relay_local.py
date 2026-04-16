"""Local relay for demo.html - runs on laptop, forwards to VM Bridge via SSH."""
import http.server
import json
import subprocess
import tempfile
import os

PORT = 8889
SSH_KEY = r"C:\Users\manavsha\.ssh\oracle_cloud_nopass"
VM = "opc@80.225.205.232"

class DemoRelayHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
            recipient = payload.get("recipient", "919867782241@s.whatsapp.net")
            message = payload.get("message", "")

            # Write a temp Python script, SCP it, run it
            script = (
                "import json,urllib.request\n"
                f"data=json.dumps({{'recipient':'{recipient}','message':{json.dumps(message)}}}).encode('utf-8')\n"
                "req=urllib.request.Request('http://localhost:8080/api/send',data=data,"
                "headers={'Content-Type':'application/json; charset=utf-8'})\n"
                "resp=urllib.request.urlopen(req,timeout=10)\n"
                "print(resp.read().decode())\n"
            )
            
            tmp = os.path.join(tempfile.gettempdir(), "demo_send.py")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(script)

            # SCP to VM
            subprocess.run(
                ["scp", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", tmp, f"{VM}:/tmp/demo_send.py"],
                capture_output=True, timeout=15
            )

            # Run on VM
            result = subprocess.run(
                ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", VM, "python3 /tmp/demo_send.py"],
                capture_output=True, text=True, timeout=15
            )
            out = result.stdout.strip()

            if "success" in out.lower():
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode())
            else:
                raise Exception(f"Bridge: {out} {result.stderr}")
        except Exception as e:
            self.send_response(500)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        print(f"[DemoRelay] {args[0]}")

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), DemoRelayHandler)
    print(f"[DemoRelay] Running on http://localhost:{PORT}")
    print(f"[DemoRelay] demo.html SEND -> localhost:{PORT} -> SSH -> VM Bridge -> WhatsApp")
    server.serve_forever()
