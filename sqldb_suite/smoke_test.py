"""Smoke test: exercise the SQLDatabase tool (read, every write verb, MySQL-isms, errors)
via the runtime and assert the env really changes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqldb_suite.environment import load_environment
from sqldb_suite.tools import build_runtime

BASE = Path(__file__).parent / "base_environment.yaml"
DB = "research_db"


def run(rt, env, query, ok=True):
    out, err = rt.run_function(env, "sql_database", {"query": query, "database": DB})
    assert (err is None) == ok, f"{query!r}: err={err}"
    return out if ok else err


def main():
    rt = build_runtime()
    env = load_environment(BASE)
    t = env.databases[DB]
    assert len(t["participants"].rows) == 12 and len(t["measurements"].rows) == 24

    r = run(rt, env, "SHOW TABLES")
    assert {"participants", "results_summary"} <= {x["table_name"] for x in r["results"]}
    r = run(rt, env, "DESCRIBE measurements"); assert any(x["column_name"] == "status" for x in r["results"])
    r = run(rt, env, "SELECT condition, ROUND(AVG(cognitive_score),1) AS m FROM measurements GROUP BY condition")
    assert len(r["results"]) == 2
    before = env.model_dump()
    run(rt, env, "SELECT * FROM participants"); assert env.model_dump() == before, "read changed state"

    run(rt, env, "INSERT INTO results_summary VALUES ('AN-03','mean_cognitive_score','sleep_deprived',79.0,12,'2026-10-29','me')")
    assert any(x["analysis_id"] == "AN-03" for x in env.databases[DB]["results_summary"].rows), "insert"
    run(rt, env, "UPDATE model_runs SET learning_rate = 0.0005 WHERE run_id = 'R-1'")
    assert env.databases[DB]["model_runs"].rows[0]["learning_rate"] == 0.0005, "update"
    run(rt, env, "DELETE FROM measurements WHERE session_id = 'S001'")
    assert len(env.databases[DB]["measurements"].rows) == 23, "delete"
    run(rt, env, "CREATE TABLE tmp_x AS SELECT participant_id, cohort FROM participants; INSERT INTO tmp_x VALUES ('Z','A')")
    assert len(env.databases[DB]["tmp_x"].rows) == 13, "create + multi-statement"
    run(rt, env, "DROP TABLE tmp_x"); assert "tmp_x" not in env.databases[DB], "drop"
    run(rt, env, "INSERT INTO train_set SELECT * FROM test_set")
    assert len(env.databases[DB]["train_set"].rows) == 12, "insert-select"

    err = run(rt, env, "SELEC nonsense", ok=False); assert "QueryExecutionException" in err
    out, err = rt.run_function(env, "sql_database", {"query": "SELECT 1", "database": "nope"})
    assert err and "InvalidDatabaseException" in err
    # failed multi-statement query must not half-apply
    n = len(env.databases[DB]["changelog"].rows)
    run(rt, env, "INSERT INTO changelog VALUES ('CL-9','x','d','m'); SELEC bad", ok=False)
    assert len(env.databases[DB]["changelog"].rows) == n, "partial write leaked"
    print("SMOKE OK: read/insert/update/delete/create/drop/insert-select/mysql-isms/errors")


if __name__ == "__main__":
    main()
