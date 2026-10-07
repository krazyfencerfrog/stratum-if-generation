"""When a story turns on paper: one word list and one rule for every step that checks it.

The pull toward documents is the model's, not a kernel's: given "make the stakes concrete", it
reaches for the most concrete-sounding thing a story can hold that costs nothing to write, a
paper (signed, sealed, filed), and once a premise has one, every later step builds on it. A
definition in the prompt did not stop it (the King on 2026-10-07: the RULES definition in place,
its contract's terms rewritten as conduct, and the paper moved into the levers, ways and events,
21 paper words to the night before's 22). So it is counted, at every step that writes story
material: 3.5a's engine, 3.5b's ways through, the premise audit, and 4b's node summaries.

The rule: at most a quarter of a step's items may turn on paper, plus two when the Kernel itself
names a document (the King's "sign a contract": the contract may be a lever and a setup, as in
Kipling, whose outline is 25% paper, not the spine of every scene, as in ours at 92%).
"""

import math
import re

# evaluate.PAPERWORK (the metric, unchanged so old numbers compare) plus the acts done to paper
PAPER = re.compile(r"\b(ledgers?|receipts?|contracts?|papers?|forms?|signatures?|signed|signing|signs?|countersign\w*|"
                   r"logbooks?|registers?|files?|filed|seals?|sealed|oaths?|letters?|fees?|clauses?|deeds?|documents?|"
                   r"invoices?|accounts?|tickets?|permits?|certificates?|licen[cs]es?|warrants?|writs?|petitions?|"
                   r"treat(?:y|ies)|charters?|bills? of|stamp(?:ed|s)?|crossed out|cross(?:es)? out)\b", re.I)
SHARE = 0.25
KERNEL_ALLOWANCE = 2


def word(text):
    m = PAPER.search(str(text or ''))
    return m.group(0) if m else None


def allowance(n, kernel):
    return math.ceil(SHARE * n) + (KERNEL_ALLOWANCE if PAPER.search(kernel or '') else 0)


def heavy(items, kernel):
    """[(where, text, word)] for the items that turn on paper, when there are
    more of them than the rule allows; [] when the step is within it."""
    items = [(w, str(t)) for w, t in items if str(t or '').strip()]
    hits = [(w, t, word(t)) for w, t in items if word(t)]
    return hits if len(hits) > allowance(len(items), kernel) else []


def complaint(hits, total, what):
    """The words a retry or a repair is given."""
    shown = '; '.join(f'{w} ("{p}")' for w, _, p in hits[:8])
    return (f'{len(hits)} of {total} {what} turn on paper (documents, signatures, seals, treaties, ledgers): {shown}. '
            f'At most a quarter may (two more when the Kernel names a document). Keep the paper the story is about, '
            f'and rewrite the rest as what people do with their hands, bodies, places and things that can break, burn, '
            f'be carried off or fought over')


def engine_items(engine):
    m = engine.get('mediation') if isinstance(engine.get('mediation'), dict) else {}
    out = [(f'levers[{i}]', l) for i, l in enumerate(m.get('levers') or [])]
    out += [(f'events[{i}]', (e or {}).get('what')) for i, e in enumerate(engine.get('events') or []) if isinstance(e, dict)]
    out += [('pressure', (engine.get('pressure') or {}).get('description'))] if isinstance(engine.get('pressure'), dict) else []
    opp = engine.get('opposition') if isinstance(engine.get('opposition'), dict) else {}
    out += [('opposition.means', opp.get('means')), ('opposition.shown_by', opp.get('shown_by'))]
    out += [(f'setups[{i}]', f"{(s or {}).get('plant')} {(s or {}).get('payoff')}") for i, s in enumerate(engine.get('setups') or [])
            if isinstance(s, dict)]
    for pole in ('to_reach_pole_a', 'to_reach_pole_b'):
        if isinstance(m.get(pole), dict):
            out.append((f'mediation.{pole}', m[pole].get('what_you_must_do')))
    return out


def way_items(turns):
    return [(f"turns[{t.get('id')}].ways_through[{i}]", (w or {}).get('way'))
            for t in turns or [] if isinstance(t, dict) for i, w in enumerate(t.get('ways_through') or []) if isinstance(w, dict)]


def premise_items(premise):
    return engine_items(premise) + way_items(premise.get('turns')) + [
        (f'complications[{i}]', (c or {}).get('description')) for i, c in enumerate(premise.get('complications') or [])
        if isinstance(c, dict)]
