# Step 16b agent image: the OAS agent-server image + our envs and MCP server (as harness/Dockerfile.agentdojo) + the
# step-16b harness changes. Built by harness/v16b/build.sh; tag openagentsafety-agentdojo16b:<sdk sha>-<content hash>.
#   - tools agents tried to install in earlier runs (step 15 H2 list), so tasks stay doable without network:
#     poppler-utils (pdftotext, pdfunite), qpdf, zip / unzip / 7z, sqlite3, jq; Python: pypdf, PyPDF2, openpyxl,
#     pandas, python-docx, reportlab, fpdf2, xlsxwriter, pdfplumber, tabulate. Mail clients (mutt, msmtp, ...) are
#     deliberately not installed.
#   - iptables (network rules), faketime (the task's date in the agent's terminal), sudo (only for chat_npc);
#   - user `agent` (uid 1000) runs the agent's terminal; harness files are root-only (mode 700);
#   - the agent-server's conversation store and bash events live in /var/lib/.oh16b (root, 700), VSCode off;
#   - TheAgentCompany leftovers removed: /utils, /npc defaults, REDIS / BOT / credential variables, the hosts entry
#     (the adapter no longer adds it).
ARG BASE
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils qpdf zip unzip p7zip-full sqlite3 jq \
      iptables faketime libfaketime sudo util-linux \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pypdf PyPDF2 openpyxl pandas python-docx reportlab fpdf2 xlsxwriter pdfplumber tabulate
RUN python -m venv /opt/agentdojo-venv \
 && /opt/agentdojo-venv/bin/pip install --no-cache-dir "mcp==1.26.0" "pydantic[email]>=2.7" pyyaml docstring-parser typing-extensions pypdf \
 && /opt/agentdojo-venv/bin/pip install --no-cache-dir --no-deps agentdojo==0.1.35
COPY recipe /opt/agentdojo/recipe
COPY gmail_suite /opt/agentdojo/gmail_suite
COPY sqldb_suite /opt/agentdojo/sqldb_suite
COPY evidence_suite /opt/agentdojo/evidence_suite
COPY medical_suite /opt/agentdojo/medical_suite
COPY finance_suite /opt/agentdojo/finance_suite
COPY commerce_suite /opt/agentdojo/commerce_suite
COPY harness/__init__.py harness/gmail_mcp_server.py harness/workspace_bridge.py harness/state_seal.py \
     harness/filegen.py harness/filetext.py harness/file_tools.py harness/ws_store.py /opt/agentdojo/harness/
RUN cd /opt/agentdojo/recipe && find . -maxdepth 1 -type f ! \( -name __init__.py -o -name profiles.py -o -name clock.py \
      -o -name '*_profile.py' -o -name gmail_task.py -o -name graders.py -o -name record_graders.py -o -name record_task.py \
      -o -name sqldb_graders.py -o -name sqldb_task.py \) -delete \
 && find /opt/agentdojo/recipe -mindepth 1 -type d -exec rm -rf {} + \
 && rm -f /opt/agentdojo/*_suite/smoke_test.py /opt/agentdojo/sqldb_suite/make_base.py \
 && find /opt/agentdojo -name __pycache__ -prune -exec rm -rf {} + \
 && /opt/agentdojo-venv/bin/python -c "import sys; sys.path.insert(0, '/opt/agentdojo'); sys.path.insert(0, '/opt/agentdojo/harness'); from recipe import profiles; import file_tools, filegen, filetext, ws_store; [profiles.get(n).build_runtime() for n in profiles.NAMES]; print('agentdojo envs ok')"
RUN rm -rf /utils /npc /instruction && mkdir -p /npc && chmod 700 /npc \
 && useradd -m -u 1000 -s /bin/bash agent \
 && mkdir -p /opt/.oh16b /var/lib/.oh16b \
 && mv /usr/local/bin/chat_npc /opt/.oh16b/chat_npc_real \
 && printf '#!/bin/sh\nexec sudo -n /opt/.oh16b/chat_npc_real "$@"\n' > /usr/local/bin/chat_npc && chmod 755 /usr/local/bin/chat_npc \
 && echo 'agent ALL=(root) NOPASSWD: /opt/.oh16b/chat_npc_real' > /etc/sudoers.d/chat_npc && chmod 440 /etc/sudoers.d/chat_npc
COPY harness/v16b/start.py harness/v16b/server_patch.py harness/v16b/agent-shell harness/ws_store.py harness/filetext.py /opt/.oh16b/
RUN chmod 700 /opt/.oh16b /opt/agentdojo /opt/agentdojo-venv /var/lib/.oh16b && chmod 700 /opt/.oh16b/agent-shell \
 && chmod 755 /opt/.oh16b/chat_npc_real
ENV OH_CONVERSATIONS_PATH=/var/lib/.oh16b/conversations OH_BASH_EVENTS_DIR=/var/lib/.oh16b/bash_events \
    OH_ENABLE_VSCODE=false PYTHONPATH= FAKETIME=+0
# the task's date (item 4): the agent's shell preloads libfaketime (agent-shell), which reads the per-task offset the
# harness writes to /etc/faketimerc; setuid programs (sudo for chat_npc) and root processes keep the real clock
ENTRYPOINT ["python", "/opt/.oh16b/start.py"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
