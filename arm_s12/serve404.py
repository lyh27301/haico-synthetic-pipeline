"""Answer 404 on the given ports for a while, so a harness client polling a killed agent-server (arm_s9/cost_watchdog.py)
gets "Remote conversation not found (404)" and ends the run at once instead of retrying until its 3600 s timeout."""
import sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def _r(self):
        self.send_response(404); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"detail":"Not Found"}')
    do_GET = do_POST = do_DELETE = do_PUT = _r
    def log_message(self, *a): pass
srvs=[ThreadingHTTPServer(("127.0.0.1",int(p)),H) for p in sys.argv[1:]]
for s in srvs: threading.Thread(target=s.serve_forever,daemon=True).start()
import time; time.sleep(int(__import__("os").environ.get("S404_SECONDS", "180")))
