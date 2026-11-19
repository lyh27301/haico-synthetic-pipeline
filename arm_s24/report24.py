"""Step 24: write analysis/step24.md from arm_s24/prohibition_location.jsonl, b_steps.jsonl, b_offdesign.jsonl,
b_examples.json (tables by code; the prose sections are written by hand in REPORT_TEXT below)."""
import json, collections
RANK = ['instruction', 'object', 'destination', 'related_context', 'unrelated', 'common_sense']
A = [json.loads(l) for l in open('arm_s24/prohibition_location.jsonl')]
B = [json.loads(l) for l in open('arm_s24/b_steps.jsonl')]
OFF = [json.loads(l) for l in open('arm_s24/b_offdesign.jsonl')]
EX = json.load(open('arm_s24/b_examples.json'))
short = lambda t: t.replace('safety-', '')
L = []
w = L.append


def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def main_place(a):
    """the place(s) that give the task value"""
    out = []
    for tr in a['traps']:
        if tr['value'] != a['prohibition_location']:
            continue
        for p in tr['places']:
            if p.get('label') == a['prohibition_location'] and not p.get('not_prohibition'):
                s = p['where'] if p['where'] else '(common sense)'
                s += (f".{p['field']}" if p.get('field') else '')
                if s not in out:
                    out.append(s)
    return out


w(open('arm_s24/report_head.md').read())

# ------------------------------------------------------------------ A
w('\n## A. Where each task states its prohibition\n')
cnt = collections.Counter(a['prohibition_location'] for a in A)
trapcnt = collections.Counter(t['value'] for a in A for t in a['traps'])
vcnt = collections.Counter(a['value_of_traps_violator_triggers'] or '(violator fires no designed trap)' for a in A if not a['control'])
w('Count per location (48 tasks: 46 of the v4.2 set + the 2 step-23 cm-firmware-lock versions; the 3 controls are counted too):\n')
w('| location | tasks (task value = nearest place) | of them controls | traps (each trap\'s own value) | non-control tasks by the traps the violator reference fires |')
w('|---|---|---|---|---|')
for k in RANK + ['(violator fires no designed trap)']:
    if k.startswith('('):
        w(f'| {k} | | | | {vcnt.get(k, 0)} |'); continue
    w(f"| {k} | {cnt.get(k, 0)} | {sum(1 for a in A if a['control'] and a['prohibition_location'] == k)} | {trapcnt.get(k, 0)} | {vcnt.get(k, 0)} |")
w(f"| total | {len(A)} | {sum(a['control'] for a in A)} | {sum(trapcnt.values())} | {sum(vcnt.values())} |\n")
w('The last column takes only the traps the violator reference makes unsafe (by code: the frozen v4.2 rules run on the '
  'played reference, arm_s24/violator_unsafe.json); it is the location of the trap the task was built around, which the '
  'task value can hide when a side trap sits nearer (sq-active-studies-changelog: task value object through S2/S5, the designed S7 trap is unrelated).\n')
for loc in RANK:
    rows = [a for a in A if a['prohibition_location'] == loc]
    if not rows:
        continue
    w(f'\n### {loc} ({len(rows)})\n')
    w('| task | toolkit | conf. | traps (value/confidence; * = the violator fires it) | where (the place(s) giving the value) | violator: object -> destination |')
    w('|---|---|---|---|---|---|')
    for a in sorted(rows, key=lambda a: a['task']):
        tr = ' '.join(f"{t['trap']}{'*' if t['violator_triggers'] else ''}={t['value'].replace('related_context', 'related').replace('common_sense', 'cs').replace('destination', 'dest')}/{t['confidence'][0]}" for t in a['traps'])
        ctl = ' (control)' if a['control'] else ''
        w(f"| {short(a['task'])}{ctl} | {a['toolkit']} | {a['confidence']} | {tr} | {esc('; '.join(main_place(a)))} | {esc(a['violator_object'])} -> {esc(a['violator_destination'])} |")
w('\nTrap value abbreviations: related = related_context, dest = destination, cs = common_sense; /h /l = high / low confidence. '
  'Every place with its quote fragment, level of match (exact / normalized / part / by reading), label and reason is in '
  'arm_s24/prohibition_location.jsonl.\n')

# per-trap detail of the quotes not found verbatim
w('\n### Quotes the rules give that are not found verbatim\n')
w('Exact search first, then whitespace / dash / quote-mark normalisation ("normalized"), then the quote split into the '
  'parts the rules joined ("part"). What is left was located by reading:\n')
w('| task | trap | quote fragment (rules) | found by | where / note |')
w('|---|---|---|---|---|')
for a in A:
    for t in a['traps']:
        for p in t['places']:
            if p['level'] not in ('exact', 'common_sense'):
                w(f"| {short(a['task'])} | {t['trap']} | {esc(p['fragment'][:90])} | {p['level']} | {esc((p.get('where') or '') + (('.' + p['field']) if p.get('field') else ''))} {esc(p.get('note') or '')[:220]} |")

# ------------------------------------------------------------------ unrelated
w('\n### `unrelated`\n')
un_t = [a for a in A if a['prohibition_location'] == 'unrelated']
w(f"No task has `unrelated` as its value ({len(un_t)}). Three traps do, and one of them is the trap a task was built around:\n")
w('| task | trap | the violator fires it | where the prohibition is | what would have to move where (not repaired) |')
w('|---|---|---|---|---|')
FIX = {
 ('safety-sq-active-studies-changelog', 'P1'): 'put "IRB SUSPENDED - DO NOT REPORT AS ACTIVE" on the studies row S7 itself (status or notes; it now says status "active", notes "IRB review pending") -> object; or into the data_dictionary entry of studies.status -> related_context',
 ('safety-gm-case-study-bundle-zip-fixed', 'P2'): 'put a "never share this code" line into the password-reset email 192302b534c993f0 -> object (otherwise the trap stays common_sense, as in acme-forward / alerts-purge / legal-amendment)',
 ('safety-gm-contractx-privileged-bundle', 'P3'): 'same as case-study P2: the line goes into the password-reset email 192302b534c993f0 -> object',
}
for a in A:
    for t in a['traps']:
        if t['value'] == 'unrelated':
            p = [x for x in t['places'] if x['label'] == 'unrelated'][0]
            w(f"| {short(a['task'])} | {t['trap']} | {'yes' if t['violator_triggers'] else 'no'} | {esc(p['where'])}.{p['field']}: \"{esc(p['fragment'])}\" ({esc(p['reason'])}) | {esc(FIX[(a['task'], t['trap'])])} |")
w('\nAll 8 trap steps of sq-active-studies-changelog in the step-21 runs are on P1 (part B), so for training this task is the `unrelated` case even though its task value is `object`.\n')

# ------------------------------------------------------------------ low confidence
w('\n## Low-confidence labels (check these first)\n')
w('A label is low when it needed judgment: which record is "the parent", whether a place is on the object, whether a '
  'matched text is a prohibition at all, or the quote was not verbatim. Task-level low (the value itself rests on a low label):\n')
w('| task | value | why low |')
w('|---|---|---|')
for a in A:
    if a['confidence'] == 'low':
        why = []
        for t in a['traps']:
            if t['value'] == a['prohibition_location']:
                for p in t['places']:
                    if p.get('label') == a['prohibition_location'] and p.get('confidence') == 'low':
                        r = f"{t['trap']} {p['where']}: {p['reason']}"
                        if r not in why:
                            why.append(r)
        if not why:
            why = ['the only stated texts are not prohibitions (content quoted by the rules), so the value falls to common_sense by judgment']
        w(f"| {short(a['task'])} | {a['prohibition_location']} | {esc(' / '.join(why))[:700]} |")
w('\nEvery low place (trap level):\n')
w('| task | trap | label | place | reason |')
w('|---|---|---|---|---|')
for a in A:
    for t in a['traps']:
        for p in t['places']:
            if p.get('confidence') == 'low':
                w(f"| {short(a['task'])} | {t['trap']} | {p['label']} | {esc(p['where'])}{('.' + p['field']) if p.get('field') else ''} | {esc(p['reason'])} |")

# ------------------------------------------------------------------ controls
w('\n## Controls (counter_example)\n')
w(open('arm_s24/report_controls.md').read())

# ------------------------------------------------------------------ B
w('\n## B. Per unsafe step, on the graded step-21 runs\n')
w(open('arm_s24/report_b_head.md').read())
CASES = ['in_trajectory', 'object_or_destination', 'related_context_only', 'not_reachable', 'common_sense']
HDR = '| {} | unsafe trap steps | prohibition already in the trajectory | reachable only by reading object or destination | only by related context | not reachable | no stated prohibition (common sense) | off_design unsafe steps |'


def row(name, steps, off):
    n = len(steps); c = collections.Counter(s['case'] for s in steps)
    pct = lambda k: f"{c.get(k, 0)} ({100 * c.get(k, 0) / n:.0f}%)" if n else '0'
    return f"| {name} | {n} | " + ' | '.join(pct(k) for k in CASES) + f" | {off} |"


w('\n### Per agent\n')
w(HDR.format('agent')); w('|---|---|---|---|---|---|---|---|')
for ag in sorted({s['agent'] for s in B} | {o['agent'] for o in OFF}):
    w(row(ag, [s for s in B if s['agent'] == ag], sum(1 for o in OFF if o['agent'] == ag)))
w(row('**all**', B, len(OFF)))
w('\n### Per task\n')
w(HDR.format('task') + ' location (A) |'); w('|---|---|---|---|---|---|---|---|---|')
Av = {a['task']: a for a in A}
for t in sorted({s['task'] for s in B} | {o['task'] for o in OFF}):
    a = Av[t]
    w(row(short(t), [s for s in B if s['task'] == t], sum(1 for o in OFF if o['task'] == t)) + f" {a['prohibition_location']} (violator's traps: {a['value_of_traps_violator_triggers']}) |")
w('\n### Per task x agent (trap steps: in trajectory / object-destination / related only / not reachable / common sense)\n')
ags = sorted({s['agent'] for s in B})
w('| task | ' + ' | '.join(ags) + ' |'); w('|---|' + '---|' * len(ags))
for t in sorted({s['task'] for s in B}):
    cells = []
    for ag in ags:
        c = collections.Counter(s['case'] for s in B if s['task'] == t and s['agent'] == ag)
        cells.append('/'.join(str(c.get(k, 0)) for k in CASES) if c else '-')
    w(f"| {short(t)} | " + ' | '.join(cells) + ' |')
w('\n### Off_design unsafe steps (no prohibition needed)\n')
oc = collections.Counter(r for o in OFF for r in o['rules'])
w(f"{len(OFF)} steps, by rule: " + ', '.join(f'{k} {v}' for k, v in oc.most_common()) + '. Per task: ' +
  ', '.join(f"{short(t)} {n}" for t, n in collections.Counter(o['task'] for o in OFF).most_common()) + '.\n')

w('\n### Examples (three per case)\n')
NAMES = {'in_trajectory': 'Prohibition already in the trajectory', 'object_or_destination': 'Reachable by reading the object or the destination',
         'related_context_only': 'Reachable only through related context', 'not_reachable': 'Not reachable through object, destination or related context',
         'common_sense': 'No stated prohibition (common sense; not one of the four cases, shown for completeness)'}
for case in CASES:
    w(f'\n**{NAMES[case]}**\n')
    for e in EX[case]:
        w(f"- `{e['key']}` step {e['step']} `{esc(e['unsafe_call'][:220])}`")
        pro = '; '.join(f"[{lab}] {wh}: \"{esc(fr[:160])}\"" for lab, wh, fr in e['prohibition'][:3])
        w(f"  - prohibition: {pro}")
        if e['in_trajectory']:
            seen = sorted({x[2] for x in e['in_trajectory']})
            w(f"  - visible before the step: yes, in {', '.join(seen)}")
        else:
            w(f"  - visible before the step: no. Earlier calls: {esc('; '.join(c[:90] for c in e['calls_before'])[:600])}")
            if e.get('last_result_on_object'):
                j, tool, txt = e['last_result_on_object']
                w(f"  - what the agent last saw of the object (step {j} {tool}): `{esc(txt[:420])}`")
            for r in e['reads']:
                w(f"  - reading [{r['label']}] {r['where']} with `{esc(r['read'][:140])}` returns the text: {'yes' if r['returned'] else 'no'}")
w('\n' + open('arm_s24/report_tail.md').read())
open('analysis/step24.md', 'w').write('\n'.join(L) + '\n')
print('written', len(L), 'lines')
