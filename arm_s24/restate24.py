"""Step 24: the same prohibition stated in other words on the object (code finds candidates, labels are by reading).
Units searched: records / files whose id or path is one of the trap's match ids / paths, or the record a harm state
selects; sentences with a prohibitive word that are not already a place of part A."""
import json, re, sys
sys.path.insert(0, 'arm_s24'); import load24 as L
PW = re.compile(r"(do not|don't|must not|may not|never|not be shared|not to be|internal only|internal use|confidential|restricted|only\b|hold\b|lock)", re.I)
rows, ctx, idx = L.tasks()
A = {json.loads(l)['task']: json.loads(l) for l in open('arm_s24/prohibition_location.jsonl')}
for t, a in A.items():
    C, pre, ws = L.corpus(rows[t], ctx.get(t, ''))
    known = {(p.get('where'), p.get('field')) for tr in a['traps'] for p in tr['places']}
    for tr in a['traps']:
        if tr['kind'] == 'protected':
            R = json.loads((L.DATA / idx[t]['rule_file']).read_text())['rules']
            m = next(p['match'] for p in R['protected'] if p['id'] == tr['trap'])
            keys = set(m['ids']) | set(m['paths'])
        else:
            R = json.loads((L.DATA / idx[t]['rule_file']).read_text())['rules']
            h = next(x for x in R['harm_states'] if x['id'] == tr['trap'])
            keys = {str(c['value']) for c in h['where'] if c['op'] == 'eq'}
        for k, w, f, txt in C:
            if k not in ('record', 'file'):
                continue
            wid = w if w.startswith('/') else (w.split('=', 1)[1] if '=' in w else '')
            if wid not in keys or (w, f) in known or (w, '') in known:
                continue
            for sent in re.split(r'(?<=[.!?])\s+|\n', txt):
                if PW.search(sent) and len(sent) > 12:
                    print(f"{t[7:]} | {tr['trap']} | {w} | {f} | {sent.strip()[:200]}")
