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
    protagonist=obj(who=S, history=S, wants=S, need=S, can_do=S, cannot_do=S, ties=arr(obj(who=S, what=S)), open=S, gender=enum(['f', 'm', 'n']), serves=S),
    arena=obj(description=S, serves=S),
    pressure=obj(description=S, clock_or_stock=S, serves=S),
    opposition=obj(who_or_what=S, wants=S, means=S, shown_by=S, serves=S),
    events=arr(obj(what=S, when=enum(['early', 'middle', 'late']), serves=S)),
    hidden_truth=nullable(obj(truth=S, who_knows=S, what_it_changes=S, serves=S)),
    mediation=obj(question=S, to_reach_pole_a=POLE, to_reach_pole_b=POLE, levers=arr(S), serves=S),
    price=obj(what=S, who_pays=S, why_final=S, serves=S),
    setups=arr(obj(plant=S, payoff=S)),
    rules=arr(obj(thing=S, terms=S)),
)

TURNS = obj(
    turns=arr(obj(id=I, situation=S, what_you_must_do=S, ways_through=arr(obj(way=S, cost=S)),
                  involves=arr(S), form=enum(TURN_FORMS), set_piece=STR_OR_NULL, serves=S)),
    complications=arr(obj(description=S, serves=S)),
)

CAST = obj(
    notes=S,
    cast_seeds=arr(obj(role=S, kind=enum(['individual', 'crowd']), speaks_for=STR_OR_NULL,
                       gender=enum(['f', 'm', 'n']), wants=S, holds=S, edge=STR_OR_NULL, tie=S, voice=STR_OR_NULL,
                       breaking_point=STR_OR_NULL, opposition=B)),
)

PREMISE_CHECK = obj(
    clauses=arr(obj(n=I, note=S, contradiction=B, quote=S)),
    constraints=arr(obj(n=I, note=S, violated=B, quote=S)),
    engine=arr(obj(id=S, note=S, holds=B, quote=S)),
    mechanics=arr(obj(material=S, note=S, permitted=B)),
)

PREMISE_REPAIR = obj(
    repair_log=arr(obj(finding=S, change=S, disagreement=S)),
    revised={'type': 'object'},
)

# ---------------------------------------------------------------- 3.8


def story_form(framework_ids, modifier_ids):
    return obj(reading=S, framework=enum(framework_ids), why=S, modifier=enum(modifier_ids), modifier_why=S)


# ---------------------------------------------------------------- step 4

BEAT_ENTRY = obj(beat=S, turn=INT_OR_NULL, way=INT_OR_NULL, event=INT_OR_NULL, plants=arr(I), pays=arr(I), adapted=S)
SKIPPED = arr(obj(beat=S, reason=S))
ANSWERS = ['pole_a', 'pole_b', 'mixed', 'neither']
# the world an ending leaves, in a form two endings can be compared by
ENDING = obj(title=S, summary=S, answer=enum(ANSWERS), standing=arr(S), lost=arr(S), changed=S, pays_price=B)

MAIN_LINE = obj(
    through_line=obj(title=S, motivation=S, strategy=S, turning_point=S),
    ending=ENDING,
    beats=arr(BEAT_ENTRY),
)

LINE_NODES = obj(
    nodes=arr(obj(id=S, title=S, summary=S, image=S, where=arr(S), who=arr(S))),
    new_locations=arr(obj(name=S, kind=S, why=S)),
    new_characters=arr(obj(label=S, kind=enum(['individual', 'crowd']), speaks_for=STR_OR_NULL, gender=enum(['f', 'm', 'n']),
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

# ---------------------------------------------------------------- stage A (arcs.py)

ARC_CAST = obj(cast=arr(obj(who=S, note=S, tier=enum(['supporting', 'functional']))))

UP_DOWN = enum(['up', 'down'])
UP_DOWN_OR_NULL = {'type': ['string', 'null'], 'enum': ['up', 'down', None]}
MOMENT = obj(node=S, kind=enum(['turn', 'reveal', 'test', 'demonstration']), change=S)
ARC = obj(
    who=S,
    state=obj(name=S, meaning=S, up_when=S, down_when=S),
    starts=S,
    moments=arr(MOMENT),
    resolutions=arr(obj(lines=arr(S), direction=UP_DOWN_OR_NULL, stands_with_you=B, becomes=S)),
)
ARC_PLAN = obj(
    visibility_note=S,
    state_visibility=enum(['signposted', 'observed', 'hidden']),
    arcs=arr(ARC),
    light_arcs=arr(obj(who=S, starts=S, moments=arr(obj(node=S, change=S)), ends=S)),
    protagonist={'type': 'object', 'additionalProperties': obj(arc=S)},
    setups=arr(obj(setup=S, payoff=S, what=S)),
    pattern_shifts=arr(obj(required=['state', 'direction', 'at', 'does', 'why'], state=S, direction=UP_DOWN, at=S,
                           does=enum(['resolution', 'ending', 'line']), to=S, why=S)),
)
OPTION = obj(do=S, effect=S, moves=arr(obj(state=S, direction=UP_DOWN)), active=B)
MINOR_NODE = obj(
    required=['after', 'kind', 'serves', 'title', 'summary', 'image', 'who'],
    after=S, kind=enum(['opportunity', 'revelation', 'demonstration', 'resolution']), serves=arr(S),
    title=S, summary=S, image=S, who=arr(S), options=arr(OPTION), tell=obj(at=S, how=S), warns=S,
)
LINE_EXPANSION = obj(notes=S, minor_nodes=arr(MINOR_NODE))

# ---------------------------------------------------------------- stage B (world.py)

VARIANT = obj(state=STR_OR_NULL, direction=UP_DOWN_OR_NULL, after=STR_OR_NULL, text=S)
WORLD_CHARACTER = obj(
    notes=S, history=STR_OR_NULL, description=arr(VARIANT), here=arr(VARIANT),
    topics=arr(obj(required=['label', 'known_after', 'says'], label=S, known_after=STR_OR_NULL, says=arr(VARIANT),
                   moves=arr(obj(state=S, direction=UP_DOWN)))),
)
WORLD_FUNCTIONAL = obj(note=S, people=arr(obj(who=S, description=S, here=S, topics=arr(obj(label=S, says=S)))))
WORLD_PLACE = obj(
    notes=S, rooms=arr(obj(name=S, description=S)),
    exits=arr(obj(**{'from': S}, to=S, label=S, back_label=S)),
    objects=arr(obj(name=S, room=S, description=S, portable=B, story=B)),
)
WORLD_MAP = obj(
    notes=S, connective=arr(obj(name=S, description=S, examinable=arr(obj(name=S, description=S)))),
    adjacent=arr(obj(from_room=S, to_room=S, label=S, back_label=S)),
)
WORLD_CONVERSATION = obj(notes=S, lines=arr(obj(subject=S, says=arr(VARIANT))))
WORLD_YOU = obj(
    notes=S, description=arr(VARIANT), carrying=arr(obj(name=S, description=S)),
    think=arr(obj(label=S, known_after=STR_OR_NULL, says=arr(VARIANT))),
)

# ---------------------------------------------------------------- stage D (compile_scenes.py)

SCENE_ACTION = obj(required=['verb', 'object', 'detail', 'label', 'room', 'text'],
                   verb=S, object=STR_OR_NULL, detail=STR_OR_NULL, label=S, room=STR_OR_NULL, text=S,
                   neutral=B, reveals=arr(S), leads_to=STR_OR_NULL, once=B)
SCENE = obj(
    notes=S, opening=S, start_room=S,
    placement=arr(obj(who=S, room=S)),
    room_text=arr(obj(room=S, variants=arr(VARIANT))),
    moments=arr(obj(required=['node', 'options'], node=S, options=arr(SCENE_ACTION), lapse=obj(after=I, text=S))),
    actions=arr(SCENE_ACTION),
    events=arr(obj(required=['text'], text=S, after_turns=INT_OR_NULL, after=STR_OR_NULL)),
    nudges=arr(obj(after=I, text=S)),
    props=arr(obj(name=S, room=S, description=S, portable=B)),
)

ALL = {
    'SHAPE': SHAPE, 'PROMISES': PROMISES, 'ENGINE': ENGINE, 'TURNS': TURNS, 'CAST': CAST,
    'PREMISE_CHECK': PREMISE_CHECK, 'PREMISE_REPAIR': PREMISE_REPAIR, 'MAIN_LINE': MAIN_LINE,
    'LINE_NODES': LINE_NODES, 'NEXT_LINE': NEXT_LINE, 'BRANCH_PLAN': BRANCH_PLAN, 'DIVERGENCE': DIVERGENCE,
    'OUTLINE_JUDGE': OUTLINE_JUDGE, 'ARC_CAST': ARC_CAST, 'ARC_PLAN': ARC_PLAN, 'LINE_EXPANSION': LINE_EXPANSION,
    'WORLD_CHARACTER': WORLD_CHARACTER, 'WORLD_FUNCTIONAL': WORLD_FUNCTIONAL, 'WORLD_PLACE': WORLD_PLACE,
    'WORLD_MAP': WORLD_MAP, 'WORLD_CONVERSATION': WORLD_CONVERSATION, 'WORLD_YOU': WORLD_YOU, 'SCENE': SCENE,
}
