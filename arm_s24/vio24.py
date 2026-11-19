"""Step 24: the violator reference's unsafe step(s) per task, by code: the reference is played on the toolkit
(arm_s16b/play.py, as the rule pipeline does) and labelled with the frozen v4.2 rules (engine4.label_run). The two
judges are replaced by their 'no answer' defaults (no model call): the note judge can only clear an unasked-change
finding and the third-label judge can only add 'intent', so the designed (trap) findings are unaffected."""
import json, sys
sys.path.insert(0, 'arm_s24'); import load24 as L
import yaml


def run():
    rows, ctx, idx = L.tasks()
    import gen_rules_set42 as S42
    import engine4 as E
    E.JUDGE = lambda *a, **k: {"claims": False, "reason": "stub (step 24: no model call)"}
    E.NOTE_JUDGE = lambda *a, **k: {"only_actions_or_known": False, "reason": "stub (step 24: no model call)"}
    out = {}
    for t in sorted(rows):
        r = rows[t]; R = json.loads((L.DATA / idx[t]['rule_file']).read_text())['rules']
        if r.get('counter_example') or not r.get('violator_reference'):
            out[t] = {'control': bool(r.get('counter_example')), 'steps': []}; continue
        st = S42.P.play(r, r['violator_reference'])
        owner = (yaml.safe_load(r['environment']) or {}).get('owner_email')
        lr = E.label_run({**R, '_note_env': ''}, st, owner)
        steps = []
        for i, (s, ls) in enumerate(zip(st, lr['steps'])):
            fs = [f for f in ls['findings'] if f.get('label') == 'unsafe']
            if fs:
                steps.append({'i': i, 'tool': s['call']['name'], 'args': json.dumps(s['call']['args'], default=str)[:400],
                              'findings': [{k: f.get(k) for k in ('rule', 'tag', 'item', 'harm', 'coll', 'key', 'to')} for f in fs]})
        out[t] = {'control': False, 'steps': steps}
    return out


if __name__ == '__main__':
    o = run()
    json.dump(o, open('arm_s24/violator_unsafe.json', 'w'), indent=1, default=str)
    for t, v in o.items():
        print('==', t, 'CONTROL' if v['control'] else '')
        for s in v['steps']:
            print('   step', s['i'], s['tool'], [(f['rule'], f['tag'], f.get('item') or f.get('harm'), f.get('coll'), str(f.get('key'))[:60], str(f.get('to'))[:80]) for f in s['findings']])
