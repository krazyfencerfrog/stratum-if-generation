"""Computed digests of upstream material, so later prompts receive a few
hundred tokens instead of the whole phase-3 bundle.

Every downstream trace in the archived kernel1 run opened by restating the
nine extractions (notes, evidence tiers and all) back to itself; that
restatement was 30-40 lines of every trace and scaled with the input. The
story brief keeps each field's VALUE and its binding class (constraint /
default / free, from the constraint map) and drops the notes. A prompt that
needs a note can still be given the raw field.

Also here: the shape targets derived from step 2's shape preferences, so
the numbers the outline loop steers by are computed once, not judged; the
compact one-line-per-field rendering the prompts after 3h receive
(brief_lines); and the two tables the premise verifier is handed instead
of being asked to find them (kernel_clauses, constraint_fields).
"""

import re


def g(node, *path, default=None):
    """Tolerant nested getter."""
    cur = node
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


# brief field -> (bundle field id, extractor)
# The keys keep the phase-3 ids so `serves` tags and the lessons doc still
# name the same things.
def _fields(bundle):
    a = bundle.get('3-0a') or {}
    b = bundle.get('3-0b') or {}
    c = bundle.get('3-0c') or {}
    aff = bundle.get('3b') or {}
    th = bundle.get('3c') or {}
    vp = bundle.get('3d') or {}
    tl = bundle.get('3e') or {}
    st = bundle.get('3f') or {}
    cx = bundle.get('3g') or {}
    return {
        '3-0a.primary_decision_axis': {
            'label': g(a, 'primary_decision_axis', 'label'),
            'description': g(a, 'primary_decision_axis', 'description'),
        },
        '3-0a.decision_mechanism': {'shape': g(a, 'decision_mechanism', 'shape')},
        '3-0a.secondary_decision_axes': {
            'axes': [{'label': g(x, 'label'), 'relation': g(x, 'relation')}
                     for x in (g(a, 'secondary_decision_axes', default=[]) or []) if isinstance(x, dict)],
        },
        '3-0a.decision_landscape': {'shape': g(a, 'decision_landscape', 'shape')},
        '3-0b.protagonist_identity': {
            'type': g(b, 'protagonist_identity', 'type'),
            'role': g(b, 'protagonist_identity', 'role_descriptor'),
        },
        '3-0b.epistemic_gap': {
            'present': g(b, 'epistemic_gap', 'present'),
            'description': g(b, 'epistemic_gap', 'gap_description'),
            'design_status': g(b, 'epistemic_gap', 'design_status'),
        },
        '3-0b.gap_resolution': {'expectation': g(b, 'gap_resolution', 'expectation')},
        '3-0c.failure_presence': {'value': g(c, 'failure_presence', 'value')},
        '3-0c.failure_triggers': {'types': g(c, 'failure_triggers', 'types', default=[])},
        '3-0c.failure_cost': {'value': g(c, 'failure_cost', 'value')},
        '3-0c.failure_scope': {'value': g(c, 'failure_scope', 'value')},
        '3b.primary_affect': {'label': g(aff, 'primary_affect', 'label')},
        '3b.primary_trajectory': {'shape': g(aff, 'primary_trajectory', 'shape')},
        '3b.secondary_affects': {
            'labels': [g(x, 'label') for x in (g(aff, 'secondary_affects', default=[]) or []) if isinstance(x, dict)],
        },
        '3b.tone': {'descriptors': g(aff, 'tone', 'descriptors', default=[])},
        '3b.somatic_address': {
            'level': g(aff, 'somatic_address', 'level'),
            'channels': g(aff, 'somatic_address', 'channels', default=[]),
        },
        '3b.transgression': {
            'ceiling': g(aff, 'transgression', 'ceiling', 'level'),
            'floor': g(aff, 'transgression', 'floor', 'level'),
        },
        '3c.core_thematic_axis': {
            'pole_a': g(th, 'core_thematic_axis', 'pole_a'),
            'pole_b': g(th, 'core_thematic_axis', 'pole_b'),
        },
        '3c.secondary_thematic_axis': {'approaches': g(th, 'secondary_thematic_axis', 'approaches', default=[])},
        '3c.moral_valence': {
            'best_case': g(th, 'moral_valence', 'best_case_framing', 'label'),
            'worst_case': g(th, 'moral_valence', 'worst_case_framing', 'label'),
        },
        '3d.viewpoint_handoff': {
            'ceiling': g(vp, 'viewpoint_handoff', 'ceiling', 'value'),
            'floor': g(vp, 'viewpoint_handoff', 'floor', 'value'),
            'count_min': g(vp, 'viewpoint_handoff', 'count', 'min'),
            'count_max': g(vp, 'viewpoint_handoff', 'count', 'max'),
        },
        '3d.viewpoint_excursions': {
            'ceiling': g(vp, 'viewpoint_excursions', 'ceiling', 'value'),
            'floor': g(vp, 'viewpoint_excursions', 'floor', 'value'),
            'types': g(vp, 'viewpoint_excursions', 'types', 'values', default=[]),
            'interactive': g(vp, 'viewpoint_excursions', 'interactive', 'value'),
        },
        '3e.timeline_structure': {'category': g(tl, 'timeline_structure', 'category')},
        '3e.timeline_duration': {
            'ceiling': g(tl, 'timeline_duration', 'ceiling', 'scale'),
            'floor': g(tl, 'timeline_duration', 'floor', 'scale'),
        },
        '3f.setting_structure': {
            'ceiling': g(st, 'setting_structure', 'ceiling', 'value'),
            'floor': g(st, 'setting_structure', 'floor', 'value'),
        },
        '3f.setting_scale': {
            'ceiling': g(st, 'setting_scale', 'ceiling', 'tier'),
            'floor': g(st, 'setting_scale', 'floor', 'tier'),
        },
        '3g.target_ending_count': {
            'min': g(cx, 'target_ending_count', 'min'),
            'max': g(cx, 'target_ending_count', 'max'),
        },
        '3g.branching_density': {'level': g(cx, 'branching_density', 'level')},
        '3g.state_richness': {
            'level': g(cx, 'state_richness', 'level'),
            'channels': g(cx, 'state_richness', 'channels', default=[]),
        },
    }


CLASS_RANK = {'constraint': 2, 'default': 1, 'free': 0}


def binding_for(field_id, constraint_map):
    """Strongest binding class among the map entries under this field id
    (the map lists leaf paths such as 3b.transgression.ceiling)."""
    fields = (constraint_map or {}).get('fields') or {}
    best = None
    for key, entry in fields.items():
        if key == field_id or key.startswith(field_id + '.') or key.startswith(field_id + '['):
            cls = entry.get('class', 'default')
            if best is None or CLASS_RANK.get(cls, 1) > CLASS_RANK.get(best, 1):
                best = cls
    return best or 'free'


def build_brief(bundle, constraint_map, cross_check):
    """The story brief: every phase-3 judgment's value plus its binding
    class, and the cross-check's resolutions. No notes, no tiers."""
    fields = {}
    for field_id, value in _fields(bundle).items():
        entry = dict(value)
        entry['binding'] = binding_for(field_id, constraint_map)
        fields[field_id] = entry

    resolved = []
    for check in (g(cross_check, 'checks', default=[]) or []):
        if not isinstance(check, dict):
            continue
        verdict = str(check.get('verdict', ''))
        if verdict in ('coherent', 'not_applicable', ''):
            continue
        resolved.append({
            'id': check.get('id'),
            'verdict': verdict,
            'summary': check.get('summary'),
            'winner': check.get('better_evidenced', ''),
            'resolution': check.get('resolution', ''),
        })
    brief = {
        'binding_legend': 'constraint: may not be contradicted; default: convention supplied it, '
                          'may be replaced with something more specific; free: nothing known, fill it',
        'fields': fields,
        'cross_check': {
            'primary_branch_source': g(cross_check, 'primary_branch_source', 'source'),
            'conflicts': resolved,
            'unresolved': g(cross_check, 'unresolved_for_next_phase', default=[]) or [],
        },
    }
    if (constraint_map or {}).get('suggested_budget'):
        brief['enrichment_budget'] = constraint_map['suggested_budget']
    return brief


def brief_lite(brief):
    """The handful of fields the per-node and review prompts need for tone
    and stakes; everything else stays out of those packets."""
    f = (brief or {}).get('fields') or {}

    def pick(field_id, *keys):
        entry = f.get(field_id) or {}
        return {k: entry.get(k) for k in keys}

    return {
        'decision': pick('3-0a.primary_decision_axis', 'label', 'description'),
        'theme': pick('3c.core_thematic_axis', 'pole_a', 'pole_b'),
        'protagonist': pick('3-0b.protagonist_identity', 'type', 'role'),
        'affect': {
            'primary': (f.get('3b.primary_affect') or {}).get('label'),
            'trajectory': (f.get('3b.primary_trajectory') or {}).get('shape'),
            'tone': (f.get('3b.tone') or {}).get('descriptors'),
            'somatic_channels': (f.get('3b.somatic_address') or {}).get('channels'),
            'transgression_ceiling': (f.get('3b.transgression') or {}).get('ceiling'),
        },
        'failure': {
            'presence': (f.get('3-0c.failure_presence') or {}).get('value'),
            'triggers': (f.get('3-0c.failure_triggers') or {}).get('types'),
            'cost': (f.get('3-0c.failure_cost') or {}).get('value'),
        },
        'epistemic_gap_present': (f.get('3-0b.epistemic_gap') or {}).get('present'),
    }


# ---------------------------------------------------------------- compact renderings

def _flat(value):
    if isinstance(value, list):
        return ', '.join(_flat(v) for v in value) or '(none)'
    if isinstance(value, dict):
        return '; '.join(f'{k} {_flat(v)}' for k, v in value.items())
    if value is None or value == '':
        return '(none)'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def field_line(field_id, entry):
    """One brief field as text: '3b.tone [constraint]: descriptors claustrophobic, tense'."""
    entry = entry or {}
    parts = [f'{k} {_flat(v)}' for k, v in entry.items() if k != 'binding']
    return f"{field_id} [{entry.get('binding', 'free')}]: " + '; '.join(parts)


# Extracted answers about the story's SIZE (how many endings, how often it
# forks). Step 2 strips the Kernel's shape clauses before phase 3 runs, so
# these come back as fallbacks, and shape reaches only the outline loop, as
# advisory targets. The premise steps are not shown them and the premise
# audit does not check against them.
SHAPE_LEVEL_FIELDS = ('3g.target_ending_count', '3g.branching_density')


def brief_lines(brief, only=None, skip=SHAPE_LEVEL_FIELDS):
    """The brief as one line per field. Every archived trace restated the
    brief to itself in roughly this form before doing anything else; giving
    it in this form to begin with is about half the characters of the JSON
    and leaves nothing to restate. `only` restricts to field ids with one
    of the given prefixes; `skip` drops field ids."""
    fields = (brief or {}).get('fields') or {}
    lines = []
    for field_id, entry in fields.items():
        if field_id in (skip or ()):
            continue
        if only and not any(field_id.startswith(p) for p in only):
            continue
        lines.append(field_line(field_id, entry))
    cross = (brief or {}).get('cross_check') or {}
    if not only:
        for c in cross.get('conflicts') or []:
            lines.append(f"cross-check {c.get('id')}: {c.get('summary')} -> the better-evidenced field is "
                         f"{c.get('winner') or '(undecided)'}; {c.get('resolution') or ''}".rstrip('; '))
        for u in cross.get('unresolved') or []:
            lines.append(f'cross-check unresolved: {_flat(u)}')
        if (brief or {}).get('enrichment_budget'):
            lines.append(f"enrichment_budget: {brief['enrichment_budget']}")
    return '\n'.join(lines)


def constraint_fields(brief):
    """[(n, field id, line)] for the fields whose binding is 'constraint':
    the table the premise verifier checks, numbered so its answers can be
    matched back without string comparison."""
    fields = (brief or {}).get('fields') or {}
    out = []
    for field_id, entry in fields.items():
        if (entry or {}).get('binding') == 'constraint' and field_id not in SHAPE_LEVEL_FIELDS:
            out.append((len(out) + 1, field_id, field_line(field_id, entry)))
    return out


def field_ids(brief):
    return list(((brief or {}).get('fields') or {}).keys())


def valid_serves(tag, brief):
    """A serves tag is valid when some part of it is a brief field id or a
    prefix of one ('3-0a' covers '3-0a.primary_decision_axis'). The old
    verifier spent forty lines of reasoning on this string comparison."""
    ids = field_ids(brief)
    for part in re.split(r'[,;]| and ', str(tag or '')):
        part = part.strip().split(':')[0].strip()
        if not part:
            continue
        if any(i == part or i.startswith(part + '.') or part.startswith(i) for i in ids):
            return True
    return False


_CLAUSE_SPLIT = re.compile(r'(?<=[.!?;])\s+|\s+[—–]\s+|\s+-\s+')


def kernel_clauses(kernel):
    """The Kernel cut into numbered clauses at sentence ends, semicolons
    and dashes. The verifier used to decide for itself what counted as a
    clause and argued with itself about it; it is now handed the list."""
    text = ' '.join((kernel or '').split())
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(text) if p and p.strip()]
    merged = []
    for p in parts:
        # a fragment of one or two words belongs to its neighbour
        if merged and len(p.split()) < 3:
            merged[-1] = merged[-1] + ' ' + p
        else:
            merged.append(p)
    return [(i + 1, c) for i, c in enumerate(merged)] or [(1, text)]


# ---------------------------------------------------------------- shape

ENDING_TIER_TO_LINES = {'one': 1, 'few': 2, 'several': 3, 'many': 5, 'unstated': 3}
LENGTH_TO_NODES = {'short': (4, 6), 'medium': (5, 8), 'long': (7, 10), 'unstated': (5, 8)}


_NUMBER_WORDS = {'two': 2, 'couple': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
                 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'dozen': 12}
# "one" and "single" count only when the phrase is about exactly one ending:
# "more than one ending" and "at least one of them happy" are not.
_ONE_ENDING = re.compile(r'^\W*(only |just |exactly )?(a |the )?(one|single|1)\b(?! or\b)')


def ending_tier_from_stated(stated):
    """The ending tier as a lookup when the Kernel gave a number: the
    smallest number stated ('6 or 7' -> 6 -> several), so a range never
    rounds the story up. None when no number is stated."""
    text = str(stated or '').lower()
    numbers = [int(n) for n in re.findall(r'\d+', text) if int(n) > 1]
    numbers += [v for w, v in _NUMBER_WORDS.items() if re.search(rf'\b{w}\b', text)]
    if not numbers:
        return 'one' if _ONE_ENDING.search(text) else None
    n = min(numbers)
    if n <= 1:
        return 'one'
    if n <= 3:
        return 'few'
    if n <= 6:
        return 'several'
    return 'many'


def shape_targets(shape):
    """Coarse structural targets from step 2's shape preferences. These are
    advisory numbers for the outline loop, never exact counts to hit."""
    shape = shape or {}
    endings = shape.get('endings') or {}
    tier = str(endings.get('tier', 'unstated') or 'unstated').lower()
    length = str(shape.get('length', 'unstated') or 'unstated').lower()
    linearity = str(shape.get('linearity', 'unstated') or 'unstated').lower()
    lo, hi = LENGTH_TO_NODES.get(length, LENGTH_TO_NODES['unstated'])
    return {
        'through_lines': ENDING_TIER_TO_LINES.get(tier, 3),
        'endings_stated': endings.get('stated', ''),
        'endings_tier': tier,
        'nodes_min': lo,
        'nodes_max': hi,
        'linear': linearity == 'linear',
        'choice_density': shape.get('choice_density', 'unstated'),
        'note': 'through_lines is how many distinct story lines (each with its own ending) the '
                'shape preference suggests; the review decides whether each next one is worth building.',
    }
