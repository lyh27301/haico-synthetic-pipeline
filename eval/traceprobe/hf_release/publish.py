"""Publish the converted TraceProbe eval set to the HF Hub as yanhanliu/traceprobe_oas (public), tag v0.1.
Uploads data/test.jsonl (eval/traceprobe/traceprobe_oas.jsonl: v1.1 schema + provenance columns; no rollout results,
no analysis fields), the dataset card (README.md) and TraceProbe's MIT LICENSE. The token comes from the env or the
cached login.
  .venv/bin/python eval/traceprobe/hf_release/publish.py"""
import json, shutil, tempfile
from pathlib import Path

from huggingface_hub import HfApi

HERE = Path(__file__).resolve().parent
REPO, TAG = "yanhanliu/traceprobe_oas", "v0.1"
COLS = ["instance_id", "problem_statement", "dependencies", "checkpoints", "agent_profiles", "agent_scenarios",
        "environment", "npcs", "has_workspace", "workspace_files", "has_utils", "utils_files", "evaluator_code",
        "github_url", "toolkit", "max_iterations", "source", "traceprobe_id", "tp_track", "tp_family", "tp_difficulty",
        "tp_risk_source", "tp_block_point", "tp_harm_locus", "tp_tools_enabled", "tp_files", "tp_meta"]


def main():
    rows = [json.loads(l) for l in (HERE.parent / "traceprobe_oas.jsonl").read_text().splitlines()]
    assert len(rows) == 116 and all(set(r) == set(COLS) for r in rows), "unexpected rows / columns"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); (d / "data").mkdir()
        (d / "data/test.jsonl").write_text("".join(json.dumps({c: r[c] for c in COLS}) + "\n" for r in rows))
        for f in ("README.md", "LICENSE"):
            shutil.copy(HERE / f, d / f)
        api = HfApi()
        api.create_repo(REPO, repo_type="dataset", private=False, exist_ok=True)
        api.upload_folder(folder_path=str(d), repo_id=REPO, repo_type="dataset",
                          commit_message="traceprobe_oas v0.1: 116 TraceProbe scenarios in OAS format (eval only)")
        api.create_tag(REPO, tag=TAG, repo_type="dataset", exist_ok=True)
    print(f"https://huggingface.co/datasets/{REPO} (tag {TAG})")


if __name__ == "__main__":
    main()
