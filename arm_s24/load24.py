"""Step 24 loader: the 46 v4.2-set0 tasks + the 2 step-23 cm-firmware-lock versions, with rules, description traps,
instruction (agent context + problem statement), starting environment (records + staged files), references.
Reads the main checkout (DATA); writes nothing."""
import json, re, sys
from pathlib import Path
DATA = Path("/Users/yanhanliu/overnight-gmail-dojo")
sys.path[:0] = [str(DATA / "grader"), str(DATA / "arm_s16b"), str(DATA / "harness"), str(DATA)]


def tasks():
    import gen_rules_set42 as S42
    rows, ctx = S42.the_set()
    idx = dict(json.loads((DATA / "grader/out/v4.2-set0/set.json").read_text())["tasks"])
    idx2 = json.loads((DATA / "grader/out/v4.2-s23/set.json").read_text())["tasks"]
    for t in idx2:
        r = json.loads((DATA / "arm_s23/bank/tasks" / f"{t}.json").read_text())
        ctx[t] = r.pop("_agent_context", ""); rows[t] = r
    idx.update(idx2)
    return rows, ctx, idx


def desc_traps(md: str) -> dict:
    sec = md.split("TRAPS", 1)[1].split("\nCOMPLETION", 1)[0] if "TRAPS" in md else ""
    out = {}
    for m in re.finditer(r"^(T\d+)\.\s*(.*?)(?=^T\d+\.|\Z)", sec, re.S | re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


# ---------------------------------------------------------------- corpus: instruction + starting environment
def _rid(rec, i):
    if not isinstance(rec, dict):
        return f"#{i}"
    for k in ("id", "key", "account"):
        if k in rec and isinstance(rec[k], (str, int)):
            return f"{k}={rec[k]}"
    for k, v in rec.items():
        if k.endswith("_id") and isinstance(v, (str, int)):
            return f"{k}={v}"
    if "table_name" in rec:
        return f"table_name={rec['table_name']}" + (f",column_name={rec['column_name']}" if "column_name" in rec else "")
    return f"#{i}"


def _flat(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _flat(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for j, v in enumerate(x):
            yield from _flat(v, f"{path}[{j}]")
    elif isinstance(x, str):
        yield path, x


def corpus(row, ctx_text):
    """[(kind, where, field, text)] kind in instruction / record / file / npc"""
    import gen_rules_set42 as S42
    import engine as E
    pre, ws = S42.P.initial(row)
    out = [("instruction", "agent_context", "", ctx_text or ""), ("instruction", "problem_statement", "", row["problem_statement"])]
    for c, recs in E.collections(pre).items():
        for i, r in enumerate(recs):
            for f, v in _flat(r):
                out.append(("record", f"{c} {_rid(r, i)}", f, v))
    for k, v in pre.items():   # scalar top-level env fields
        if isinstance(v, str):
            out.append(("record", "env", k, v))
    for p, v in ws.items():
        out.append(("file", p, "", v))
    for k in ("agent_profiles", "agent_scenarios"):
        for f, v in _flat(row.get(k) or []):
            out.append(("npc", k, f, v))
    return out, pre, ws


_TR = str.maketrans({"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', " ": " "})


def norm(s):
    return re.sub(r"\s+", " ", s.translate(_TR)).strip().lower()


def fragments(quote: str) -> list:
    """the quote as the rules give it, then its quoted parts / ;-separated parts (the rules join several sources)"""
    q = quote.strip()
    parts = re.findall(r"[“\"]([^“”\"]{6,})[”\"]", q)
    rest = re.sub(r"[“\"][^“”\"]{6,}[”\"]", "", q)
    if not parts:
        parts = [q]
    out = []
    for p in parts:
        out.append(p.strip())
    if re.search(r"common sense", rest + q, re.I):
        m = re.search(r"common sense:?.*", q, re.I | re.S)
        out.append(m.group(0).strip())
    return list(dict.fromkeys(x for x in out if x))


def search(frag, C):
    """exact hits, then normalized hits; [(level, kind, where, field)]"""
    hits = [("exact", k, w, f) for k, w, f, t in C if frag in t]
    if hits:
        return hits
    nf = norm(frag)
    return [("normalized", k, w, f) for k, w, f, t in C if nf in norm(t)]


def best_partial(frag, C):
    """longest common block of the normalized fragment in any unit (for quotes not found verbatim)"""
    import difflib
    nf = norm(frag); best = (0, None)
    for k, w, f, t in C:
        nt = norm(t)
        if not nt:
            continue
        m = difflib.SequenceMatcher(None, nf, nt, autojunk=False).find_longest_match(0, len(nf), 0, len(nt))
        if m.size > best[0]:
            best = (m.size, (k, w, f, nf[m.a:m.a + m.size]))
    return best
