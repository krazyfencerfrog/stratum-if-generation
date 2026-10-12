"""Computed views and checks over the story document (<id>_story.json).

Everything here is a pure function of the document: no model, no pipeline
state. The outline loop calls these after every change; the test script
calls check_story() on finished stories; a later reconciliation stage can
call the same functions after it has annotated the document.

Derived views (recomputed, never asked of a model):
  derive_edges   the graph's edges, from the lines' paths and divergences
  derive_grid    lines x framework beats: which nodes fill which beat
  derive_hooks   premise-turn options no line has taken, with their nodes
  derive_usage   which nodes use each character and location

check_story returns {"findings": [...], "notes": [...]}. A FINDING is a
broken invariant (the graph does not hold together, a required beat is
uncovered without a reason, a turn is placed twice); the loop's validators
are meant to make these impossible, so one appearing is a bug or a
hand-edited file. A NOTE is something a person or a later stage should
look at (an unused character, a line that never shows the opposition).
"""

import re

def norm(text):
    """Comparison key for a register name or a role label: case,
    punctuation and a LEADING article do not distinguish two places or two
    people. Nothing else is dropped: "Sector A" and "Sector B" differ."""
    s = re.sub(r'[^a-z0-9 ]+', ' ', str(text or '').lower())
    s = ' '.join(s.split())
    return re.sub(r'^(the|a|an) ', '', s)


def speaks_for(character, crowd):
    return character.get('kind') != 'crowd' and bool(norm(character.get('speaks_for'))) \
        and norm(character.get('speaks_for')) == norm(crowd.get('label'))


MENU_TRIGGER_RE = re.compile(r'^\s*you\s+(choose|chose|decide|decided|pick|picked|select|selected|opt|opted)\b', re.IGNORECASE)

SECTOR_GROUP_RE = re.compile(
    r'\b(?:sector|district|ward|block|deck|bay|vault|zone|squad|unit|division|clan|house)\s+([0-9]+|[a-z]\b)',
    re.IGNORECASE
)

FACTION_GROUP_RE = re.compile(
    r'\b(?:the\s+)?([A-Za-z0-9_\'-]+)\s+(?:faction|clan|guild|tribe|syndicate|union)\b',
    re.IGNORECASE
)

FACELESS_GROUP_RE = re.compile(
    r'\b(?:the\s+)?(?:other|nameless|weakest|unnamed|remaining|rest of the)\s+(?:sector|district|ward|block|deck|bay|vault|zone|faction|crew|family|miners|people|group|colonists|citizens|inhabitants)\b'
    r'|\b(?:the\s+)?(?:sector|district|ward|block|deck|bay|vault|zone|faction|group|people)\s+whose\s+people\b'
    r'|\b(?:the\s+)?(?:sector|district|ward|block|deck|bay|vault|zone|faction|group)\s+whose\s+(?:air|water|food|lives|margin|weakest)\b',
    re.IGNORECASE
)


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def competing_groups_in_turns(turns):
    """Detects distinct groups, sectors, or factions referenced across turns.
    Returns a dict mapping normalized group key -> display label (e.g. 'sector 4' -> 'Sector 4').
    Only returns groups when 2 or more distinct groups of the same family are found, indicating
    competing dilemma poles or trade-offs."""
    sectors = {}
    factions = {}
    for t in as_list(turns):
        texts = [t.get('situation', ''), t.get('what_you_must_do', '')]
        for w in t.get('ways_through') or []:
            if isinstance(w, dict):
                texts.extend([w.get('way', ''), w.get('cost', '')])
        for inv in t.get('involves') or []:
            texts.append(str(inv))
        for text in texts:
            if not text:
                continue
            for m in SECTOR_GROUP_RE.finditer(text):
                lbl = m.group(0).strip()
                sectors[norm(lbl)] = lbl
            for m in FACTION_GROUP_RE.finditer(text):
                lbl = m.group(0).strip()
                factions[norm(lbl)] = lbl

    res = {}
    if len(sectors) >= 2:
        res.update(sectors)
    if len(factions) >= 2:
        res.update(factions)
    return res


NON_AGENT_ROLE_RE = re.compile(
    r"\b(maintenance drone|repair drone|surveillance drone|recon drone|drone|autopilot|"
    r"reactor core|power cells?|battery|generator|compressor|pump|valve|bulkhead|"
    r"terminal|sensor|recycler|accumulator|engine)\b",
    re.I
)

AGENT_TITLE_RE = re.compile(
    r"\b(pilot|operator|technician|mechanic|engineer|handler|master|chief|specialist|"
    r"officer|crew|worker|driver|keeper|controller|inspector|guard|clerk|attendant|"
    r"tender|user|builder|programmer|captain|navigator|steward)\b",
    re.I
)

HARDWARE_SPECS_RE = re.compile(
    r"\b(diagnostic cycle|charging bay|charging dock|oil pressure|logic loops?|firmware|"
    r"hardware specs?|maintenance loop|system protocol|recharge bay|operating system|"
    r"factory settings?|power cells? (?:that can|to) stabilize|spare power cells?|"
    r"built to serve the ship's systems)\b",
    re.I
)

MACHINE_VOICE_RE = re.compile(
    r"\b(status beeps?|error logs?|error codes?|audio logs?|diagnostic logs?|beeps and boops)\b|"
    r"['\"]?\b(error|alert|warning|priority|offline|standby)[\.:]",
    re.I
)

ROUTINE_WANTS_RE = re.compile(
    r"\b(diagnostic cycle|return to (?:the )?charg|recharge|maintenance loop|await(?:ing)? orders|"
    r"execute protocol|run routine)\b",
    re.I
)


def is_non_agent_role(role):
    """Returns True if the role describes a non-agent tool, hardware device,
    drone, or consumable prop without an agentic profession/title."""
    r = str(role or '').strip()
    return bool(NON_AGENT_ROLE_RE.search(r) and not AGENT_TITLE_RE.search(r))


def check_seed_agency(seed):
    """Verifies that a cast seed represents an agent with dramatic agency,
    rejecting consumable tools, hardware devices, and non-agent entities."""
    if not isinstance(seed, dict):
        return None
    role = str(seed.get('role', '') or seed.get('label', '')).strip()
    wants = str(seed.get('wants', '')).strip()
    holds = str(seed.get('holds', '')).strip()
    edge = str(seed.get('edge', '')).strip()
    tie = str(seed.get('tie', '')).strip()
    voice = str(seed.get('voice', '')).strip()
    all_text = f"{wants} {holds} {edge} {tie} {voice}"

    # 1. Non-agent role name (e.g., 'the maintenance drone', 'the battery', 'the reactor core')
    if is_non_agent_role(role):
        return (f"'{role}' is a consumable tool or object, not a dramatic agent. "
                f"Model it as an object/fixture in the world and seed a character with interpersonal agency instead.")

    # 2. Hardware specs, routine loops, or machine voice on any seed
    if (MACHINE_VOICE_RE.search(voice) or
            HARDWARE_SPECS_RE.search(all_text) or
            ROUTINE_WANTS_RE.search(wants)):
        return (f"'{role}' is a consumable tool or object, not a dramatic agent. "
                f"Model it as an object/fixture in the world and seed a character with interpersonal agency instead.")

    return None


def validate_cast(cast_seeds, turns):
    """Checks that:
    1. The cast represents all competing groups, sectors, or factions
       referenced in dramatic turns, avoiding asymmetric dilemmas where one side is
       personified and the competing side is an unrepresented collective.
    2. Cast seeds do not represent non-agent tools, hardware, vehicles, or consumable
       props lacking interpersonal agency or moral stakes."""
    groups = competing_groups_in_turns(turns)
    problems = []
    seeds = as_list(cast_seeds)
    if groups:
        for g_norm, g_label in groups.items():
            represented = False
            for s in seeds:
                if not isinstance(s, dict):
                    continue
                role = norm(s.get('role', '')) or norm(s.get('label', ''))
                speaks = norm(s.get('speaks_for', ''))
                name = norm(s.get('name', ''))
                wants = norm(s.get('wants', ''))
                holds = norm(s.get('holds', ''))
                tie = norm(s.get('tie', ''))
                if (g_norm in role or g_norm in speaks or g_norm in name or
                        g_norm in wants or g_norm in holds or g_norm in tie):
                    represented = True
                    break
            if not represented:
                problems.append(
                    f"competing dilemma group/sector {g_label!r} is referenced in turns but has no representative "
                    f"in the cast (must appear in role or speaks_for of a cast seed)"
                )
    for s in seeds:
        if not isinstance(s, dict):
            continue
        prob = check_seed_agency(s)
        if prob:
            problems.append(prob)
    return problems


def beat_order(story):
    return [b['id'] for b in as_list((story.get('framework') or {}).get('beats'))]


def beat_index(story, beat_id):
    order = beat_order(story)
    return order.index(beat_id) if beat_id in order else -1


def line_ids(story):
    return list(story.get('line_order') or (story.get('lines') or {}).keys())


# ---------------------------------------------------------------- derived views

def derive_edges(story):
    """One edge per consecutive pair on any line's path. An edge is a
    'branch' when it is the first step of a divergent line away from its
    parent (it carries that line's plain-language trigger), a 'rejoin' when
    it is the step back onto existing nodes, otherwise 'continue'. The edge
    a branch competes with gets the branch's instead_of text under
    'otherwise', so both sides of every fork are stated."""
    lines = story.get('lines') or {}
    edges = {}
    for lid in line_ids(story):
        path = lines[lid].get('path') or []
        for a, b in zip(path, path[1:]):
            e = edges.setdefault((a, b), {'from': a, 'to': b, 'lines': [], 'kind': 'continue',
                                          'trigger': None, 'otherwise': []})
            e['lines'].append(lid)
    for lid in line_ids(story):
        line = lines[lid]
        dv = line.get('divergence')
        if not dv:
            continue
        path = line.get('path') or []
        at = dv.get('diverges_at')
        if at in path and path.index(at) + 1 < len(path):
            nxt = path[path.index(at) + 1]
            e = edges[(at, nxt)]
            e['kind'] = 'branch'
            e['trigger'] = {'text': dv.get('trigger'), 'kind': dv.get('trigger_kind') or 'act', 'formal': None}
            for (a, b), other in edges.items():
                if a == at and b != nxt and dv.get('instead_of') and dv['instead_of'] not in other['otherwise']:
                    if line.get('parent') in other['lines']:
                        other['otherwise'].append(dv['instead_of'])
        rejoin = line.get('rejoins_at')
        if rejoin and rejoin in path:
            i = path.index(rejoin)
            if i > 0 and (path[i - 1], rejoin) in edges and edges[(path[i - 1], rejoin)]['kind'] == 'continue':
                edges[(path[i - 1], rejoin)]['kind'] = 'rejoin'
    return list(edges.values())


def derive_grid(story):
    """Lines x framework beats. rows[line][beat] is the list of node ids on
    that line's path filling that beat, in path order."""
    order = beat_order(story)
    nodes = story.get('nodes') or {}
    rows, skipped = {}, {}
    for lid in line_ids(story):
        line = story['lines'][lid]
        row = {b: [] for b in order}
        for nid in line.get('path') or []:
            beat = (nodes.get(nid) or {}).get('beat')
            if beat in row:
                row[beat].append(nid)
        rows[lid] = row
        skipped[lid] = as_list(line.get('skipped_beats'))
    return {'beats': order, 'rows': rows, 'skipped': skipped}


def premise_turns(story):
    return [t for t in as_list((story.get('premise') or {}).get('turns')) if isinstance(t, dict)]


def turn_by_id(story, turn_id):
    for t in premise_turns(story):
        if str(t.get('id')) == str(turn_id):
            return t
    return None


def derive_hooks(story):
    """Options of a premise turn that no line has taken at the node that
    carries the turn: the cheapest places for a new line to take hold.
    A way counts as taken at a node by the line that built the node
    (node.way) and by any line that diverges there (divergence.way)."""
    nodes = story.get('nodes') or {}
    taken = {}
    for nid, node in nodes.items():
        if node.get('turn') is not None and node.get('way'):
            taken.setdefault(nid, set()).add(int(node['way']))
    for lid in line_ids(story):
        dv = story['lines'][lid].get('divergence') or {}
        if dv.get('diverges_at') and dv.get('way'):
            taken.setdefault(dv['diverges_at'], set()).add(int(dv['way']))
    hooks = []
    for nid in story.get('node_order') or list(nodes):
        node = nodes[nid]
        if node.get('turn') is None or node.get('is_ending'):
            continue
        turn = turn_by_id(story, node['turn'])
        if not turn:
            continue
        for i, way in enumerate(as_list(turn.get('ways_through')), 1):
            if i in taken.get(nid, set()) or not isinstance(way, dict):
                continue
            hooks.append({'node': nid, 'turn': node['turn'], 'way': i,
                          'what': way.get('way'), 'cost': way.get('cost')})
    return hooks


def derive_usage(story):
    """character id / location id -> node ids that use it, in node order."""
    chars = {cid: [] for cid in (story.get('characters') or {})}
    locs = {lid: [] for lid in (story.get('locations') or {})}
    nodes = story.get('nodes') or {}
    for nid in story.get('node_order') or list(nodes):
        node = nodes[nid]
        for cid in as_list(node.get('who')):
            chars.setdefault(cid, []).append(nid)
        for lid in as_list(node.get('where')):
            locs.setdefault(lid, []).append(nid)
    return {'characters': chars, 'locations': locs}


# ---------------------------------------------------------------- checks

def _finding(kind, issue, lines=(), nodes=()):
    return {'kind': kind, 'issue': issue, 'lines': list(lines), 'nodes': list(nodes)}


def path_turns(story, path):
    nodes = story.get('nodes') or {}
    return [(nid, nodes[nid]['turn']) for nid in path if nid in nodes and nodes[nid].get('turn') is not None]


def check_story(story):
    findings, notes = [], []
    nodes = story.get('nodes') or {}
    lines = story.get('lines') or {}
    chars = story.get('characters') or {}
    locs = story.get('locations') or {}
    order = beat_order(story)
    required = [b['id'] for b in as_list((story.get('framework') or {}).get('beats')) if b.get('required', True)]
    turn_ids = [t.get('id') for t in premise_turns(story)]
    ids = line_ids(story)
    shape = story.get('shape') or {}

    if not ids:
        findings.append(_finding('no_lines', 'the story has no lines'))
        return {'findings': findings, 'notes': notes}

    main = lines[ids[0]]
    start = (main.get('path') or [None])[0]

    # --- every line is a path through existing nodes from the start to an ending
    on_some_path = set()
    for lid in ids:
        line = lines[lid]
        path = line.get('path') or []
        if not path:
            findings.append(_finding('empty_path', f'line {lid} has no path', [lid]))
            continue
        missing = [n for n in path if n not in nodes]
        if missing:
            findings.append(_finding('unknown_node', f'line {lid} path names nodes that do not exist: {missing}', [lid], missing))
            continue
        on_some_path.update(path)
        if path[0] != start:
            findings.append(_finding('wrong_start', f'line {lid} starts at {path[0]}, not at the story start {start}', [lid], [path[0]]))
        if len(set(path)) != len(path):
            findings.append(_finding('repeated_node', f'line {lid} visits a node twice', [lid]))
        last = path[-1]
        if not nodes[last].get('is_ending'):
            findings.append(_finding('no_ending', f'line {lid} ends at {last}, which is not an ending node', [lid], [last]))
        if (line.get('ending') or {}).get('node') != last:
            findings.append(_finding('ending_mismatch', f"line {lid} names ending node {(line.get('ending') or {}).get('node')} "
                                     f'but its path ends at {last}', [lid], [last]))
        for nid in path[:-1]:
            if nodes[nid].get('is_ending'):
                findings.append(_finding('ending_mid_path', f'line {lid} passes through ending node {nid}', [lid], [nid]))

        # beats in framework order, required beats covered or skipped with a reason
        idx = [order.index(nodes[n]['beat']) if nodes[n].get('beat') in order else -1 for n in path]
        if -1 in idx:
            bad = [n for n, i in zip(path, idx) if i == -1]
            findings.append(_finding('unknown_beat', f'line {lid}: nodes {bad} carry a beat the framework does not have', [lid], bad))
        elif any(b < a for a, b in zip(idx, idx[1:])):
            findings.append(_finding('beats_out_of_order', f'line {lid}: beats do not follow the framework order along its path', [lid]))
        covered = {nodes[n].get('beat') for n in path}
        skipped = {s.get('beat'): s.get('reason') for s in as_list(line.get('skipped_beats')) if isinstance(s, dict)}
        for beat in required:
            if beat not in covered and not skipped.get(beat):
                findings.append(_finding('beat_uncovered', f'line {lid}: required beat {beat} has no node and no stated reason for skipping it', [lid]))
        for beat in order:
            count = sum(1 for n in path if nodes[n].get('beat') == beat)
            if count > 2:
                notes.append(_finding('crowded_beat', f'line {lid}: {count} nodes share beat {beat}', [lid]))

        # premise turns: never twice, in order; the main line places them all
        placed = [t for _, t in path_turns(story, path)]
        if len(set(placed)) != len(placed):
            findings.append(_finding('turn_twice', f'line {lid} plays a premise turn more than once: {placed}', [lid]))
        positions = [turn_ids.index(t) if t in turn_ids else -1 for t in placed]
        if -1 in positions:
            findings.append(_finding('unknown_turn', f'line {lid} references a turn the premise does not have: {placed}', [lid]))
        elif any(b < a for a, b in zip(positions, positions[1:])):
            findings.append(_finding('turns_out_of_order', f'line {lid} plays the premise turns out of order: {placed}', [lid]))
        unplaced = [t for t in turn_ids if t not in placed]
        if unplaced:
            if lid == ids[0]:
                findings.append(_finding('turn_unplaced', f'the main line never plays premise turn(s) {unplaced}', [lid]))
            else:
                notes.append(_finding('turn_unplaced', f'line {lid} ends without playing premise turn(s) {unplaced}', [lid]))

        # the divergence and the rejoin point
        dv = line.get('divergence')
        if lid != ids[0]:
            if not dv or dv.get('diverges_at') not in path:
                findings.append(_finding('no_divergence', f'line {lid} does not say where it leaves the existing story', [lid]))
            else:
                if not str(dv.get('trigger') or '').strip():
                    findings.append(_finding('no_trigger', f"line {lid} branches at {dv['diverges_at']} with no trigger", [lid], [dv['diverges_at']]))
                elif MENU_TRIGGER_RE.search(str(dv.get('trigger'))):
                    notes.append(_finding('menu_trigger', f"line {lid}: the trigger \"{dv.get('trigger')}\" is phrased as a pick; "
                                          f'a trigger names what the player did in the world', [lid], [dv['diverges_at']]))
                parent = lines.get(line.get('parent') or '')
                if not parent or dv['diverges_at'] not in (parent.get('path') or []):
                    findings.append(_finding('unreachable_branch', f"line {lid} branches at {dv['diverges_at']}, which is not on its parent line", [lid], [dv['diverges_at']]))
        if line.get('rejoins_at') and line['rejoins_at'] not in path:
            findings.append(_finding('bad_rejoin', f"line {lid} says it rejoins at {line['rejoins_at']}, which is not on its path", [lid]))

        lo, hi = shape.get('nodes_min'), shape.get('nodes_max')
        if lo and hi and not (lo <= len(path) <= hi):
            notes.append(_finding('line_length', f'line {lid} has {len(path)} nodes; the advisory range is {lo}-{hi}', [lid]))

        # the opposition should be seen, not only mentioned
        opp = {cid for cid, c in chars.items() if c.get('opposition') and c.get('kind') != 'crowd'}
        if opp:
            seen = sum(1 for n in path if opp & set(as_list(nodes[n].get('who'))))
            if seen < 2:
                notes.append(_finding('opposition_thin', f'line {lid}: the opposition is present in {seen} node(s); it should act in at least two', [lid]))

    # --- nodes
    for nid, node in nodes.items():
        if nid not in on_some_path:
            findings.append(_finding('orphan_node', f'node {nid} is on no line', nodes=[nid]))
        if not as_list(node.get('where')):
            findings.append(_finding('no_location', f'node {nid} has no location', nodes=[nid]))
        unknown = [x for x in as_list(node.get('where')) if x not in locs]
        if unknown:
            findings.append(_finding('unknown_location', f'node {nid} uses unregistered locations {unknown}', nodes=[nid]))
        unknown = [x for x in as_list(node.get('who')) if x not in chars]
        if unknown:
            findings.append(_finding('unknown_character', f'node {nid} uses unregistered characters {unknown}', nodes=[nid]))
        present = [x for x in as_list(node.get('who')) if x in chars]
        for cid in present:
            if chars[cid].get('kind') == 'crowd':
                reps = [r for r, c in chars.items() if speaks_for(c, chars[cid])]
                if not set(reps) & set(present):
                    findings.append(_finding('crowd_without_voice', f"node {nid}: the crowd {chars[cid].get('label')} is present with nobody who speaks for it", nodes=[nid]))
        if not present and not node.get('is_ending'):
            notes.append(_finding('nobody_present', f'node {nid} has no characters besides the protagonist', nodes=[nid]))
        if node.get('turn') is not None:
            turn = turn_by_id(story, node['turn'])
            labels = {norm(chars[c].get('label')) for c in present}
            absent = [r for r in as_list((turn or {}).get('involves')) if norm(r) not in labels]
            if turn and absent:
                notes.append(_finding('turn_cast_absent', f"node {nid} plays turn {node['turn']} without {absent}, whom the turn involves", nodes=[nid]))
        if not str(node.get('summary') or '').strip():
            notes.append(_finding('unfilled_node', f'node {nid} has a plan line but no summary yet', nodes=[nid]))

    # --- graph: edges resolve, no cycles, every non-ending node leads somewhere
    edges = derive_edges(story)
    out = {}
    for e in edges:
        out.setdefault(e['from'], []).append(e['to'])
        if e['kind'] == 'branch' and not (e.get('trigger') or {}).get('text'):
            findings.append(_finding('branch_without_trigger', f"the branch {e['from']} -> {e['to']} has no trigger", nodes=[e['from'], e['to']]))
    for nid, node in nodes.items():
        if not node.get('is_ending') and nid in on_some_path and not out.get(nid):
            findings.append(_finding('dead_end', f'node {nid} is not an ending and leads nowhere', nodes=[nid]))
        if node.get('is_ending') and out.get(nid):
            findings.append(_finding('ending_with_exit', f'ending node {nid} leads on to {out[nid]}', nodes=[nid]))
    state = {}

    def cyclic(n):
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        for m in out.get(n, []):
            if cyclic(m):
                return True
        state[n] = 2
        return False

    if any(cyclic(n) for n in list(nodes)):
        findings.append(_finding('cycle', 'the graph has a cycle'))
    if start and start in nodes:
        seen, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(out.get(n, []))
        unreachable = [n for n in nodes if n not in seen]
        if unreachable:
            findings.append(_finding('unreachable_node', f'nodes {unreachable} cannot be reached from the start', nodes=unreachable))

    # --- registers
    for cid, c in chars.items():
        if c.get('kind') == 'crowd':
            reps = [r for r, o in chars.items() if speaks_for(o, c)]
            if not reps:
                findings.append(_finding('crowd_without_representative', f"the crowd {c.get('label')} has no individual who speaks for it"))
    cast_issues = validate_cast(story.get('premise', {}).get('cast_seeds', []) or list(chars.values()), premise_turns(story))
    for issue in cast_issues:
        kind = 'non_agent_cast_entity' if 'consumable tool or object' in issue else 'unrepresented_dilemma_pole'
        notes.append(_finding(kind, issue))
    usage = derive_usage(story)
    unused_c = [chars[c].get('label') for c, used in usage['characters'].items() if not used and c in chars and chars[c].get('kind') != 'crowd']
    unused_l = [locs[l].get('name') for l, used in usage['locations'].items() if not used and l in locs]
    if unused_c:
        notes.append(_finding('unused_characters', f'registered characters no node uses: {unused_c}'))
    if unused_l:
        notes.append(_finding('unused_locations', f'registered locations no node uses: {unused_l}'))
    undescribed = [locs[l].get('name') for l in locs if not str(locs[l].get('why') or '').strip()]
    if undescribed:
        notes.append(_finding('undescribed_locations', f'locations used by a node but never described: {undescribed}'))
    late = late_forks(lines)
    if late:
        notes.append(_finding('late_forks', late))
    for a, b in repeated_nodes(nodes):
        notes.append(_finding('repeated_node', f'nodes {a} and {b} play the same turn the same way in the same beat '
                                               f'on different lines; the second retells the first', nodes=[a, b]))
    for a, b in repeated_situations(story):
        notes.append(_finding('repeated_situation', f'nodes {a} and {b} play the same turn in the same beat on different '
                                                    f'lines and their summaries share most of their words; the situation '
                                                    f'should differ, not only the way', nodes=[a, b]))
    for a, b, world in same_worlds(lines, [c for c in chars.values() if c.get('kind') != 'crowd']):
        notes.append(_finding('same_world', f'lines {a} and {b} end in the same world ({world}): the same answer with the '
                                            f'same people standing and lost', lines=[a, b]))
    static = static_companions(story)
    if static:
        notes.append(_finding('companions_static', static))

    return {'findings': findings, 'notes': notes}


def people_only(values, cast):
    """The entries of an ending's standing/lost list that are people in the
    cast (by role label, name, or a label's words in order). The model also
    lists things there ("the hedge-witch's home-tending"), and a thing in one
    list made two same-world endings look different on kernel31."""
    out = set()
    for v in as_list(values):
        n = norm(v)
        for c in cast:
            label, name = norm(c.get('label')), norm(c.get('name'))
            words = iter(n.split())
            if n and (n == label or (name and (n == name or n == name.split()[0]))
                      or (label and all(w in words for w in label.split()))
                      or (label and all(w in iter(label.split()) for w in n.split()))):
                out.add(label)
                break
    return frozenset(out)


def world_key(ending, cast=None):
    """(answer, people standing, people lost). Without a cast every entry
    counts, as before."""
    ending = ending or {}
    if cast:
        return (ending.get('answer'), people_only(ending.get('standing'), cast), people_only(ending.get('lost'), cast))
    return (ending.get('answer'), frozenset(norm(x) for x in as_list(ending.get('standing'))),
            frozenset(norm(x) for x in as_list(ending.get('lost'))))


def same_worlds(lines, cast=None):
    """Pairs of lines whose endings leave the same world, with the world."""
    seen, out = {}, []
    for lid in list(lines):
        e = lines[lid].get('ending') or {}
        if not e.get('answer'):
            continue
        key = world_key(e, cast)
        if key in seen:
            desc = f"answer {key[0]}" + (f", standing {', '.join(sorted(key[1]))}" if key[1] else '') + (f", lost {', '.join(sorted(key[2]))}" if key[2] else '')
            out.append((seen[key], lid, desc))
        else:
            seen[key] = lid
    return out


def static_companions(story):
    """A note when the cast has companions with breaking points, three or
    more lines are built, and no companion's standing differs between
    endings: the 'who is still with you' the Kernel asked for never
    moved. Returns the note text, or None."""
    lines = story.get('lines') or {}
    seeds = [s for s in as_list((story.get('premise') or {}).get('cast_seeds')) if isinstance(s, dict) and s.get('breaking_point')]
    if len(lines) < 3 or not seeds:
        return None
    varies = {}
    for l in lines.values():
        e = l.get('ending') or {}
        if not e.get('answer'):
            return None
        for x in as_list(e.get('standing')):
            varies.setdefault(norm(x), set()).add('standing')
        for x in as_list(e.get('lost')):
            varies.setdefault(norm(x), set()).add('lost')
    if any(len(v) > 1 for v in varies.values()):
        return None
    names = ', '.join(str(s.get('role')) for s in seeds)
    return (f'{len(lines)} lines and no companion whose standing differs between endings; the cast has breaking points '
            f'({names}) that no line crossed')


def repeated_situations(story, threshold=0.35):
    """Pairs of nodes on different lines that fill the same beat with the
    same turn (by any way) and whose summaries share most of their
    distinctive four-word phrases: the same situation told twice with the
    way changed."""
    import example_guard
    nodes = story.get('nodes') or {}
    by_key = {}
    for nid, n in nodes.items():
        if n.get('turn') is None or not str(n.get('summary') or '').strip():
            continue
        by_key.setdefault((n.get('beat'), n.get('turn')), []).append(nid)
    out = []
    for ids in by_key.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = nodes[ids[i]], nodes[ids[j]]
                if set(as_list(a.get('lines'))) & set(as_list(b.get('lines'))):
                    continue
                pa, pb = example_guard.ngrams(a.get('summary') or ''), example_guard.ngrams(b.get('summary') or '')
                if pa and pb and len(pa & pb) / len(pa | pb) >= threshold:
                    out.append((ids[i], ids[j]))
    return out


def repeated_nodes(nodes):
    """Pairs of nodes on different lines that fill the same beat with the
    same premise turn taken the same way: the later line retells what an
    earlier one already built (it left a node too early)."""
    seen, out = {}, []
    for nid, n in nodes.items():
        if n.get('turn') is None or not n.get('way'):
            continue
        key = (n.get('beat'), n.get('turn'), n.get('way'))
        if key in seen and not set(as_list(n.get('lines'))) & set(as_list(nodes[seen[key]].get('lines'))):
            out.append((seen[key], nid))
        seen.setdefault(key, nid)
    return out


def late_forks(lines):
    """A story whose lines all leave the main line in its second half is
    one road with a choice of endings. Returns the note text, or None."""
    main = next((l for l in lines.values() if not l.get('divergence')), None)
    path = as_list((main or {}).get('path'))
    forks = [(l.get('divergence') or {}).get('diverges_at') for l in lines.values() if l.get('divergence')]
    forks = [f for f in forks if f in path]
    if len(path) < 5 or len(forks) < 2:
        return None
    if all(path.index(f) + 1 > len(path) / 2 for f in forks):
        return (f'every divergent line leaves the main line in its second half (at {", ".join(sorted(set(forks)))}, '
                f'of {len(path)} nodes): one road with a choice of endings')
    return None


DEATH_WORDS = re.compile(r'\b(dies|died|killed|perished|succumbed|dead|death)\b', re.I)
SURVIVAL_WORDS = re.compile(r'\b(survives|survived|alive|steps back|remains|still standing|keeps breathing|watches|stands|flees|leaves|steps away)\b', re.I)


def resolution_liveness_contradiction(summary_text, resolution_text, char_label=None, char_name=None):
    """Checks if an ending summary describes a character's physical state (alive or dead)
    and a resolution variant directly contradicts it. Returns an error string or None."""
    if not summary_text or not resolution_text:
        return None

    name_patterns = []
    if char_label:
        name_patterns.append(re.escape(str(char_label)))
        m = re.match(r'\{([A-Za-z0-9_]+)\}', str(char_label))
        if m:
            name_patterns.append(re.escape(m.group(1)))
    if char_name:
        name_patterns.append(re.escape(str(char_name)))
        first = str(char_name).split()[0]
        if len(first) > 2:
            name_patterns.append(re.escape(first))

    char_re = re.compile(r'\b(' + '|'.join(name_patterns) + r')\b', re.I) if name_patterns else None

    sentences = [s.strip() for s in re.split(r'[.!?]+', summary_text) if s.strip()]
    if char_re:
        relevant = [s for s in sentences if char_re.search(s)]
    else:
        relevant = sentences

    char_summary = ' '.join(relevant)
    if not char_summary:
        return None

    summary_says_dead = bool(DEATH_WORDS.search(char_summary))
    summary_says_alive = bool(SURVIVAL_WORDS.search(char_summary)) and not DEATH_WORDS.search(char_summary)

    res_says_dead = bool(DEATH_WORDS.search(resolution_text))
    res_says_alive = bool(SURVIVAL_WORDS.search(resolution_text)) and not DEATH_WORDS.search(resolution_text)

    if summary_says_alive and res_says_dead:
        return f'summary describes character alive ({char_summary!r}), but resolution says they died ({resolution_text!r})'
    if summary_says_dead and res_says_alive:
        return f'summary describes character dead ({char_summary!r}), but resolution says they survived ({resolution_text!r})'
    return None


DISENBODIED_EMBODIMENTS = {'distributed_network', 'ship_ai', 'sessile_entity', 'swarm', 'systemic_entity'}

SOMATIC_DRIFT_PATTERNS = [
    re.compile(r"\byou\s+(?:step|steps|walk|walks|climb|climbs|run|runs|crawl|crawls|stride|strides|pace|paces|stumble|stumbles|trudge|trudges|creep|creeps|tiptoe|tiptoes)\b", re.I),
    re.compile(r"\b(?:step|walk|climb|run|crawl)\s+(?:down|up|into|out|across|through|over|away)\b", re.I),
    re.compile(r"\b(?:on\s+)?your\s+(?:feet|footing|heels|toes|legs|knees)\b", re.I),
    re.compile(r"\b(?:in\s+)?your\s+(?:hands?|palms?|fingers?|fingertips?|arms?|shoulders?|chest|throat|neck|stomach|belly|spine|blood|veins|sweat|breath|lungs|ribs|flesh)\b", re.I),
    re.compile(r"\b(?:in|into)\s+your\s+pockets?\b", re.I),
    re.compile(r"\b(?:catch(?:ing)?|hold(?:ing)?|under)\s+your\s+breath\b", re.I),
    re.compile(r"\b(?:pen\s+touches\s+(?:the|your)|sign(?:ing)?\s+your\s+name|you\s+sign\b)", re.I),
]


def check_somatic_drift(text, embodiment):
    """Flags forbidden human somatic markers in second-person text when the protagonist
    is non-human, disembodied, or a distributed intelligence. Returns finding string or None."""
    if not text or not embodiment:
        return None
    emb = str(embodiment).lower()
    if emb not in DISENBODIED_EMBODIMENTS:
        return None
    for pattern in SOMATIC_DRIFT_PATTERNS:
        m = pattern.search(text)
        if m:
            return f"somatic drift for {emb} protagonist: {m.group(0)!r} (use telemetry, sensor, or network mechanics instead)"
    return None


EPILOGUE_FORMULA_PATTERN = re.compile(
    r",\s+(?:that|this|his|her|their|[A-Za-z_]+['’]s)\s+[a-z]+\s+(?:broken|shaken|thinned|abandoned|chose|chosen|shattered|lost|severed|frayed|hollowed|spent|ended|withdrawn|ruined|surrendered)\b",
    re.I
)


def epilogue_formulaic_clause(text):
    """Detects formulaic participial heads in ending resolutions (e.g. ', that trust broken',
    ', his faith thinned'). Returns the matched clause snippet or None."""
    if not text:
        return None
    m = EPILOGUE_FORMULA_PATTERN.search(str(text))
    if m:
        return m.group(0).strip(', ')
    return None


def check_epilogue_syntactic_repetition(texts):
    """Checks a collection of ending character resolution texts for formulaic pattern collapse.
    Returns finding string if 2 or more resolutions exhibit the formulaic participial head, else None."""
    hits = []
    for t in texts or []:
        clause = epilogue_formulaic_clause(t)
        if clause:
            hits.append(clause)
    if len(hits) >= 2:
        return f"repetitive formulaic epilogue syntax ({len(hits)} occurrences: {', '.join(hits[:3])}); vary sentence structures"
    return None


