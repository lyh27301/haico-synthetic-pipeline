"""Step 24 part B: example steps per case (3 each) with the text that was / was not visible, and a clip check of the
recorded tool results (markers of truncated observations)."""
import json, sys, random, re, collections
sys.path.insert(0, 'arm_s24'); import load24 as L
import grade23 as G23, runs16c
runs16c._BANK = G23.rows()
res = {r['key']: r for r in G23.results(G23.TREES21)}
B = [json.loads(l) for l in open('arm_s24/b_steps.jsonl')]
A = {json.loads(l)['task']: json.loads(l) for l in open('arm_s24/prohibition_location.jsonl')}
CLIP = re.compile(r'truncat|clipped|\.\.\. \[|<response clipped>|\[output (?:was )?(?:truncated|cut)', re.I)
clipped = collections.Counter(); checked = 0
for b in B:
    st = runs16c.load(res[b['key']])['steps']
    for s in st[:b['step']]:
        checked += 1
        if CLIP.search(str(s['call'].get('result'))):
            clipped[(b['task'], s['call']['name'])] += 1
print('earlier results checked:', checked, 'with a clip marker:', sum(clipped.values()), dict(clipped))
random.seed(24)
ex = {}
for case in ('in_trajectory', 'object_or_destination', 'related_context_only', 'not_reachable', 'common_sense'):
    pool = [b for b in B if b['case'] == case]
    # spread over tasks
    by_t = collections.defaultdict(list)
    for b in pool:
        by_t[b['task']].append(b)
    ts = sorted(by_t); random.shuffle(ts)
    pick = [random.choice(by_t[t]) for t in ts[:3]]
    if len(pick) < 3:
        pick += random.sample([b for b in pool if b not in pick], min(3 - len(pick), len(pool) - len(pick)))
    out = []
    for b in pick:
        st = runs16c.load(res[b['key']])['steps']
        before = [f"{j} {s['call']['name']} {json.dumps(s['call']['args'], default=str)[:120]}" for j, s in enumerate(st[:b['step']])]
        # what the agent saw about the object: the last earlier result that mentions an id of the trap
        tr = [x for x in A[b['task']]['traps'] if x['trap'] in b['traps']][0]
        objkeys = []
        if tr['kind'] == 'protected':
            objkeys = tr.get('places') and []
        seen = None
        for j, s in reversed(list(enumerate(st[:b['step']]))):
            r = str(s['call'].get('result'))
            m = re.search(r'(PROD-\d+|60071|4532|VT-926|SLBX4471|test_set|S7\b|S-2[13]|S-44|f_\w+|Amiodarone|Methotrexate|BP-\d+|S10[123])', r)
            if m:
                k = r.find(m.group(1)); seen = (j, s['call']['name'], r[max(0, k - 300): k + 500]); break
        out.append({**{k: b[k] for k in ('key', 'task', 'agent', 'step', 'tool', 'traps', 'case', 'in_trajectory')},
                    'reads': [{k: r[k] for k in ('label', 'where', 'read', 'returned')} for r in b['reads']],
                    'unsafe_call': f"{st[b['step']]['call']['name']} {json.dumps(st[b['step']]['call']['args'], default=str)[:300]}",
                    'calls_before': before, 'last_result_on_object': seen,
                    'prohibition': [(p['label'], p['where'], p['fragment'][:200]) for x in A[b['task']]['traps'] if x['trap'] in b['traps']
                                    for p in x['places'] if p['label'] and not p.get('not_prohibition')]})
    ex[case] = out
json.dump(ex, open('arm_s24/b_examples.json', 'w'), indent=1, default=str)
for case, v in ex.items():
    print('#####', case)
    for e in v:
        print(json.dumps(e, default=str)[:2500]); print()
