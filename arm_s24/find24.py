import sys, json; sys.path.insert(0, 'arm_s24'); import load24 as L
rows, ctx, idx = L.tasks()
out = {}
for t in sorted(rows):
    r = rows[t]; R = json.loads((L.DATA / idx[t]['rule_file']).read_text())['rules']
    md = (L.DATA / idx[t]['description']).read_text(); DT = L.desc_traps(md)
    C, pre, ws = L.corpus(r, ctx.get(t, ''))
    traps = [(p['id'], p['what'], p['quote']) for p in R['protected']] + [(h['id'], h['what'], None) for h in R['harm_states']]
    print('=' * 80); print(t)
    for tid, what, q in traps:
        print(' ', tid, what[:90], '| quote:', (q or '(none in rules)')[:120])
        if q is None:
            continue
        for fr in L.fragments(q):
            if fr.lower().startswith('common sense'):
                print('     [common sense]', fr[:100]); continue
            h = L.search(fr, C)
            if h:
                for x in h: print('     HIT', x[0], x[1], x[2], x[3], '<-', fr[:60])
            else:
                n, b = L.best_partial(fr, C)
                print('     MISS', fr[:80], '| best', n, '/', len(fr), b)
    for tk, txt in DT.items():
        print('  DESC', tk, txt.split('|')[-1].split('recognised by')[0].strip()[:250].replace('\n', ' '))
