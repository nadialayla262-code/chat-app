"""A stand-in for Ollama's /api/embed: a deterministic bag-of-words vector, so search can be tested without a model.
Also answers /api/chat like fake_model.py, so one process serves both."""
import hashlib, json, math, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
DIM = 64
def embed(text):
    v = [0.0] * DIM
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 8) % 2 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            inp = body["input"]; inp = [inp] if isinstance(inp, str) else inp
            out = {"model": body["model"], "embeddings": [embed(t) for t in inp]}
        else:
            msgs = body["messages"]
            system = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
            remembered = ""
            if "What you remember" in system:
                facts = [l[2:] for l in system.split("What you remember", 1)[1].splitlines() if l.startswith("- ")]
                remembered = f" (remembers: {'; '.join(facts)})"
            out = {"message": {"role": "assistant", "content": f"<think>hmm</think>[{body['model']}|{len(msgs)} msgs] You said: {msgs[-1]['content']}{remembered}"}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
HTTPServer(("127.0.0.1", PORT), H).serve_forever()
