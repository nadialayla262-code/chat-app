"""A stand-in IMAP server that serves one mbox file, read-only. Just enough for imaplib and handi_mail.py:
CAPABILITY, LOGIN, SELECT, SEARCH ALL, FETCH n (BODY.PEEK[]), LOGOUT. Plain TCP, no TLS: test use only."""
import mailbox, socketserver, sys
PORT = int(sys.argv[1]); MBOX = sys.argv[2]
MESSAGES = [bytes(m) for m in mailbox.mbox(MBOX)]

class H(socketserver.StreamRequestHandler):
    def send(self, line): self.wfile.write(line + b"\r\n")
    def handle(self):
        self.send(b"* OK fake IMAP ready")
        while True:
            raw = self.rfile.readline()
            if not raw: return
            parts = raw.strip().split(b" ", 2)
            tag, cmd = parts[0], parts[1].upper()
            arg = parts[2] if len(parts) > 2 else b""
            if cmd == b"CAPABILITY":
                self.send(b"* CAPABILITY IMAP4rev1"); self.send(tag + b" OK done")
            elif cmd == b"LOGIN":
                self.send(tag + b" OK logged in")
            elif cmd == b"SELECT" or cmd == b"EXAMINE":
                self.send(b"* %d EXISTS" % len(MESSAGES)); self.send(b"* FLAGS ()"); self.send(tag + b" OK [READ-ONLY] selected")
            elif cmd == b"SEARCH":
                self.send(b"* SEARCH " + b" ".join(str(i + 1).encode() for i in range(len(MESSAGES)))); self.send(tag + b" OK search done")
            elif cmd == b"FETCH":
                n = int(arg.split()[0]); body = MESSAGES[n - 1]
                self.wfile.write(b"* %d FETCH (BODY[] {%d}\r\n" % (n, len(body))); self.wfile.write(body); self.send(b")"); self.send(tag + b" OK fetch done")
            elif cmd == b"LOGOUT":
                self.send(b"* BYE"); self.send(tag + b" OK bye"); return
            elif cmd == b"NOOP":
                self.send(tag + b" OK")
            else:
                self.send(tag + b" BAD unsupported")

socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H).serve_forever()
