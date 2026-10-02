"""Computed checks for the optional craft spine (3.75, --craft-spine).

Ported from the request-4-outline-loop-opus branch. Everything the old
3.75v audit checked that is a comparison or a lookup: the irony type
against the brief's epistemic gap, the escalation family against the
affect trajectory, setup/payoff citing real turns, citations by list
index. A hard finding goes to 3.75r; one that survives the repair rounds
is recorded and the pipeline continues (the spine colors the outline, it
does not carry it).

Each finding: {"source": "computed", "check", "material_quote",
"severity": "hard" | "soft", "note"}.
"""

import re


def _s(value):
    return str(value or '').strip()


def finding(check, quote, note, severity='hard'):
    return {'source': 'computed', 'check': check, 'material_quote': _s(quote)[:300],
            'severity': severity, 'note': note}


ESCALATION_FAMILIES = {
    'escalating':   ('compound', 'escalat', 'rising', 'ratchet', 'mount', 'build', 'cascad'),
    'oscillating':  ('oscillat', 'spike', 'wave', 'reset', 'undertow', 'pendul', 'alternat'),
    'sustained':    ('sustain', 'maintain', 'steady', 'plateau', 'constant', 'hold'),
    'diminishing':  ('diminish', 'easing', 'ease', 'declin', 'fade', 'wind down', 'subsid'),
    'arc':          ('arc', 'two-phase', 'two_phase', 'two phase', 'rise and fall', 'rise-and-fall'),
    'transforming': ('transform', 'shift', 'metamorph', 'change in kind', 'mutat'),
}


def _family_of(text):
    t = _s(text).lower()
    return {fam for fam, keys in ESCALATION_FAMILIES.items()
            if any(re.search(r'\b' + re.escape(k), t) for k in keys)}


def spine_findings(spine, brief, premise):
    out = []
    if not isinstance(spine, dict):
        return [finding('shape', '', 'the craft spine is not an object')]
    fields = (brief or {}).get('fields') or {}

    gap = (fields.get('3-0b.epistemic_gap') or {}).get('present')
    gap_present = gap is True or str(gap).lower() == 'true'
    irony = spine.get('irony_mode') or {}
    avail = irony.get('gap_available')
    avail_b = avail is True or str(avail).lower() == 'true'
    if avail_b != gap_present:
        out.append(finding('irony_mode.gap_available matches 3-0b.epistemic_gap.present', avail,
                           f'gap_available is {avail_b} but the brief says present is {gap_present}'))
    itype = _s(irony.get('type')).lower()
    if not gap_present and ('dramatic' in itype or 'knowledge' in itype):
        out.append(finding('irony type follows the gap', irony.get('type'),
                           'knowledge-based irony with no epistemic gap; only situational irony is allowed'))

    trajectory = _s((fields.get('3b.primary_trajectory') or {}).get('shape')).lower()
    esc = spine.get('escalation_shape') or {}
    pattern = _s(esc.get('pattern'))
    target = next((fam for fam in ESCALATION_FAMILIES if fam in trajectory), None)
    if target and pattern:
        fams = _family_of(pattern)
        # flag only a pattern that reads as ANOTHER family and not as its
        #  own, so an unusual but compatible word does not cost a repair
        if fams and target not in fams:
            out.append(finding('escalation pattern matches 3b.primary_trajectory', pattern,
                               f"pattern reads as {sorted(fams)}; the trajectory is '{trajectory}'"))
    if target == 'transforming' and not _s(esc.get('transformation_note')):
        out.append(finding('a transforming escalation names its shift', '',
                           'transformation_note is empty for a transforming trajectory'))
    if esc.get('new_variable_required') in (True, 'true') and not _s(esc.get('state_note')):
        out.append(finding('a new variable is justified', '', 'new_variable_required is true with no state_note'))

    turn_ids = {str(t.get('id')) for t in (premise or {}).get('turns') or [] if isinstance(t, dict)}
    pairs = spine.get('setup_payoff_pairs') or []
    if not isinstance(pairs, list) or not pairs:
        out.append(finding('one setup/payoff pair', '', 'setup_payoff_pairs is empty'))
    else:
        for i, p in enumerate(pairs):
            if not isinstance(p, dict):
                continue
            text = ' '.join(_s(p.get(k)) for k in ('setup', 'payoff', 'serves'))
            for n in re.findall(r'\bturns?\s*(\d+)', text.lower()):
                if turn_ids and n not in turn_ids:
                    out.append(finding('setup/payoff cites real turns', text,
                                       f'setup_payoff_pairs[{i}] cites turn {n}; the premise has turns {sorted(turn_ids)}'))
    for path, value in _strings(spine):
        if path.endswith('serves') and re.search(r'\w\[\d+\]', value):
            out.append(finding('cite by label, never by index', value,
                               f'{path} cites a list index; name the item by its label'))
    return out


def _strings(node, path=''):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f'{path}.{k}' if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f'{path}[{i}]')
    elif isinstance(node, str):
        yield path, node
