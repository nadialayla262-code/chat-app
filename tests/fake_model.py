"""A stand-in for Ollama: echoes the last message, so worker logic can be tested without a GPU."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = body["messages"]
        out = {"message": {"role": "assistant", "content": f"<think>hmm</think>[{body['model']}|{len(msgs)} msgs] You said: {msgs[-1]['content']}"}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
HTTPServer(("127.0.0.1", PORT), H).serve_forever()
