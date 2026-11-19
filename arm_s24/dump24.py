import sys, json; sys.path.insert(0, 'arm_s24'); import load24 as L
rows, ctx, idx = L.tasks()
for t in sorted(rows):
    r = rows[t]; ix = idx[t]; R = json.loads((L.DATA / ix['rule_file']).read_text())['rules']
    md = (L.DATA / ix['description']).read_text()
    print('=' * 100); print(t, '| toolkit', r.get('toolkit'), '| user_instructed', r.get('user_instructed'), '| control', r.get('counter_example'), '| rule_set_of', ix['rule_set_of'])
    print('INSTR:', r['problem_statement'].strip()[:600])
    print('DESC TRAPS:', md.split('TRAPS', 1)[1].split('\nCOMPLETION', 1)[0].strip()[:1500] if 'TRAPS' in md else '-')
    for p in R['protected']: print('  PROT', p['id'], json.dumps({k: p[k] for k in ('what', 'quote', 'match', 'may_go_to')})[:700])
    for p in R['places']: print('  PLACE', json.dumps(p)[:500])
    for h in R['harm_states']: print('  HARM', h['id'], h['what'][:200], h['collection'], json.dumps(h['where'])[:300])
    print('  VIO:', ' | '.join(f"{s['tool']} {json.dumps(s['args'])[:250]}" for s in (r.get('violator_reference') or []) if s.get('pivotal') or True)[:1500])
