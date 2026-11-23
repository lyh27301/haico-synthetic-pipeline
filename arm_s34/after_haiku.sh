#!/bin/bash
# Step 34: once the main Haiku runs are done (runner_haiku.out says r3 finished), (1) redo the Haiku runs of the two tasks
# changed after the runs started (sq-cleaned-meas-retain-v141-v34, sq-cohort-contact-notes-v34: deliverable table created
# empty for the rules), (2) run Haiku on the 15 twins (2 workers), before any other part-4 work.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
until grep -q "haiku5.5 r3 attempt" arm_s34/runs/runner_haiku.out && ! pgrep -f "run_harness34.py --agent haiku --root arm_s34/runs" >/dev/null; do sleep 30; done
echo "$(date) main haiku done"
R=arm_s34/runs/harness/results; mkdir -p arm_s34/runs/superseded_haiku
printf 'safety-sq-cleaned-meas-retain-v141-v34\nsafety-sq-cohort-contact-notes-v34\n' > arm_s34/logs/redo_ids.txt
for t in $(cat arm_s34/logs/redo_ids.txt); do for k in 1 2 3; do f=$R/${t}__haiku5.5__r$k.json; [ -f $f ] && mv $f arm_s34/runs/superseded_haiku/; done; done
WORKERS=2 $PY arm_s34/run_harness34.py --agent haiku --root arm_s34/runs --first 1 --last 3 --ids arm_s34/logs/redo_ids.txt >> arm_s34/runs/runner_haiku_redo.out 2>&1
echo "$(date) haiku redo done"
mkdir -p arm_s34/twins/runs
BANK34=arm_s34/twins WORKERS=2 $PY arm_s34/run_harness34.py --agent haiku --root arm_s34/twins/runs --first 1 --last 3 >> arm_s34/twins/runs/runner_haiku.out 2>&1
echo "$(date) haiku twins done"
