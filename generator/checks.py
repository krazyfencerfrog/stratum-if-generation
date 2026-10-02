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


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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

    return {'findings': findings, 'notes': notes}
