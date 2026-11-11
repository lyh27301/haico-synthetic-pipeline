"""Step 13f-4: keep the task state and the grader's state out of the agent's reach (stdlib only).

The agent's terminal runs as root in the same container as the MCP server, so file permissions cannot hide anything.
Instead:
  - the task file (env YAML + a per-run key) is staged at a random path and the MCP server deletes it on startup,
    before the agent's first action (the SDK starts the server once, while the agent initializes its tools);
  - the state dumps (pre.json, post.json, calls.jsonl, workspace_*.json) are sealed with that key, in a randomly named
    directory. The host unseals them after download; the in-container evaluator shim carries the key.
The key exists only on the host, in the MCP server's memory, and in the evaluator code uploaded after the run.

Sealing is a SHA-256 counter-mode keystream with an HMAC tag: enough to stop `cat` / `grep` / `find` from reading the
state, not a defence against an agent that reads the server process's memory."""
import hashlib, hmac, os

MAGIC = b"ADJS1"


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out, i = bytearray(), 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + i.to_bytes(8, "big")).digest(); i += 1
    return bytes(out[:n])


def seal(key: bytes, data: bytes) -> bytes:
    nonce = os.urandom(16)
    ct = bytes(a ^ b for a, b in zip(data, _stream(key, nonce, len(data))))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    return MAGIC + nonce + tag + ct


def unseal(key: bytes, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a sealed state file")
    nonce, tag, ct = blob[5:21], blob[21:53], blob[53:]
    if not hmac.compare_digest(tag, hmac.new(key, nonce + ct, hashlib.sha256).digest()):
        raise ValueError("sealed state file: bad tag")
    return bytes(a ^ b for a, b in zip(ct, _stream(key, nonce, len(ct))))
