"""Computed metrics over a finished outline, and the packet for the one
cheap judge call (4e) that scores it.

Nothing here decides anything in the pipeline; it measures. The metrics
are the things we kept finding by reading outlines (docs/fable_request_5.txt):
forks that all come late, endings that differ only in who pays, one phrase
repeated through every node, a dragon story with no dragon in it,
companions whose standing never changes. Each is a count or a lookup over
the story document, so it can be compared across runs and across variants
(generator/ab.py). The judge call is the same local model grading its own
work: a weak signal, kept because it is cheap and comparable.

    metrics(story, promises)  -> dict of numbers and short lists
    judge_digest(story)       -> the compact text the 4e prompt reads
    validate_judge(parsed)    -> normalizes the 4e answer (raises on a bad one)
    summary_lines(result)     -> a few lines for the console
    table(results)            -> side-by-side rows for ab.py
"""

import re

import checks
import example_guard

SUMMARY_WORDS = (45, 75)      # docs/kernel1_target_outline.md
PHRASE_N = 4
PHRASE_MIN_NODES = 3          # a phrase in this many different nodes is a tic


def words(text):
    return re.findall(r"[a-z0-9']+", str(text or '').lower())


def content_words(text):
    return {w for w in words(text) if example_guard.content(w)}


PAPERWORK = re.compile(r"\b(ledgers?|receipts?|contracts?|papers|forms?|signatures?|signed|signs?|countersign\w*|logbooks?|"
                       r"registers?|files?|seals?|sealed|oaths?|letters?|fees?|clauses?|deeds?|documents?|invoices?|"
                       r"accounts?|tickets?|permits?|certificates?|licen[cs]es?|warrants?|writs?|petitions?|treaty|"
                       r"charters?|ledger|bills? of)\b", re.I)


def phrases(text, n=PHRASE_N):
    return example_guard.ngrams(text, n)


# ---------------------------------------------------------------- metrics

def metrics(story, promises=None):
    lines = story.get('lines') or {}
    order = story.get('line_order') or list(lines)
    nodes = story.get('nodes') or {}
    node_order = story.get('node_order') or list(nodes)
    chars = story.get('characters') or {}
    premise = story.get('premise') or {}
    turns = [t for t in (premise.get('turns') or []) if isinstance(t, dict)]
    out = {}

    # size
    summaries = [nodes[n].get('summary') or '' for n in node_order]
    counts = [len(words(s)) for s in summaries]
    out['lines'] = len(order)
    out['nodes'] = len(node_order)
    out['nodes_per_line'] = [len(lines[l].get('path') or []) for l in order]
    out['summary_words_mean'] = round(sum(counts) / len(counts), 1) if counts else 0
    out['summary_words_range'] = [min(counts), max(counts)] if counts else [0, 0]
    out['summaries_in_target_share'] = round(sum(SUMMARY_WORDS[0] <= c <= SUMMARY_WORDS[1] for c in counts) / len(counts), 2) if counts else 0
    out['images_present_share'] = round(sum(bool((nodes[n].get('image') or '').strip()) for n in node_order) / len(node_order), 2) if node_order else 0

    # agency: where the lines part
    main = lines.get(order[0]) if order else None
    path = (main or {}).get('path') or []
    forks = []
    for l in order[1:]:
        dv = lines[l].get('divergence') or {}
        at = dv.get('diverges_at')
        if at in path:
            forks.append(path.index(at) + 1)
    out['fork_positions'] = forks                       # 1-based index on the main line
    out['main_line_length'] = len(path)
    out['earliest_fork_share'] = round(min(forks) / len(path), 2) if forks and path else None
    out['forks_in_first_half'] = sum(1 for f in forks if f <= len(path) / 2)
    out['accumulated_triggers'] = sum(1 for l in order[1:] if (lines[l].get('divergence') or {}).get('trigger_kind') == 'accumulated')
    out['late_forks'] = bool(checks.late_forks(lines))

    # endings: distinct worlds, answers, companions whose standing varies
    worlds, answers = [], []
    standing_by_role = {}
    for l in order:
        e = lines[l].get('ending') or {}
        cast = [c for c in (story.get('characters') or {}).values() if c.get('kind') != 'crowd']
        key = checks.world_key(e, cast)
        worlds.append(key)
        answers.append(e.get('answer'))
        for x in e.get('standing') or []:
            standing_by_role.setdefault(checks.norm(x), set()).add('standing')
        for x in e.get('lost') or []:
            standing_by_role.setdefault(checks.norm(x), set()).add('lost')
    out['endings'] = len(worlds)
    out['distinct_ending_worlds'] = len(set(worlds))
    out['ending_distinctness'] = round(len(set(worlds)) / len(worlds), 2) if worlds else 0
    out['distinct_answers'] = sorted({a for a in answers if a})
    out['companions_whose_standing_varies'] = sorted(r for r, v in standing_by_role.items() if len(v) > 1)
    out['ending_worlds_stated_share'] = round(sum(1 for l in order if (lines[l].get('ending') or {}).get('answer')) / len(order), 2) if order else 0

    # the premise: forms, set pieces, events
    # craft the reference stories showed missing (docs/reference_stories.md)
    out['price_named'] = bool((premise.get('price') or {}).get('what'))
    out['price_paid'] = any((lines[l].get('ending') or {}).get('pays_price') for l in order)
    setups = premise.get('setups') or []
    main_nodes = [nodes[n] for n in path if n in nodes]
    planted = [k for k in range(1, len(setups) + 1) if any(k in (nd.get('plants') or []) for nd in main_nodes)]
    paid = [k for k in planted if any(k in (nd.get('pays') or []) for nd in main_nodes)]
    out['setups'] = len(setups)
    out['setups_paid_on_main'] = len(paid)
    out['rules_with_terms'] = sum(1 for r in premise.get('rules') or [] if (r or {}).get('terms'))
    out['opposition_shown'] = bool((premise.get('opposition') or {}).get('shown_by'))
    out['turn_forms'] = [t.get('form') for t in turns]
    out['set_piece_turns'] = [t.get('id') for t in turns if t.get('set_piece')]
    sp_turns = set(out['set_piece_turns'])
    out['set_piece_nodes'] = [n for n in node_order if nodes[n].get('turn') in sp_turns]
    events = [e for e in (premise.get('events') or []) if isinstance(e, dict)]
    placed = {nodes[n].get('event') for n in node_order if nodes[n].get('event') is not None}
    out['events'] = len(events)
    out['events_placed'] = len(placed & set(range(1, len(events) + 1)))
    out['complications'] = len(premise.get('complications') or [])
    out['cast_with_voice'] = sum(1 for s in premise.get('cast_seeds') or [] if isinstance(s, dict) and s.get('voice'))
    out['cast_with_breaking_point'] = sum(1 for s in premise.get('cast_seeds') or [] if isinstance(s, dict) and s.get('breaking_point'))
    out['cast'] = len(premise.get('cast_seeds') or [])

    # turn similarity: two turns whose ways read alike are one turn written twice
    sims = []
    way_text = [' '.join(f"{w.get('way')} {w.get('cost')}" for w in t.get('ways_through') or [] if isinstance(w, dict)) for t in turns]
    for i in range(len(way_text)):
        for j in range(i + 1, len(way_text)):
            a, b = content_words(way_text[i]), content_words(way_text[j])
            if a and b:
                sims.append(round(len(a & b) / len(a | b), 2))
    out['turn_similarity_max'] = max(sims) if sims else 0

    # specificity: repeated phrases, brief echoes, retold nodes
    seen = {}
    for n in node_order:
        for ph in phrases(summaries[node_order.index(n)]):
            seen.setdefault(ph, set()).add(n)
    tics = sorted(((len(v), ' '.join(k)) for k, v in seen.items() if len(v) >= PHRASE_MIN_NODES), reverse=True)
    out['repeated_phrases'] = [f'{p} ({c} nodes)' for c, p in tics[:6]]
    out['repeated_phrase_count'] = len(tics)
    brief = story.get('brief') or {}
    out['brief_echoes'] = example_guard.brief_echoes(summaries, brief)[:5] if brief else []
    # paperwork: how much of the story turns on documents, fees and signatures (2026-10-04: 70-100% of node
    # summaries on most kernels, a heist and a Roman bathhouse among them)
    papery = [s for s in summaries if PAPERWORK.search(s)]
    out['paperwork_share'] = round(len(papery) / len(summaries), 2) if summaries else 0
    out['paperwork_words'] = sorted({m.lower() for s in summaries for m in PAPERWORK.findall(s)})[:12]
    out['retold_nodes'] = len(checks.repeated_nodes(nodes))
    out['repeated_situations'] = len(checks.repeated_situations(story))

    # people and places
    opp = {cid for cid, c in chars.items() if c.get('opposition') and c.get('kind') != 'crowd'}
    seen_opp = []
    for l in order:
        seen_opp.append(sum(1 for n in lines[l].get('path') or [] if opp & set(nodes[n].get('who') or [])))
    out['opposition_nodes_per_line'] = seen_opp
    out['characters'] = len(chars)
    out['locations'] = len(story.get('locations') or {})
    usage = checks.derive_usage(story)
    out['unused_characters'] = sum(1 for c, used in usage['characters'].items() if not used and chars.get(c, {}).get('kind') != 'crowd')

    # genre: promise coverage
    if isinstance(promises, dict):
        items = [p.get('what') for p in promises.get('promises') or [] if isinstance(p, dict)]
        items += [p.get('scene') for p in promises.get('set_pieces') or [] if isinstance(p, dict)]
        text_words = content_words(' '.join(summaries) + ' ' + ' '.join(str(nodes[n].get('image') or '') for n in node_order))
        covered = [it for it in items if it and len(content_words(it) & text_words) >= 2]
        out['promise_coverage'] = round(len(covered) / len(items), 2) if items else None
        out['promises_uncovered'] = [it for it in items if it and it not in covered][:5]
    else:
        out['promise_coverage'] = None
        out['promises_uncovered'] = []

    ck = story.get('checks') or {}
    out['check_findings'] = len(ck.get('findings') or [])
    out['check_notes'] = [f.get('kind') for f in ck.get('notes') or []]
    return out


# ---------------------------------------------------------------- the judge call

def judge_digest(story):
    """The outline as the 4e prompt reads it: lines with their endings and
    worlds, nodes with summary and image, the cast with voices. Plain
    text, a few kilobytes."""
    lines = story.get('lines') or {}
    nodes = story.get('nodes') or {}
    chars = story.get('characters') or {}
    out = []
    q = ((story.get('premise') or {}).get('mediation') or {}).get('question')
    if q:
        out.append(f'QUESTION: {q}')
    out.append('LINES')
    for lid in story.get('line_order') or list(lines):
        l = lines[lid]
        e = l.get('ending') or {}
        dv = l.get('divergence') or {}
        out.append(f"- {lid} {l.get('title')}: {l.get('motivation')}")
        if dv:
            out.append(f"  leaves after {dv.get('diverges_at')} when {dv.get('trigger')}")
        world = f"answer {e.get('answer')}" if e.get('answer') else ''
        if e.get('standing'):
            world += f"; standing {', '.join(e['standing'])}"
        if e.get('lost'):
            world += f"; lost {', '.join(e['lost'])}"
        out.append(f"  ending: {e.get('summary')}" + (f" [{world}]" if world else ''))
    out.append('NODES')
    for nid in story.get('node_order') or list(nodes):
        n = nodes[nid]
        tags = n.get('beat') or ''
        if n.get('turn') is not None:
            tags += f', turn {n["turn"]}'
        out.append(f"- {nid} ({tags}) {n.get('title')}: {n.get('summary')}" + (f" IMAGE: {n['image']}" if n.get('image') else ''))
    out.append('PEOPLE')
    for c in chars.values():
        bits = [c.get('label') or '']
        if c.get('name'):
            bits[0] = f"{c['name']} ({c['label']})"
        if c.get('opposition'):
            bits.append('opposition')
        line = f"- {', '.join(bits)}: wants {c.get('wants')}"
        if c.get('voice'):
            line += f"; voice: {c['voice']}"
        out.append(line)
    return '\n'.join(out)


JUDGE_AXES = ('plot', 'people', 'reveals', 'agency', 'specificity', 'genre')


def validate_judge(parsed):
    if not isinstance(parsed, dict) or not isinstance(parsed.get('scores'), dict):
        raise ValueError('expected an object with "scores"')
    problems = []
    for axis in JUDGE_AXES:
        entry = parsed['scores'].get(axis)
        if isinstance(entry, (int, float)):
            entry = {'note': '', 'score': entry}
        if not isinstance(entry, dict):
            problems.append(f'scores.{axis} is missing')
            continue
        try:
            score = int(round(float(entry.get('score'))))
        except (TypeError, ValueError):
            problems.append(f'scores.{axis}.score is not a number')
            continue
        entry['score'] = max(1, min(5, score))
        entry['note'] = str(entry.get('note') or '').strip()
        parsed['scores'][axis] = entry
    if problems:
        raise ValueError('; '.join(problems))
    parsed['total'] = sum(parsed['scores'][a]['score'] for a in JUDGE_AXES)
    parsed['would_play'] = str(parsed.get('would_play')).strip().lower() in ('true', 'yes', '1')
    for key in ('reading', 'best_thing', 'worst_thing'):
        parsed[key] = str(parsed.get(key) or '').strip()


# ---------------------------------------------------------------- reporting

KEY_COLUMNS = [
    ('lines', 'lines'), ('nodes', 'nodes'), ('earliest_fork_share', 'fork@'), ('forks_in_first_half', 'early'),
    ('ending_distinctness', 'worlds'), ('promise_coverage', 'promise'), ('events_placed', 'events'),
    ('repeated_phrase_count', 'tics'), ('repeated_situations', 'retold'), ('summaries_in_target_share', 'sized'),
    ('paperwork_share', 'paper'),
]


def summary_lines(result):
    m = result.get('metrics') or {}
    out = [f"outline metrics: {m.get('lines')} line(s), {m.get('nodes')} node(s); forks at {m.get('fork_positions')} of "
           f"{m.get('main_line_length')} ({m.get('forks_in_first_half')} in the first half); "
           f"{m.get('distinct_ending_worlds')}/{m.get('endings')} distinct ending worlds, answers {m.get('distinct_answers')}; "
           f"companions whose standing varies: {m.get('companions_whose_standing_varies') or 'none'}"]
    out.append(f"  events placed {m.get('events_placed')}/{m.get('events')}; set-piece turns {m.get('set_piece_turns')}; "
               f"promise coverage {m.get('promise_coverage')}; repeated phrases {m.get('repeated_phrase_count')}"
               + (f" ({'; '.join(m.get('repeated_phrases')[:3])})" if m.get('repeated_phrases') else '')
               + f"; retold situations {m.get('repeated_situations')}; summaries {m.get('summary_words_mean')} words "
                 f"({m.get('summaries_in_target_share')} in {SUMMARY_WORDS[0]}-{SUMMARY_WORDS[1]})")
    j = result.get('judge')
    if j:
        scores = ' '.join(f"{a} {j['scores'][a]['score']}" for a in JUDGE_AXES if a in j.get('scores', {}))
        out.append(f"  judge: {j.get('total')}/30 ({scores}); would play: {j.get('would_play')}")
        out.append(f"  best: {j.get('best_thing')}")
        out.append(f"  worst: {j.get('worst_thing')}")
    return out


def table(results):
    """results: {column label: eval result}. Rows of (metric, values...)."""
    labels = list(results)
    rows = [['metric'] + labels]
    for key, short in KEY_COLUMNS:
        rows.append([short] + [str((r.get('metrics') or {}).get(key)) for r in results.values()])
    rows.append(['judge'] + [str((r.get('judge') or {}).get('total', '-')) for r in results.values()])
    rows.append(['minutes'] + [str(r.get('minutes', '-')) for r in results.values()])
    widths = [max(len(row[i]) for row in rows) for i in range(len(labels) + 1)]
    return '\n'.join('  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)
