# Safe twins

A safe twin is a training task paired with a trap version: the same task with the one fact that made the action
unsafe removed, so the path that is unsafe in the trap version is the right one here.

- id of a twin = id of its trap version + `-twin` (`-twin2` for a second twin of another type)
- `twin_of`, `pair_id` = the trap version's id; `twin_type` = remove_prohibition | harmless_content | allowed_destination
- `pairs.jsonl`: one row per pair
- a twin and its trap version always go to the same side of a train / dev split

Built in step 26 (analysis/prompts/step26.md).
