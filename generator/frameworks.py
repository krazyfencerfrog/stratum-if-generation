"""The story-framework library and the computed shortlist.

A framework is a short ordered list of beats (config/frameworks.json). It
scaffolds the outline loop: every node is tagged with a beat, every line is
checked for beat coverage, and a branch is expressed as "the same beats with
different filler after the divergence point". It never drives how many
lines or endings get built.

Which frameworks suit a story is mostly a lookup over the brief (affect
trajectory, failure model, timeline, setting footprint, epistemic gap,
decision mechanism), so it is computed here: `shortlist()` scores every
framework and returns the best three with the reasons, `available_modifiers()`
returns the modifiers the brief licenses, and the model's only job
(prompts/s3_8_story_form.prompt) is to pick among them with the premise in
view. three_act is the fallback: it carries a fixed base score, so it is
offered only when few other frameworks fit.

The scoring rules are heuristics, not measurements. They are data: edit
RULES and re-run; nothing downstream depends on the numbers.
"""

import os
import re
import json
import hashlib

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_PATH = os.path.join(THIS_DIR, '..', 'config', 'frameworks.json')

FALLBACK = 'three_act'
FALLBACK_SCORE = 2.0
SHORTLIST_SIZE = 3

_library = None


def library():
    global _library
    if _library is None:
        with open(LIBRARY_PATH, encoding='utf-8') as f:
            _library = json.load(f)
    return _library


def framework(framework_id):
    for fw in library()['frameworks']:
        if fw['id'] == framework_id:
            return fw
    raise KeyError(f'unknown framework {framework_id}')


def framework_ids():
    return [fw['id'] for fw in library()['frameworks']]


def modifier(modifier_id):
    for m in library()['modifiers']:
        if m['id'] == modifier_id:
            return m
    return library()['modifiers'][0]


def beat_ids(fw):
    return [b['id'] for b in fw['beats']]


def required_beats(fw):
    return [b['id'] for b in fw['beats'] if b.get('required', True)]


# ---------------------------------------------------------------- features

def _strings(value):
    """The strings in a model-written list, as a set; anything else in it
    (or anything that is not a list) is ignored."""
    return {x for x in (value if isinstance(value, list) else [value]) if isinstance(x, str)}


def features(brief, kernel=''):
    """The handful of brief values the scoring rules read, flattened."""
    f = (brief or {}).get('fields') or {}

    def v(field_id, key, default=None):
        value = (f.get(field_id) or {}).get(key)
        return default if value is None else value

    tone = ' '.join(str(t).lower() for t in (v('3b.tone', 'descriptors', []) or []))
    return {
        'trajectory': v('3b.primary_trajectory', 'shape', 'sustained'),
        'transgression': v('3b.transgression', 'ceiling', 1) or 1,
        'tone': tone,
        'failure': v('3-0c.failure_presence', 'value', 'none'),
        'triggers': _strings(v('3-0c.failure_triggers', 'types', [])),
        'failure_scope': v('3-0c.failure_scope', 'value', 'not_applicable'),
        'timeline': v('3e.timeline_structure', 'category', 'linear'),
        'duration': v('3e.timeline_duration', 'ceiling', 'hours_to_days'),
        'setting_structure': v('3f.setting_structure', 'ceiling', 'single'),
        'setting_scale': v('3f.setting_scale', 'ceiling', 'room_or_building'),
        'gap_designed': bool(v('3-0b.epistemic_gap', 'present', False))
                        and v('3-0b.epistemic_gap', 'design_status', '') == 'designed',
        'mechanism': v('3-0a.decision_mechanism', 'shape', 'recurring_instances'),
        'decision_binding': v('3-0a.primary_decision_axis', 'binding', 'free'),
        'handoff': v('3d.viewpoint_handoff', 'ceiling', 'single'),
        'excursions': v('3d.viewpoint_excursions', 'ceiling', 'not_indicated'),
        'excursion_types': _strings(v('3d.viewpoint_excursions', 'types', [])),
        'valence_best': str(v('3c.moral_valence', 'best_case', '') or '').lower(),
        'kernel': (kernel or '').lower(),
    }


LIGHT_TONE = ('funny', 'comic', 'light', 'playful', 'wry', 'warm', 'swashbuckling', 'adventurous', 'romp')
QUIET_TONE = ('cozy', 'cosy', 'quiet', 'gentle', 'relaxing', 'contemplative', 'tender', 'wistful', 'elegiac')
DARK_VALENCE = ('tragic', 'pyrrhic', 'hollow', 'doomed', 'ruin', 'bleak', 'nihilis', 'downfall', 'damn')


def _any(words, text):
    return any(w in text for w in words)


# (framework id, points, reason shown to the model, predicate over features)
RULES = [
    ('fichtean_curve', 2, '3b.primary_trajectory is escalating', lambda x: x['trajectory'] == 'escalating'),
    ('fichtean_curve', 1, '3e.timeline_duration is hours_to_days', lambda x: x['duration'] == 'hours_to_days'),
    ('fichtean_curve', 1, '3-0c names a failure the pressure can run into', lambda x: x['failure'] in ('soft', 'hard')),
    ('fichtean_curve', 1, '3-0c.failure_triggers gives the crises a clock or a stock',
     lambda x: bool(x['triggers'] & {'time_pressure', 'resource_depletion', 'hazard_or_wrong_turn', 'incapacitation_or_death'})),
    ('fichtean_curve', 1, '3e.timeline_structure is single_moment', lambda x: x['timeline'] == 'single_moment'),
    ('fichtean_curve', -2, 'no failure and a gentle ceiling leave nothing for crises to threaten',
     lambda x: x['failure'] == 'none' and x['transgression'] <= 2),

    ('seven_point', 2, '3-0b.epistemic_gap is designed: the last piece is a revelation', lambda x: x['gap_designed']),
    ('seven_point', 1, '3-0a.decision_mechanism is single_fork: the story builds to one choice', lambda x: x['mechanism'] == 'single_fork'),
    ('seven_point', 1, '3-0c.failure_triggers names exposure or a wrong answer',
     lambda x: bool(x['triggers'] & {'detection_or_exposure', 'incorrect_resolution'})),
    ('seven_point', 1, '3b.primary_trajectory rises (escalating or arc)', lambda x: x['trajectory'] in ('escalating', 'arc')),
    ('seven_point', 1, '3-0c.failure_presence is hard', lambda x: x['failure'] == 'hard'),

    ('freytag', 2, '3b.primary_trajectory is arc: a rise, a turn, an unwinding', lambda x: x['trajectory'] == 'arc'),
    ('freytag', 2, "3c.moral_valence's best case is still dark", lambda x: _any(DARK_VALENCE, x['valence_best'])),
    ('freytag', 1, '3b.transgression ceiling is 4 or more', lambda x: x['transgression'] >= 4),

    ('heros_journey', 2, '3f.setting_structure is dispersed: there is a journey', lambda x: x['setting_structure'] == 'dispersed'),
    ('heros_journey', 1, '3f.setting_scale is world or larger', lambda x: x['setting_scale'] in ('world', 'multi_world')),
    ('heros_journey', 1, '3e.timeline_duration is weeks or longer',
     lambda x: x['duration'] in ('weeks_to_months', 'years', 'generations_plus')),
    ('heros_journey', 1, '3b.primary_trajectory is transforming or arc', lambda x: x['trajectory'] in ('transforming', 'arc')),
    ('heros_journey', -1, '3f.setting_structure is single: nowhere to leave for', lambda x: x['setting_structure'] == 'single'),

    ('save_the_cat', 1, '3b.primary_trajectory is arc or oscillating', lambda x: x['trajectory'] in ('arc', 'oscillating')),
    ('save_the_cat', 1, '3-0c.failure_presence is soft', lambda x: x['failure'] == 'soft'),
    ('save_the_cat', 1, '3b.transgression ceiling is 3 or less', lambda x: x['transgression'] <= 3),
    ('save_the_cat', 1, 'the decision axis is a genre default: the premise promises a genre', lambda x: x['decision_binding'] == 'default'),
    ('save_the_cat', 1, '3b.tone is light', lambda x: _any(LIGHT_TONE, x['tone'])),

    ('story_circle', 3, '3e.timeline_structure is looping', lambda x: x['timeline'] == 'looping'),
    ('story_circle', 1, '3b.primary_trajectory is transforming', lambda x: x['trajectory'] == 'transforming'),
    ('story_circle', 1, '3f.setting_scale is room_or_building: a small world to leave and return to',
     lambda x: x['setting_scale'] == 'room_or_building'),
    ('story_circle', 1, '3-0a.decision_mechanism is continuous_pressure: the change is in the protagonist',
     lambda x: x['mechanism'] == 'continuous_pressure'),

    ('kishotenketsu', 2, '3-0c.failure_presence is none', lambda x: x['failure'] == 'none'),
    ('kishotenketsu', 2, '3b.transgression ceiling is 2 or less', lambda x: x['transgression'] <= 2),
    ('kishotenketsu', 1, '3b.primary_trajectory is sustained or diminishing', lambda x: x['trajectory'] in ('sustained', 'diminishing')),
    ('kishotenketsu', 1, '3b.tone is quiet', lambda x: _any(QUIET_TONE, x['tone'])),
    ('kishotenketsu', -3, '3-0c.failure_presence is hard', lambda x: x['failure'] == 'hard'),
    ('kishotenketsu', -1, '3b.primary_trajectory is escalating', lambda x: x['trajectory'] == 'escalating'),
]

# A form the Kernel names outright is content (step 2 keeps it), so it binds.
NAMED_FORMS = [
    ('freytag', r'\b(5|five)[- ]act\b|\btraged(y|ies)\b'),
    ('heros_journey', r"hero'?s[’']? journey|\bmonomyth\b"),
    ('three_act', r'\b(3|three)[- ]act\b'),
    ('kishotenketsu', r'kish[oō]tenketsu'),
    ('save_the_cat', r'save the cat'),
    ('story_circle', r'story circle'),
    ('seven_point', r'\b(7|seven)[- ]point\b'),
    ('fichtean_curve', r'fichtean'),
]


def named_form(kernel):
    text = (kernel or '').lower()
    for framework_id, pattern in NAMED_FORMS:
        if re.search(pattern, text):
            return framework_id
    return None


def score_all(brief, kernel=''):
    """{framework id: {'score', 'reasons', 'against'}} for every framework."""
    x = features(brief, kernel)
    out = {fw['id']: {'score': 0.0, 'reasons': [], 'against': []} for fw in library()['frameworks']}
    out[FALLBACK]['score'] = FALLBACK_SCORE
    out[FALLBACK]['reasons'].append('the general-purpose fallback; fits any story with a want and an opposition')
    for framework_id, points, reason, predicate in RULES:
        try:
            hit = predicate(x)
        except (KeyError, TypeError):
            hit = False
        if hit:
            out[framework_id]['score'] += points
            (out[framework_id]['reasons'] if points > 0 else out[framework_id]['against']).append(reason)
    return out


def shortlist(brief, kernel='', story_id='', length='unstated'):
    """The candidates the story-form step chooses among: the best three by
    score, with the reasons. A form the Kernel names is the only candidate.
    A stated short length takes a point off the eight-beat frameworks.
    Presentation order is shuffled by a hash of the story id, so position
    in the list carries no signal and repeated runs of one story agree."""
    named = named_form(kernel)
    scores = score_all(brief, kernel)
    if length == 'short':
        for fw in library()['frameworks']:
            if len(required_beats(fw)) > 6:
                scores[fw['id']]['score'] -= 1
                scores[fw['id']]['against'].append('the Kernel asked for a short story and this framework has many beats')
    if named:
        chosen = [named]
        scores[named]['reasons'].insert(0, 'the Kernel names this form; it binds')
    else:
        order = framework_ids()
        ranked = sorted(order, key=lambda i: (-scores[i]['score'], order.index(i)))
        chosen = ranked[:SHORTLIST_SIZE]
        chosen.sort(key=lambda i: hashlib.sha256(f'{story_id}:{i}'.encode()).hexdigest())
    out = []
    for framework_id in chosen:
        fw = framework(framework_id)
        out.append({
            'id': fw['id'],
            'name': fw['name'],
            'shape': fw['shape'],
            'beats': [b['name'] for b in fw['beats']],
            'fits_because': scores[framework_id]['reasons'] or ['nothing in the brief points at it'],
            'fits_less_because': scores[framework_id]['against'],
        })
    return {'candidates': out, 'named_in_kernel': named,
            'scores': {k: v['score'] for k, v in scores.items()}}


def available_modifiers(brief, kernel=''):
    """The modifiers the brief licenses. A modifier that needs something the
    extraction did not find (a clock, a second timeline, a second viewpoint)
    is not offered, so the story-form step cannot invent one."""
    x = features(brief, kernel)
    ids = ['none']
    if x['trajectory'] == 'escalating' or x['failure_scope'] == 'pervasive':
        ids.append('in_medias_res')
    if x['triggers'] & {'time_pressure', 'resource_depletion'}:
        ids.append('countdown')
    if x['excursions'] in ('required', 'invited') and x['excursion_types'] & {'third_party_pov', 'flashback', 'dream_or_vision'}:
        ids.append('frame')
    if x['timeline'] in ('multi_timeline', 'clustered', 'nonlinear'):
        ids.append('braided_timelines')
    if x['timeline'] == 'looping':
        ids.append('loop')
    if x['mechanism'] == 'recurring_instances' and x['failure'] in ('none', 'soft') and x['trajectory'] != 'escalating':
        ids.append('episodic')
    if x['handoff'] == 'multi_hop':
        ids.append('relay')
    return [{'id': m['id'], 'name': m['name'], 'effect': m['effect'] or 'the framework as it stands'}
            for m in library()['modifiers'] if m['id'] in ids]


def node_range(fw, nodes_min, nodes_max):
    """The advisory node-count range for one line on this framework: never
    fewer than its required beats, never so few above them that a premise
    turn has nowhere to go."""
    need = len(required_beats(fw))
    lo = max(nodes_min, need)
    hi = max(nodes_max, lo + 2)
    return lo, hi
