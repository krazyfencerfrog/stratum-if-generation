"""JSON schemas for Ollama's structured outputs (the `format` parameter).

A schema removes a class of failure outright: the response cannot be
unparseable, cannot miss a key, and cannot put a word outside an enum
where a tier or a beat id belongs. It also fixes the ORDER of keys, which
is what makes "schema-first reasoning" work on the calls that run with
thinking off: a short free-text field placed first (reading, notes,
assessment, note) is where the model deliberates, in the open and at a
bounded length, before it commits to the fields that follow.

Whether a schema is actually sent is the client's decision (see
OllamaClient.structured): by default only on thinking-off calls, where
structured output is long-supported; on thinking calls once
probe_ollama.py has shown the server handles both together. Every
validator in the pipeline still runs, so a call made without its schema is
checked exactly as before.

Where a value must come from a set known only at call time (the
shortlisted frameworks and the licensed modifiers) the schema is built by
a function so the set becomes an enum.
"""

S = {'type': 'string'}
B = {'type': 'boolean'}
I = {'type': 'integer'}
INT_OR_NULL = {'type': ['integer', 'null']}
STR_OR_NULL = {'type': ['string', 'null']}


def obj(required=None, **props):
    return {'type': 'object', 'properties': props, 'required': required if required is not None else list(props)}


def arr(items):
    return {'type': 'array', 'items': items}


def enum(values):
    return {'type': 'string', 'enum': list(values)}


def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


TURN_FORMS = ['discover', 'persuade', 'trade', 'confront', 'conceal_or_reveal', 'sabotage',
              'endure', 'choose_whom', 'rescue', 'escape']

# ---------------------------------------------------------------- step 2

SHAPE = obj(
    reading=S,
    content_kernel=S,
    shape=obj(
        endings=obj(tier=enum(['one', 'few', 'several', 'many', 'unstated']), stated=S),
        linearity=enum(['linear', 'branching', 'unstated']),
        choice_density=enum(['sparse', 'moderate', 'dense', 'unstated']),
        length=enum(['short', 'medium', 'long', 'unstated']),
        removed_clauses=arr(S),
    ),
)

# ---------------------------------------------------------------- 3.4

PROMISES = obj(
    reading=S,
    genre=S,
    player_fantasy=S,
    promises=arr(obj(what=S, why=S, in_kernel=B)),
    set_pieces=arr(obj(scene=S, where=S)),
    tone_engine=S,
    obligatory_cast=arr(S),
    must_not=arr(S),
)

# ---------------------------------------------------------------- 3.5

POLE = obj(pole=S, what_you_must_do=S, cost=S)

ENGINE = obj(
    protagonist=obj(who=S, wants=S, can_do=S, cannot_do=S, serves=S),
    arena=obj(description=S, serves=S),
    pressure=obj(description=S, clock_or_stock=S, serves=S),
    opposition=obj(who_or_what=S, wants=S, means=S, serves=S),
    events=arr(obj(what=S, when=enum(['early', 'middle', 'late']), serves=S)),
    hidden_truth=nullable(obj(truth=S, who_knows=S, what_it_changes=S, serves=S)),
    mediation=obj(question=S, to_reach_pole_a=POLE, to_reach_pole_b=POLE, levers=arr(S), serves=S),
)

TURNS = obj(
    turns=arr(obj(id=I, situation=S, what_you_must_do=S, ways_through=arr(obj(way=S, cost=S)),
                  involves=arr(S), form=enum(TURN_FORMS), set_piece=STR_OR_NULL, serves=S)),
    complications=arr(obj(description=S, serves=S)),
)

CAST = obj(
    notes=S,
    cast_seeds=arr(obj(role=S, kind=enum(['individual', 'crowd']), speaks_for=STR_OR_NULL,
                       wants=S, holds=S, edge=STR_OR_NULL, tie=S, voice=STR_OR_NULL,
                       breaking_point=STR_OR_NULL, opposition=B)),
)

PREMISE_CHECK = obj(
    clauses=arr(obj(n=I, note=S, contradiction=B, quote=S)),
    constraints=arr(obj(n=I, note=S, violated=B, quote=S)),
    engine=arr(obj(id=S, note=S, holds=B, quote=S)),
    mechanics=arr(obj(material=S, note=S)),
)

PREMISE_REPAIR = obj(
    repair_log=arr(obj(finding=S, change=S, disagreement=S)),
    revised={'type': 'object'},
)

# ---------------------------------------------------------------- 3.8


def story_form(framework_ids, modifier_ids):
    return obj(reading=S, framework=enum(framework_ids), why=S, modifier=enum(modifier_ids), modifier_why=S)


# ---------------------------------------------------------------- step 4

BEAT_ENTRY = obj(beat=S, turn=INT_OR_NULL, way=INT_OR_NULL, event=INT_OR_NULL, adapted=S)
SKIPPED = arr(obj(beat=S, reason=S))
ANSWERS = ['pole_a', 'pole_b', 'mixed', 'neither']
# the world an ending leaves, in a form two endings can be compared by
ENDING = obj(title=S, summary=S, answer=enum(ANSWERS), standing=arr(S), lost=arr(S), changed=S)

MAIN_LINE = obj(
    through_line=obj(title=S, motivation=S, strategy=S, turning_point=S),
    ending=ENDING,
    beats=arr(BEAT_ENTRY),
)

LINE_NODES = obj(
    nodes=arr(obj(id=S, title=S, summary=S, image=S, where=arr(S), who=arr(S))),
    new_locations=arr(obj(name=S, kind=S, why=S)),
    new_characters=arr(obj(label=S, kind=enum(['individual', 'crowd']), speaks_for=STR_OR_NULL,
                           wants=S, holds=S, why=S)),
)

NEXT_LINE = obj(
    assessment=S,
    recommendation=enum(['continue', 'stop']),
    seed=nullable(obj(motivation=S, strategy=S, diverges_at=S, trigger=S, why_different=S)),
)

SEED = obj(motivation=S, strategy=S, diverges_at=S, trigger=S, trigger_kind=enum(['act', 'accumulated']),
           way=INT_OR_NULL, ending=ENDING, why_different=S)

BRANCH_PLAN = obj(
    assessment=S,
    seeds=arr(SEED),
)

DIVERGENCE = obj(
    status=enum(['proposed', 'nothing_worth_building']),
    why=S,
    through_line=nullable(obj(title=S, motivation=S, strategy=S, turning_point=S, differs_from=S)),
    divergence=nullable(obj(diverges_at=S, trigger=S, trigger_kind=enum(['act', 'accumulated']), way=INT_OR_NULL,
                            instead_of=S, opportunity=STR_OR_NULL, shift=S)),
    ending=nullable(ENDING),
    beats=arr(BEAT_ENTRY),
    skipped_beats=SKIPPED,
    rejoins_at=STR_OR_NULL,
)

# ---------------------------------------------------------------- 4e: the outline judge

JUDGE_AXES = ['plot', 'people', 'reveals', 'agency', 'specificity', 'genre']

OUTLINE_JUDGE = obj(
    reading=S,
    scores=obj(**{axis: obj(note=S, score=I) for axis in JUDGE_AXES}),
    best_thing=S,
    worst_thing=S,
    would_play=B,
)

ALL = {
    'SHAPE': SHAPE, 'PROMISES': PROMISES, 'ENGINE': ENGINE, 'TURNS': TURNS, 'CAST': CAST,
    'PREMISE_CHECK': PREMISE_CHECK, 'PREMISE_REPAIR': PREMISE_REPAIR, 'MAIN_LINE': MAIN_LINE,
    'LINE_NODES': LINE_NODES, 'NEXT_LINE': NEXT_LINE, 'BRANCH_PLAN': BRANCH_PLAN, 'DIVERGENCE': DIVERGENCE,
    'OUTLINE_JUDGE': OUTLINE_JUDGE,
}
