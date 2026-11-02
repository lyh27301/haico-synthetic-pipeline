"""Step 11 Part C: classify every v0.6 task on Qwen3.5-9B alone from its 5 runs (results/<task>__qwen3.5-9b__r<k>.json):
good = at least one graded safe and one graded unsafe run; all_safe / all_unsafe = every graded run agrees;
no_grade = no graded run.
  .venv/bin/python arm_s11/classify_qwen.py -> arm_s11/qwen_class.json"""
import collections, json
from pathlib import Path

S11 = Path(__file__).resolve().parent; RES = S11 / "harness/results"


def main():
    ids = (S11 / "ids_v06.txt").read_text().split()
    out = {}
    for t in ids:
        rs = [json.loads((RES / f"{t}__qwen3.5-9b__r{k}.json").read_text()) for k in range(1, 6)]
        g = [r["unsafe"] for r in rs if r["graded"]]
        n_u = sum(bool(x) for x in g)
        c = "no_grade" if not g else "good" if 0 < n_u < len(g) else "all_unsafe" if n_u else "all_safe"
        out[t] = {"class": c, "n_graded": len(g), "n_unsafe": n_u, "unsafe_rate": n_u / len(g) if g else None,
                  "reruns": sum(bool(r.get("rerun")) for r in rs), "no_grade": sum(not r["graded"] for r in rs)}
    (S11 / "qwen_class.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(collections.Counter(v["class"] for v in out.values())),
          "reruns", sum(v["reruns"] for v in out.values()))


if __name__ == "__main__":
    main()
