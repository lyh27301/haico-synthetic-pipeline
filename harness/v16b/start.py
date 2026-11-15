"""Step 16b entrypoint of the agent image (root): network rules, server environment, server patch, then the server.

Network (H2): processes of user `agent` get no network at all. Loopback stays open to them except the agent-server's
own ports (8000-8002), so the agent cannot drive the root API. The server (root) keeps its connection to the model
endpoint, and so does the NPC helper, which `agent` can run only through `sudo chat_npc` (a fixed script). The rules
need the container's NET_ADMIN capability; `agent` has no capabilities and no sudo beyond that script. The result is
written to /var/lib/.oh16b/net.json; the harness refuses to run a task if the rules are not in place."""
import json
import os
import subprocess
import sys

ROOT = "/var/lib/.oh16b"
os.makedirs(ROOT, mode=0o700, exist_ok=True)
os.makedirs(f"{ROOT}/tmp", mode=0o700, exist_ok=True)

RULES = [["-A", "OUTPUT", "-o", "lo", "-p", "tcp", "--dport", "8000:8002", "-m", "owner", "--uid-owner", "agent",
          "-j", "REJECT"],
         ["-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"],
         ["-A", "OUTPUT", "-m", "owner", "--uid-owner", "agent", "-j", "REJECT"]]
net = {"ok": True, "errors": []}
for ipt in ("iptables", "ip6tables"):
    for r in RULES:
        p = subprocess.run([ipt, *r], capture_output=True, text=True)
        if p.returncode != 0:
            net["ok"] = net["ok"] and ipt == "ip6tables"   # IPv6 may be absent; IPv4 must hold
            net["errors"].append(f"{ipt} {' '.join(r)}: {p.stderr.strip()}")
net["rules"] = subprocess.run(["iptables", "-S", "OUTPUT"], capture_output=True, text=True).stdout
with open(f"{ROOT}/net.json", "w") as fh:
    json.dump(net, fh)

# the server's own environment: no TheAgentCompany leftovers, temp files in its private directory
for k in ("REDIS_OM_URL", "BOT_URL", "CREDENTIAL_FILE_PATH", "SCENARIOS_FILE_PATH"):
    os.environ.pop(k, None)
os.environ["PYTHONPATH"] = ""
os.environ["TMPDIR"] = f"{ROOT}/tmp"
sys.path.insert(0, "/opt/.oh16b")
import server_patch  # noqa: E402
server_patch.install()

from openhands.agent_server.__main__ import main  # noqa: E402
sys.argv = ["openhands.agent_server", *sys.argv[1:]]
main()
