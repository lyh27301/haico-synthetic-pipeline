"""Step 13h: hazard exposure. Shared helpers for arm_s13/gen_exposure.py and arm_s13/exposure13h.py.

A run is `exposed` if some TOOL RESULT of the run contains one of the task's exposure matchers
(arm_s13/exposure/<task>.json). The agent's own text never counts:
  - steps of finish / think / task_tracker / terminate, and file_editor create / str_replace / insert / undo_edit
    (their results echo what the agent wrote) are skipped;
  - a match in a step whose own arguments contain the matcher is skipped (the result echoes the agent's text, e.g. a
    sent email or an `echo`).
Matching: case-insensitive substring after normalisation (JSON results re-dumped unescaped, escaped newlines / tabs /
quotes removed, whitespace collapsed). Matchers are concrete strings only (no regexes)."""
import glob, io, json, re, subprocess, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"; EXPO = S13 / "exposure"
FILES = ROOT / "arm_hf/out_v08/files"
STEP_DIRS = {"step13f": S13 / "steps", "v0.8": ROOT / "arm_v08/analysis/steps", "v0.9": ROOT / "arm_v09/analysis/steps",
             "v0.10": ROOT / "arm_v10/analysis/steps"}
OUTCOMES = {"step13f": S13 / "outcomes_record.jsonl", "v0.8": ROOT / "arm_v08/analysis/outcomes_v08.jsonl",
            "v0.9": ROOT / "arm_v09/analysis/outcomes_v09.jsonl",
            "v0.10": ROOT / "arm_v10/analysis/outcomes_v09.jsonl"}   # step 13j re-roll of the repaired tasks
AGENT_TEXT_TOOLS = {"finish", "think", "thought", "task_tracker", "terminate"}
FE_WRITE = {"create", "str_replace", "insert", "undo_edit"}


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def norm(x) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    try:
        v = json.loads(s)
        if isinstance(v, (dict, list)):
            s = json.dumps(v, ensure_ascii=False, default=str)
    except (ValueError, TypeError):
        pass
    s = s.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ").replace('\\"', '"').replace("\\'", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


def bank_rows() -> dict:
    return {r["instance_id"]: r for r in jl(ROOT / "arm_v08/bank_v08.jsonl")}


def scenario(t, row) -> dict:
    """The scenario file of a task (references, cue marker, notes): the copy whose problem statement matches the bank."""
    cands = [Path(f) for f in glob.glob(str(ROOT / f"arm_*/tasks/{t}/scenario.json"))]
    best = None
    for f in sorted(cands, key=lambda f: ("arm_s13j" not in str(f), "arm_s12" not in str(f), str(f))):   # 13j repairs first
        s = json.loads(f.read_text())
        if best is None:
            best = s
        if norm(s.get("problem_statement", "")) == norm(row["problem_statement"]):
            return s
    return best or {}


def file_text(p: Path) -> str:
    """Readable text of a staged file (what an agent could see by reading / unpacking it)."""
    b = p.read_bytes(); ext = p.suffix.lower()
    try:
        if ext in (".docx", ".xlsx", ".pptx", ".zip"):
            z = zipfile.ZipFile(io.BytesIO(b)); parts = []
            for n in z.namelist():
                if ext == ".zip":
                    parts.append(n)
                d = z.read(n)
                if n.endswith((".xml", ".txt", ".csv", ".md", ".json", ".pem", ".env", ".yaml", ".yml", ".log")) or ext == ".zip":
                    try:
                        t = d.decode("utf-8")
                    except UnicodeDecodeError:
                        if n.lower().endswith((".docx", ".xlsx")):
                            t = file_text_bytes(d, Path(n).suffix.lower())
                        else:
                            continue
                    parts.append(re.sub(r"<[^>]+>", " ", t) if n.endswith(".xml") else t)
            return "\n".join(parts)
        if ext == ".pdf":
            try:
                return subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, timeout=20).stdout
            except (OSError, subprocess.SubprocessError):   # no pdftotext: the literal strings of the PDF
                return " ".join(x.decode("latin-1") for x in re.findall(rb"\(([^()]{3,})\)", b))
        if ext == ".png":
            return ""
        return b.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return b.decode("latin-1", "replace")


def file_text_bytes(d: bytes, ext: str) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(d))
        return "\n".join(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace")) for n in z.namelist()
                         if n.endswith(".xml"))
    except Exception:  # noqa: BLE001
        return ""


def staged_files(t) -> dict:
    d = FILES / t
    return {str(p.relative_to(d)): file_text(p) for p in sorted(d.rglob("*")) if p.is_file()} if d.exists() else {}


def results(steps):
    """(step index, tool, normalised result, normalised args) of every tool result that is not the agent's own text."""
    for s in steps:
        tool = str(s.get("tool") or ""); args = s.get("args") or {}
        if tool in AGENT_TEXT_TOOLS:
            continue
        if tool == "file_editor" and str(args.get("command")) in FE_WRITE:
            continue
        obs = s.get("observation")
        if obs is None:
            continue
        yield s.get("step"), tool, norm(obs), norm(args)


def exposure(steps, matchers) -> dict:
    """{exposed, step (first exposing step), matchers hit}."""
    ms = [norm(m) for m in matchers]; first = None; hit = set()
    for i, tool, r, a in results(steps):
        for m, raw in zip(ms, matchers):
            if m and m in r and m not in a:
                hit.add(raw)
                first = i if first is None else first
    return {"exposed": first is not None, "step": first, "matchers_hit": sorted(hit)}


def load_runs() -> list:
    """Every stored run with its source, outcome fields, contamination flag and steps path."""
    import sys
    sys.path.insert(0, str(ROOT / "arm_v09"))
    import analyze_v09   # hidden-state scan (old /agentdojo paths + the v0.8 sealed paths)
    out = []
    for src, f in OUTCOMES.items():
        for o in jl(f) if Path(f).exists() else []:
            if "crash" in o:
                continue
            p = STEP_DIRS[src] / f"{o['task']}__{o['agent']}__r{o['run']}.json"
            if src == "step13f":
                cont = bool(o.get("contaminated"))
            elif src in ("v0.9", "v0.10"):
                cont = bool((o.get("hidden") or {}).get("contaminated"))
            else:
                cont = bool(analyze_v09.hidden(json.loads(p.read_text()))["contaminated"]) if p.exists() else False
            out.append(o | {"source": src, "steps_path": str(p), "contaminated": cont})
    # runs of record (the bank_v08 environment): v0.8 and v0.9 runs; step-13f runs of the tasks that were not
    # re-rolled in v0.8 and whose slot was not re-run in v0.8
    rer = set((ROOT / "arm_v08/ids_v08.txt").read_text().split())
    slots = {(o["task"], o["agent"], o["run"]) for o in out if o["source"] == "v0.8" and o.get("slot")}
    # step 13j: a task repaired to task_version 0.10 has only its v0.10 runs of record (older runs are of the old version)
    rep = {t for t, r in bank_rows().items() if r.get("task_version") == "0.10"}
    for o in out:
        o["of_record"] = o["source"] != "step13f" or (o["task"] not in rer and (o["task"], o["agent"], o["run"]) not in slots)
        if o["task"] in rep:
            o["of_record"] = o["source"] == "v0.10"
    return out


def hazard_texts(spec_records, recs, matchers=()) -> list:
    """The text right around the cue in the hazard records (the 30 characters before and after each matcher
    occurrence), to tell a run that never received the cue's context (blind) from one that received it but no matcher
    fired (a rule gap, e.g. a different formatting of the same sentence)."""
    out = []
    for h in spec_records:
        v = recs.get(h)
        if v is None:
            continue
        t = norm(v)
        for m in map(norm, matchers):
            i = t.find(m)
            while m and i >= 0:
                for w in (t[max(0, i - 30):i], t[i + len(m):i + len(m) + 30]):
                    w = w.strip(' ,;:"\'{}[]')
                    if len(w) >= 12:
                        out.append(w)
                i = t.find(m, i + 1)
    return sorted(set(out))


def saw_hazard_text(steps, texts) -> bool:
    return any(t in r and t not in a for _, _, r, a in results(steps) for t in texts)
