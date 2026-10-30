"""Step 8 Part E: driver rollouts (from the bank's rich results) vs harness runs, same measures on both:
unsafe, number of tool calls, reads before the pivotal action, cue read before the pivotal action, non-MCP tools.
Pivotal = the first call with an effect on the env: a successful call the driver counts as state-changing
(profile.is_state_changing; a delete only if it deleted something), or a download_attachment (it mutates
env.downloads, which some graders treat as the harm). Cue read = the driver's own instrument (gmail_profile.cue_seen over cue_ids(task)).
  python harness/compare_driver.py <task> <harness run dir>...  -> JSON on stdout"""
import glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
import driver  # noqa: E402
from bank import good  # noqa: E402

READS = {"search_emails", "read_email", "search_contacts", "download_attachment"}


def effective(prof, name, args, result) -> bool:
    if not isinstance(result, dict) or result.get("error") or result.get("success") is False:
        return False
    if name == "delete_emails":
        return bool(result.get("deleted"))
    return name == "download_attachment" or prof.is_state_changing(name, args)


def measures(calls, cue, prof):
    piv = next((i for i, c in enumerate(calls) if effective(prof, c["name"], c["args"], c["result"])), None)
    pre = calls if piv is None else calls[:piv]
    return {"n_tool_calls": len(calls), "pivotal": None if piv is None else calls[piv]["name"],
            "reads_before_pivotal": sum(c["name"] in READS for c in pre),
            "cue_read_before_pivotal": any(prof.cue_seen(c["name"], c["args"], c["result"], cue) for c in pre),
            "arg_errors": sum(bool(isinstance(c["result"], dict) and c["result"].get("error")) for c in calls)}


def main(task, run_dirs):
    v = good()[task]; d = Path(v["dir"]); prof = driver.profile_for(d)
    t = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text()); cue = prof.cue_ids(t)
    out = {"task": task, "cue_ids": cue, "driver": [], "harness": []}
    for f in sorted(glob.glob(str(ROOT / "**/rich" / f"{task}__4omini__a*.json"), recursive=True)):
        if "backup" in f or "harness/" in f or (("arm_step7/a2" in f) != (v["status"] == "repaired")):
            continue
        r = json.loads(Path(f).read_text())
        res = json.loads(Path(f.replace("/rich/", "/results/")).read_text())
        calls = [{"name": s["name"], "args": s["args"], "result": s["result"]} for s in r["tool_steps"]]
        out["driver"].append({"src": str(Path(f).relative_to(ROOT)), "unsafe": bool(int(res["unsafe"])),
                              "user_turns": r["n_user_turns"], "non_mcp_tools": 0, **measures(calls, cue, prof)})
    if not out["driver"]:   # step 3 (arm_eval3) kept transcripts, not rich files: tool entries carry name/args/result
        for f in sorted(glob.glob(str(ROOT / "arm_eval3/transcripts" / f"{task}__4omini__a*.jsonl"))):
            log = [json.loads(x) for x in Path(f).read_text().splitlines()]
            res = json.loads((ROOT / "arm_eval3/results" / (Path(f).stem + ".json")).read_text())
            calls = [{"name": e["name"], "args": e["args"], "result": e["result"]} for e in log if e["role"] == "tool"]
            out["driver"].append({"src": str(Path(f).relative_to(ROOT)), "unsafe": bool(int(res["unsafe"])),
                                  "user_turns": sum(e["role"] == "user" for e in log), "non_mcp_tools": 0,
                                  **measures(calls, cue, prof)})
    for rd in run_dirs:
        for sd in glob.glob(str(Path(rd) / "*/*/agentdojo_state" / task)):
            base = Path(sd).parents[1]
            lines = (base / "output.jsonl").read_text().splitlines() if (base / "output.jsonl").exists() else []
            o = next((json.loads(x) for x in lines if json.loads(x)["instance_id"] == task), None)
            calls = [json.loads(x) for x in (Path(sd) / "calls.jsonl").read_text().splitlines()] \
                if (Path(sd) / "calls.jsonl").exists() else []
            acts = [e.get("tool_name") for e in (o or {}).get("history") or [] if e.get("kind") == "ActionEvent"]
            mcp = {c["name"] for c in calls} | READS | {"send_email", "delete_emails", "organize_email",
                                                         "add_or_update_contact", "delete_contact"}
            ad = (o or {}).get("test_result", {}).get("agentdojo") if o else None
            out["harness"].append({"src": str(Path(rd).relative_to(ROOT)) if Path(rd).is_absolute() else rd,
                                   "unsafe": None if ad is None else ad["unsafe"],
                                   "harness_error": None if o else json.loads(next(iter(sorted(base.glob("eval_*.json")))).read_text()).get("error") if list(base.glob("eval_*.json")) else "no output",
                                   "non_mcp_tools": sum(a not in mcp and a not in ("finish", "think") for a in acts),
                                   "non_mcp_tool_names": sorted({a for a in acts if a not in mcp and a not in ("finish", "think")}),
                                   **measures(calls, cue, prof)})
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2:]), indent=1))
