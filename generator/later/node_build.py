# =====================================================================
# LATER-STAGE MATERIAL (stage D: the per-node room build). NOT RUN.
# =====================================================================
# This is generator/step4.py as it stood on 2026-09-29, moved here whole
# when the outline loop (generator/outline.py) replaced it. Nothing
# imports it. It is kept because it is good work done at the wrong time:
# when stage D is built (docs/later_stages.md, section D) these are the
# parts to lift, in this order:
#
#   normalize_writes()            tolerant parser for requires / sets / when
#   Step4Builder.node_validator   shape check for one built node
#   Step4Builder.node_packet,     the per-node input packet (to be rebuilt
#     previous_context,           from <id>_story.json: the node's summary
#     next_context                and expansion, its locations' rooms, its
#                                 characters' packets, its outgoing triggers)
#   rebuild_state_registry,       the state registry, recomputed from every
#     register_state,             built node so a repaired node's variables
#     touch_variable, writes_of   do not linger
#   mechanical_checks()           exit reachability, reads before writes,
#                                 outline/build mismatches, menu interactions
#   repair_nodes, collect_findings  node rebuild from a finding list
#   story_markdown()              rendering of built nodes
#
# What does NOT carry over: main_line / divergence / apply_divergence and
# the review loop (the outline loop owns lines now), and the outline's
# `exits` with leads_to (edges and plain-language triggers live in the
# story document; stage D turns each trigger into a `when` condition and
# writes it to edge.trigger.formal).
#
# Prompts that go with this file: prompts/later/sD_node_build.prompt and
# prompts/later/sD_review.prompt. The stub handlers that answered them are
# in generator/later/stub_handlers_2026_09_29.py (p_s4b, p_s4d).
# =====================================================================
"""Step 4: the story-line build-out for a room-based engine.

The unit of story is a NODE: a section of play in a subset of the world's
rooms, with a goal, the cast present, and EXITS (states of play the player
brings about, each leading to another node). A THROUGH-LINE is one
complete story: a motivation, a strategy, a sequence of nodes, an ending.

  iteration 1:  4a main line   -> through-line T1 and its nodes
  iteration n:  4c divergence  -> a different motivation/strategy for the
                                  protagonist, where it takes hold in the
                                  existing story, the new nodes, its ending
  every iteration:
                4b node build  for each new node in play order, and a
                               revision of any existing node the
                               divergence changed or rejoined
                computed checks (exit reachability, reads before writes,
                               outline/build mismatches, menu interactions)
                4d review      judgment checks + termination (next seed)
                node repair    rebuild the nodes the findings name
                4d re-review   once, so termination is judged on the
                               repaired story

Everything the model produces goes through StoryGenerator.run_prompt with a
unique prefix per call (s4a_i1, s4c_i2, s4b_i2_p2_n01, s4d_i2_r1, ...), so
a rerun replays this driver, finds every file, and rebuilds the same state
without a model call. The assembled story is written to <id>_s4_story.json
and <id>_s4_story.md after every iteration.
"""

import re
import json

from brief import brief_lite, shape_targets


def slug(text):
    s = re.sub(r'[^a-z0-9]+', '_', (text or '').strip().lower()).strip('_')
    return s or 'x'


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_writes(writes):
    """[{"variable","value"}], tolerating "var = value" strings and dicts
    with drifted key names."""
    out = []
    for item in as_list(writes):
        if isinstance(item, dict):
            var = item.get('variable') or item.get('var') or item.get('name') or item.get('key')
            if var:
                val = item.get('value')
                out.append({'variable': str(var).strip(),
                            'value': '' if val is None else str(val)})
        elif isinstance(item, str) and item.strip() and item.strip().lower() != 'none':
            m = re.match(r'\s*([^=:]+?)\s*(?:==|=|:|\bis\b)\s*(.+)$', item)
            if m:
                out.append({'variable': m.group(1).strip(), 'value': m.group(2).strip()})
            else:
                out.append({'variable': item.strip(), 'value': 'true'})
    return out


MENU_RE = re.compile(r'\b(choose|decide|select|pick)\b', re.IGNORECASE)


class Step4Builder:

    def __init__(self, gen, max_iterations=4, max_repair_nodes=4):
        self.gen = gen
        self.max_iterations = max_iterations
        self.max_repair_nodes = max_repair_nodes

        self.lines = {}          # line id -> dict
        self.nodes = {}          # node id -> {'outline','content','line_ids','iteration','revisions'}
        self.node_order = []
        self.state_variables = {}
        self.iterations = []
        self.stop_reason = None
        self.warnings = []

    # ------------------------------------------------------------------ upstream

    def upstream(self):
        g = self.gen
        brief = g.analysis.get('s3_brief') or {}
        return {
            'kernel': g.kernel,
            'brief': brief,
            'brief_lite': brief_lite(brief),
            'premise': g.analysis.get('s3_5_premise_expansion') or {},
            'cast': g.analysis.get('s3_6_cast') or {},
            'world': g.analysis.get('s3_7_world') or {},
            'craft': g.analysis.get('s3_75_craft_spine') or {},
            'shape': shape_targets(g.shape),
        }

    def budget(self):
        premise = self.gen.analysis.get('s3_5_premise_expansion') or {}
        return str((premise.get('enrichment_budget') or {}).get('level', 'moderate'))

    def turn(self, ref):
        premise = self.gen.analysis.get('s3_5_premise_expansion') or {}
        turns = premise.get('turns') or []
        if ref is None or ref == '':
            return None
        for t in turns:
            if isinstance(t, dict) and str(t.get('id')) == str(ref):
                return t
        try:
            index = int(ref)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(turns):
            return turns[index]
        return None

    def cast_compact(self):
        cast = self.upstream()['cast']
        return {
            'protagonist_name': cast.get('protagonist_name'),
            'characters': [{'name': c.get('name'), 'role': c.get('role'), 'wants': c.get('wants'),
                            'holds': c.get('holds'), 'speaks_for': c.get('speaks_for')}
                           for c in as_list(cast.get('characters')) if isinstance(c, dict)],
            'crowds': [{'name': c.get('name'), 'representatives': c.get('representatives')}
                       for c in as_list(cast.get('crowds')) if isinstance(c, dict)],
        }

    def world_compact(self):
        world = self.upstream()['world']
        return {
            'protagonist_presence': world.get('protagonist_presence'),
            'rooms': [{'id': r.get('id'), 'name': r.get('name'), 'purpose': r.get('purpose'),
                       'usually_here': r.get('usually_here')}
                      for r in as_list(world.get('rooms')) if isinstance(r, dict)],
        }

    def room(self, room_id):
        for r in as_list(self.upstream()['world'].get('rooms')):
            if isinstance(r, dict) and r.get('id') == room_id:
                return r
        return None

    def character(self, name):
        for c in as_list(self.upstream()['cast'].get('characters')):
            if isinstance(c, dict) and c.get('name') == name:
                return c
        return None

    def room_ids(self):
        return [r.get('id') for r in as_list(self.upstream()['world'].get('rooms')) if isinstance(r, dict)]

    def character_names(self):
        return [c.get('name') for c in as_list(self.upstream()['cast'].get('characters')) if isinstance(c, dict)]

    # ------------------------------------------------------------------ main loop

    def run(self):
        n = 1
        while n <= self.max_iterations:
            print(f'--- step 4, iteration {n}')
            if n == 1:
                outline = self.main_line()
                line = self.register_main_line(outline)
                modified, new_ids, rejoin = [], [b['id'] for b in outline['nodes']], None
            else:
                proposal = self.divergence(n)
                if proposal.get('status') != 'proposed':
                    self.stop_reason = f"4c found nothing worth building at iteration {n}: {proposal.get('why', '')}"
                    break
                line, modified, new_ids, rejoin = self.apply_divergence(n, proposal)

            for nid in modified:
                if self.nodes[nid]['content'] is not None:
                    self.rebuild_for_change(n, nid, line)
            for nid in new_ids:
                self.build_node(n, nid, line['id'])
            if rejoin and self.nodes[rejoin]['content'] is not None:
                self.rebuild_for_rejoin(n, rejoin, line)

            computed = self.mechanical_checks()
            review = self.review(n, computed, round_no=0)
            repaired = self.repair_nodes(n, review, computed)
            if repaired:
                computed = self.mechanical_checks()
                review = self.review(n, computed, round_no=1)

            self.iterations.append({
                'iteration': n,
                'line_id': line['id'],
                'new_node_ids': new_ids,
                'modified_node_ids': modified,
                'repaired_node_ids': repaired,
                'termination': review.get('termination', {}),
            })
            self.save_story()

            termination = review.get('termination') or {}
            recommendation = str(termination.get('recommendation', '')).lower()
            if 'stop' in recommendation:
                self.stop_reason = f"4d recommended stopping after iteration {n}: {termination.get('reasoning', '')}"
                break
            n += 1
        else:
            self.stop_reason = f'reached --max-iterations ({self.max_iterations})'

        if not self.stop_reason:
            self.stop_reason = 'loop ended'
        self.save_story()
        print(f'--- step 4 done: {self.stop_reason}')
        return self.story_json()

    # ------------------------------------------------------------------ 4a

    def normalize_node_entry(self, entry, known_rooms, known_chars):
        entry = dict(entry)
        rooms = [r for r in as_list(entry.get('rooms')) if isinstance(r, str)]
        unknown = [r for r in rooms if r not in known_rooms]
        if unknown:
            self.warnings.append(f"node {entry.get('id')}: unknown room ids {unknown} dropped")
        entry['rooms'] = [r for r in rooms if r in known_rooms]
        chars = [c for c in as_list(entry.get('characters')) if isinstance(c, str)]
        unknown = [c for c in chars if c not in known_chars]
        if unknown:
            self.warnings.append(f"node {entry.get('id')}: unknown characters {unknown} dropped")
        entry['characters'] = [c for c in chars if c in known_chars]
        exits = []
        for i, ex in enumerate(as_list(entry.get('exits'))):
            if not isinstance(ex, dict):
                continue
            ex = dict(ex)
            ex.setdefault('id', f"{entry.get('id')}.{chr(ord('a') + i)}")
            ex.setdefault('leads_to', None)
            exits.append(ex)
        entry['exits'] = exits
        entry.setdefault('turn_ref', None)
        entry.setdefault('failure_exit', None)
        return entry

    def outline_validator(self, key, existing_ids=()):
        def validate(parsed):
            nodes = parsed.get(key)
            if not isinstance(nodes, list):
                raise ValueError(f'{key} must be a list')
            seen = set()
            for b in nodes:
                if not isinstance(b, dict):
                    raise ValueError('node entries must be objects')
                for k in ('id', 'title', 'goal'):
                    if not b.get(k):
                        raise ValueError(f'node entry missing {k}')
                if b['id'] in seen or b['id'] in existing_ids:
                    raise ValueError(f'node id {b["id"]} is not fresh')
                seen.add(b['id'])
                if not isinstance(b.get('exits', []), list):
                    raise ValueError(f'node {b["id"]}: exits must be a list')
                for ex in b.get('exits') or []:
                    if isinstance(ex, dict) and ex.get('leads_to') and ex['leads_to'] not in seen | set(existing_ids) \
                            and ex['leads_to'] not in {x.get('id') for x in nodes if isinstance(x, dict)}:
                        raise ValueError(f'node {b["id"]}: exit leads_to unknown node {ex["leads_to"]}')
        return validate

    def main_line(self):
        u = self.upstream()
        shape = u['shape']
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$BRIEF_LITE_JSON$$': self.gen.to_json(u['brief_lite']),
            '$$PREMISE_EXPANSION_JSON$$': self.gen.to_json(self.premise_for_outline()),
            '$$CAST_COMPACT_JSON$$': self.gen.to_json(self.cast_compact()),
            '$$WORLD_COMPACT_JSON$$': self.gen.to_json(self.world_compact()),
            '$$CRAFT_SPINE_JSON$$': self.gen.to_json(self.craft_compact()),
            '$$SHAPE_JSON$$': self.gen.to_json(shape),
            '$$NODES_MIN$$': str(shape['nodes_min']),
            '$$NODES_MAX$$': str(shape['nodes_max']),
        }

        def validate(parsed):
            if not isinstance(parsed.get('through_line'), dict) or not parsed['through_line'].get('id'):
                raise ValueError('through_line with an id is required')
            self.outline_validator('nodes')(parsed)
            if not parsed['nodes']:
                raise ValueError('nodes must be non-empty')
            if not isinstance(parsed.get('ending'), dict):
                raise ValueError('ending object is required')

        return self.gen.run_prompt('s4a_i1', 'main_line', repl,
                                   prompt_file='s4a_main_line.prompt', validator=validate)

    def premise_for_outline(self):
        p = self.upstream()['premise']
        return {k: p.get(k) for k in ('protagonist', 'pressure', 'opposition', 'mediation', 'turns', 'complications')}

    def craft_compact(self):
        c = self.upstream()['craft']
        wn = c.get('want_need_tension') or {}
        return {
            'want_need_tension': {'want': (wn.get('want') or {}).get('restated') if isinstance(wn.get('want'), dict) else wn.get('want'),
                                  'need': (wn.get('need') or {}).get('description') if isinstance(wn.get('need'), dict) else wn.get('need'),
                                  'tension': wn.get('tension'), 'enacts_via': wn.get('enacts_via')},
            'irony': {'type': (c.get('irony_mode') or {}).get('type'), 'device': (c.get('irony_mode') or {}).get('device')},
            'escalation': {'pattern': (c.get('escalation_shape') or {}).get('pattern'),
                           'mechanism': (c.get('escalation_shape') or {}).get('mechanism'),
                           'transformation_note': (c.get('escalation_shape') or {}).get('transformation_note')},
            'setup_payoff': [{'setup': p.get('setup'), 'payoff': p.get('payoff')}
                             for p in as_list(c.get('setup_payoff_pairs')) if isinstance(p, dict)],
            'motif': c.get('motif'),
        }

    def register_main_line(self, outline):
        known_rooms, known_chars = self.room_ids(), self.character_names()
        entries = [self.normalize_node_entry(e, known_rooms, known_chars) for e in outline['nodes']]
        entries[-1]['exits'] = []
        for e in entries:
            self.nodes[e['id']] = {'outline': e, 'content': None, 'line_ids': ['T1'], 'iteration': 1, 'revisions': []}
            self.node_order.append(e['id'])
        tl = dict(outline['through_line'])
        tl['id'] = 'T1'
        ending = dict(outline.get('ending') or {})
        ending.setdefault('node', entries[-1]['id'])
        line = {'id': 'T1', 'iteration': 1, 'through_line': tl, 'ending': ending,
                'path': [e['id'] for e in entries], 'divergence': None, 'rejoins_at': None}
        self.lines['T1'] = line
        return line

    # ------------------------------------------------------------------ 4c

    def divergence(self, n):
        u = self.upstream()
        digest = self.digest()
        last_review = self.iterations[-1]['termination'] if self.iterations else {}
        shape = dict(u['shape'])
        shape['through_lines_built'] = len(self.lines)
        shape['iteration'] = n
        existing = set(self.nodes)
        open_exits = {(o['node'], o['exit_id']) for o in digest['open_exits']}

        def validate(parsed):
            status = parsed.get('status')
            if status not in ('proposed', 'nothing_worth_building'):
                raise ValueError('status must be proposed or nothing_worth_building')
            if status != 'proposed':
                return
            tl = parsed.get('through_line') or {}
            if not tl.get('id') or tl['id'] in self.lines:
                raise ValueError('through_line needs a fresh id')
            dv = parsed.get('divergence') or {}
            if dv.get('node') not in self.nodes:
                raise ValueError(f'divergence.node {dv.get("node")} is not an existing node')
            kind = dv.get('kind')
            if kind not in ('existing_exit', 'new_opportunity', 'state_variant'):
                raise ValueError('divergence.kind must be existing_exit, new_opportunity or state_variant')
            if kind == 'existing_exit' and (dv['node'], dv.get('exit_id')) not in open_exits:
                raise ValueError(f'existing_exit must name an open exit; open exits are {sorted(open_exits)}')
            self.outline_validator('new_nodes', existing_ids=existing)(parsed)
            if kind == 'state_variant' and parsed.get('new_nodes'):
                raise ValueError('state_variant adds no new nodes')
            if kind != 'state_variant' and not parsed.get('new_nodes') and not parsed.get('rejoins_at'):
                raise ValueError('a new line needs new nodes or a rejoin')
            rec = parsed.get('rejoins_at')
            if rec and rec not in self.nodes:
                raise ValueError(f'rejoins_at names unknown node {rec}')
            for m in as_list(parsed.get('modify_nodes')):
                if isinstance(m, dict) and m.get('id') not in self.nodes:
                    raise ValueError(f'modify_nodes names unknown node {m.get("id")}')

        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$BRIEF_LITE_JSON$$': self.gen.to_json(u['brief_lite']),
            '$$PREMISE_EXPANSION_JSON$$': self.gen.to_json(self.premise_for_outline()),
            '$$CAST_COMPACT_JSON$$': self.gen.to_json(self.cast_compact()),
            '$$WORLD_COMPACT_JSON$$': self.gen.to_json(self.world_compact()),
            '$$CRAFT_SPINE_JSON$$': self.gen.to_json(self.craft_compact()),
            '$$STORY_DIGEST_JSON$$': self.gen.to_json(digest),
            '$$PRIOR_REVIEW_JSON$$': self.gen.to_json(last_review),
            '$$SHAPE_JSON$$': self.gen.to_json(shape),
            '$$ITERATION$$': str(n),
        }
        return self.gen.run_prompt(f's4c_i{n}', 'divergence', repl,
                                   prompt_file='s4c_divergence.prompt', validator=validate)

    def apply_divergence(self, n, proposal):
        """Wire the proposal into the outlines: claim or add the exit at the
        divergence node, register the new nodes, build the line's path.
        Returns (line, modified_node_ids, new_node_ids, rejoin_node_id)."""
        known_rooms, known_chars = self.room_ids(), self.character_names()
        line_id = proposal['through_line']['id']
        dv = proposal['divergence']
        kind = dv['kind']
        new_entries = [self.normalize_node_entry(e, known_rooms, known_chars) for e in proposal.get('new_nodes') or []]
        rejoin = proposal.get('rejoins_at') or None
        first_new = new_entries[0]['id'] if new_entries else rejoin

        modified = []
        for m in as_list(proposal.get('modify_nodes')):
            if not isinstance(m, dict) or m.get('id') not in self.nodes:
                continue
            node = self.nodes[m['id']]
            change = {'add': m.get('add')}
            ex = m.get('add_exit')
            if isinstance(ex, dict) and ex.get('id'):
                ex = dict(ex)
                if kind != 'state_variant' and m['id'] == dv['node']:
                    ex['leads_to'] = first_new
                existing = [e for e in node['outline']['exits'] if e.get('id') == ex['id']]
                if existing:
                    existing[0].update(ex)
                else:
                    node['outline']['exits'].append(ex)
                change['add_exit'] = ex
            node.setdefault('changes', []).append({'line_id': line_id, 'iteration': n, **change})
            modified.append(m['id'])

        if kind == 'existing_exit':
            node = self.nodes[dv['node']]
            for ex in node['outline']['exits']:
                if ex.get('id') == dv.get('exit_id'):
                    ex['leads_to'] = first_new
            node.setdefault('changes', []).append({'line_id': line_id, 'iteration': n,
                                                   'claimed_exit': dv.get('exit_id'), 'leads_to': first_new})
            if dv['node'] not in modified:
                modified.append(dv['node'])
        elif kind == 'new_opportunity' and dv['node'] not in modified:
            # the model put the opportunity in divergence but forgot modify_nodes
            node = self.nodes[dv['node']]
            ex = {'id': f"{dv['node']}.{chr(ord('a') + len(node['outline']['exits']))}",
                  'summary': dv.get('opportunity') or 'the new line takes hold here', 'leads_to': first_new}
            node['outline']['exits'].append(ex)
            node.setdefault('changes', []).append({'line_id': line_id, 'iteration': n,
                                                   'add': dv.get('opportunity'), 'add_exit': ex})
            modified.append(dv['node'])

        parent = self.line_containing(dv['node'])
        prefix = parent['path'][:parent['path'].index(dv['node']) + 1]
        for nid in prefix:
            if line_id not in self.nodes[nid]['line_ids']:
                self.nodes[nid]['line_ids'].append(line_id)

        for i, e in enumerate(new_entries):
            if i == len(new_entries) - 1:
                if rejoin:
                    if not e['exits']:
                        e['exits'] = [{'id': f"{e['id']}.a", 'summary': 'the line rejoins the story', 'leads_to': rejoin}]
                    else:
                        e['exits'][0]['leads_to'] = rejoin
                else:
                    e['exits'] = []
            self.nodes[e['id']] = {'outline': e, 'content': None, 'line_ids': [line_id], 'iteration': n, 'revisions': []}
            self.node_order.append(e['id'])

        path = list(prefix) + [e['id'] for e in new_entries]
        if kind == 'state_variant':
            path = list(parent['path'])
            for nid in path:
                if line_id not in self.nodes[nid]['line_ids']:
                    self.nodes[nid]['line_ids'].append(line_id)
        elif rejoin:
            rec_line = self.line_containing(rejoin)
            tail = rec_line['path'][rec_line['path'].index(rejoin):]
            for nid in tail:
                if line_id not in self.nodes[nid]['line_ids']:
                    self.nodes[nid]['line_ids'].append(line_id)
            path.extend(tail)

        ending = dict(proposal.get('ending') or {})
        if kind == 'state_variant':
            ending.setdefault('node', parent['path'][-1])
        elif rejoin:
            ending.setdefault('node', self.line_containing(rejoin)['path'][-1])
        elif new_entries:
            ending.setdefault('node', new_entries[-1]['id'])
        tl = dict(proposal['through_line'])
        line = {'id': line_id, 'iteration': n, 'through_line': tl, 'ending': ending, 'path': path,
                'divergence': dv, 'rejoins_at': rejoin, 'why': proposal.get('why')}
        self.lines[line_id] = line
        rejoin_node = rejoin if rejoin else (ending.get('node') if kind == 'state_variant' else None)
        return line, modified, [e['id'] for e in new_entries], rejoin_node

    def line_containing(self, node_id):
        for lid in sorted(self.lines, key=lambda l: self.lines[l]['iteration']):
            if node_id in self.lines[lid]['path']:
                return self.lines[lid]
        raise ValueError(f'no line contains node {node_id}')

    # ------------------------------------------------------------------ 4b

    def node_validator(self, node_id, outline):
        expected_exits = {ex['id'] for ex in outline.get('exits') or [] if ex.get('id')}

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected an object')
            if not parsed.get('arrival'):
                raise ValueError('node needs arrival text')
            rooms = parsed.get('rooms')
            if not isinstance(rooms, list) or not rooms:
                raise ValueError('rooms must be a non-empty list')
            for r in rooms:
                if not isinstance(r, dict) or not isinstance(r.get('interactions'), list):
                    raise ValueError('each room needs an interactions list')
            exits = parsed.get('exits')
            if not isinstance(exits, list):
                raise ValueError('exits must be a list')
            got = {ex.get('id') for ex in exits if isinstance(ex, dict)}
            missing = expected_exits - got
            if missing:
                raise ValueError(f'exits missing the outline ids {sorted(missing)}')
        return validate

    def previous_context(self, node_id, line_id):
        path = self.lines[line_id]['path']
        i = path.index(node_id)
        if i == 0:
            return None
        prev_id = path[i - 1]
        prev = self.nodes[prev_id]
        exit_entry = None
        for ex in prev['outline'].get('exits') or []:
            if ex.get('leads_to') == node_id:
                exit_entry = dict(ex)
                break
        built = None
        if prev['content'] and exit_entry:
            for ex in prev['content'].get('exits') or []:
                if isinstance(ex, dict) and ex.get('id') == exit_entry.get('id'):
                    built = ex
        return {
            'node': prev_id, 'title': prev['outline'].get('title'),
            'exit': exit_entry.get('id') if exit_entry else None,
            'summary': exit_entry.get('summary') if exit_entry else None,
            'when': built.get('when') if built else None,
            'transition': built.get('transition') if built else None,
        }

    def next_context(self, outline):
        out = []
        for ex in outline.get('exits') or []:
            target = ex.get('leads_to')
            if target and target in self.nodes:
                t = self.nodes[target]['outline']
                out.append({'exit': ex.get('id'), 'node': target, 'title': t.get('title'), 'goal': t.get('goal')})
            else:
                out.append({'exit': ex.get('id'), 'node': None, 'note': 'open exit: no line follows it yet'})
        return out

    def node_packet(self, node_id, line_id):
        node = self.nodes[node_id]
        o = node['outline']
        line = self.lines[line_id]
        packet = dict(o)
        packet['line_id'] = line_id
        packet['position'] = f"{line['path'].index(node_id) + 1} of {len(line['path'])}"
        packet['previous'] = self.previous_context(node_id, line_id)
        packet['next'] = self.next_context(o)
        packet['shared_with'] = [l for l in node['line_ids'] if l != line_id]
        packet['is_ending'] = not (o.get('exits') or [])
        if packet['is_ending']:
            packet['ending'] = line.get('ending')
        if node.get('changes'):
            packet['changes'] = node['changes']
        return packet

    def build_node(self, n, node_id, line_id, revision=None, round_no=0):
        u = self.upstream()
        node = self.nodes[node_id]
        o = node['outline']
        line = self.lines[line_id]
        entities = {
            'rooms': [self.room(r) for r in o.get('rooms') or [] if self.room(r)],
            'characters': [self.character(c) for c in o.get('characters') or [] if self.character(c)],
        }
        tone = {'brief': u['brief_lite'], 'craft_spine': self.craft_compact()}
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$THROUGH_LINE_JSON$$': self.gen.to_json(line['through_line']),
            '$$NODE_OUTLINE_JSON$$': self.gen.to_json(self.node_packet(node_id, line_id)),
            '$$TURN_JSON$$': self.gen.to_json(self.turn(o.get('turn_ref'))),
            '$$MEDIATION_JSON$$': self.gen.to_json((u['premise'] or {}).get('mediation')),
            '$$NODE_ENTITIES_JSON$$': self.gen.to_json(entities),
            '$$PRESENCE_JSON$$': self.gen.to_json((u['world'] or {}).get('protagonist_presence')),
            '$$TONE_JSON$$': self.gen.to_json(tone),
            '$$STATE_VARIABLES_JSON$$': self.gen.to_json(self.state_compact()),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
            '$$REVISION_JSON$$': self.gen.to_json(revision) if revision else 'none',
        }
        prefix = f's4b_i{n}_{slug(node_id)}'
        if round_no:
            prefix += f'_r{round_no}'
        content = self.gen.run_prompt(prefix, 'node', repl, prompt_file='s4b_node_build.prompt',
                                      validator=self.node_validator(node_id, o))
        content = dict(content)
        content['id'] = node_id
        self.normalize_content(content)
        if node['content'] is not None:
            node['revisions'].append({'prefix': prefix, 'reason': revision})
        node['content'] = content
        self.rebuild_state_registry()
        return content

    def normalize_content(self, content):
        for room in as_list(content.get('rooms')):
            if not isinstance(room, dict):
                continue
            for it in as_list(room.get('interactions')):
                if isinstance(it, dict):
                    it['requires'] = normalize_writes(it.get('requires'))
                    it['sets'] = normalize_writes(it.get('sets'))
        exits = []
        for ex in as_list(content.get('exits')):
            if isinstance(ex, dict):
                ex['when'] = normalize_writes(ex.get('when'))
                exits.append(ex)
        content['exits'] = exits
        variants = content.get('ending_variants')
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, dict):
                    v['when'] = normalize_writes(v.get('when'))

    def rebuild_for_change(self, n, node_id, line):
        node = self.nodes[node_id]
        changes = [c for c in node.get('changes', []) if c.get('line_id') == line['id']]
        findings = []
        for c in changes:
            if c.get('add'):
                findings.append({'issue': f"A new story line ({line['id']}: {line['through_line'].get('title')}) takes hold in this node.",
                                 'fix': f"Add to this node: {c['add']}. Make the new exit "
                                        f"{(c.get('add_exit') or {}).get('id')} reachable through interactions, with its own cost."})
            if c.get('claimed_exit'):
                findings.append({'issue': f"Exit {c['claimed_exit']} is now followed by line {line['id']} "
                                          f"({line['through_line'].get('title')}).",
                                 'fix': 'Keep the exit reachable through interactions and make its transition lead into the new line; '
                                        f"the line's motivation: {line['through_line'].get('motivation')}"})
        if not findings:
            return None
        revision = {'prior_node': node['content'], 'findings': findings}
        origin = self.line_containing(node_id)
        return self.build_node(n, node_id, origin['id'], revision=revision, round_no=len(node['revisions']) + 1)

    def rebuild_for_rejoin(self, n, node_id, line):
        node = self.nodes[node_id]
        dv = line.get('divergence') or {}
        if dv.get('kind') == 'state_variant':
            issue = (f"Line {line['id']} ({line['through_line'].get('title')}) plays the same nodes with a different "
                     f"strategy and needs its own ending variant here, selected when {line['ending'].get('when')}.")
        else:
            issue = (f"This node is now reached by line {line['id']} ({line['through_line'].get('title')}) as well, "
                     f"arriving from {line['path'][line['path'].index(node_id) - 1] if node_id in line['path'] and line['path'].index(node_id) > 0 else 'its own nodes'}.")
        revision = {'prior_node': node['content'], 'findings': [{
            'issue': issue,
            'fix': 'Keep the node; add ending_variants (or vary the arrival and exits) by the state each arriving line '
                   f"carries. The new line's ending: {self.gen.to_json(line.get('ending'))}",
        }]}
        origin = self.line_containing(node_id)
        return self.build_node(n, node_id, origin['id'], revision=revision, round_no=len(node['revisions']) + 1)

    # ------------------------------------------------------------------ state

    def state_compact(self):
        return {k: {'kind': v.get('kind'), 'values': v.get('values')} for k, v in self.state_variables.items()}

    def rebuild_state_registry(self):
        """Recomputed from every built node after each build, so a repaired
        node's old variables do not linger in what later nodes are shown."""
        self.state_variables = {}
        for nid in self.node_order:
            if self.nodes[nid]['content']:
                self.register_state(nid, self.nodes[nid]['content'])

    def register_state(self, node_id, content):
        for room in as_list(content.get('rooms')):
            if not isinstance(room, dict):
                continue
            for it in as_list(room.get('interactions')):
                if not isinstance(it, dict):
                    continue
                for w in it.get('sets') or []:
                    self.touch_variable(w['variable'], w['value'], node_id, 'written_by')
                for r in it.get('requires') or []:
                    self.touch_variable(r['variable'], None, node_id, 'read_by')
        for ex in content.get('exits') or []:
            for r in ex.get('when') or []:
                self.touch_variable(r['variable'], None, node_id, 'read_by')
        for v in as_list(content.get('ending_variants')):
            if isinstance(v, dict):
                for r in v.get('when') or []:
                    self.touch_variable(r['variable'], None, node_id, 'read_by')

    def touch_variable(self, name, value, node_id, relation):
        var = self.state_variables.setdefault(name, {
            'kind': 'flag', 'values': [], 'declared_by': node_id, 'written_by': [], 'read_by': [],
        })
        if value not in (None, '') and str(value) not in var['values']:
            var['values'].append(str(value))
        if node_id not in var[relation]:
            var[relation].append(node_id)

    def writes_of(self, node_id):
        content = self.nodes[node_id]['content'] or {}
        out = set()
        for room in as_list(content.get('rooms')):
            if isinstance(room, dict):
                for it in as_list(room.get('interactions')):
                    if isinstance(it, dict):
                        for w in it.get('sets') or []:
                            out.add(w['variable'])
        return out

    # ------------------------------------------------------------------ computed checks

    def mechanical_checks(self):
        """Findings the pipeline can compute: an exit whose conditions no
        interaction on any path can satisfy, an interaction that requires a
        variable nothing earlier sets, outline rooms/characters missing from
        the build, an interaction that is a menu. Each names its node."""
        findings = []
        for nid in self.node_order:
            node = self.nodes[nid]
            content = node['content']
            if not content:
                continue
            o = node['outline']
            # what can be set before this node, per line through it
            available_by_line = {}
            for lid in node['line_ids']:
                path = self.lines[lid]['path']
                if nid not in path:
                    continue
                avail = set()
                for earlier in path[:path.index(nid)]:
                    avail |= self.writes_of(earlier)
                available_by_line[lid] = avail
            here = self.writes_of(nid)

            def satisfiable(conds):
                names = {c['variable'] for c in conds}
                if not names:
                    return True
                for avail in available_by_line.values() or [set()]:
                    if names <= (avail | here):
                        return True
                return False

            for ex in content.get('exits') or []:
                if not satisfiable(ex.get('when') or []):
                    findings.append({'kind': 'unreachable_exit', 'node_ids': [nid],
                                     'issue': f"exit {ex.get('id')} requires {[c['variable'] for c in ex.get('when') or []]}, "
                                              f"and no interaction in this node or earlier on its lines sets all of them",
                                     'fix': 'add the interactions that set those variables here, or change the exit condition '
                                            'to variables the node actually sets'})
            built_rooms = {r.get('room') for r in as_list(content.get('rooms')) if isinstance(r, dict)}
            missing_rooms = [r for r in o.get('rooms') or [] if r not in built_rooms]
            if missing_rooms:
                findings.append({'kind': 'missing_room', 'node_ids': [nid],
                                 'issue': f'outline rooms {missing_rooms} have no entry in the build',
                                 'fix': 'give each outline room an entry with at least two interactions'})
            built_chars = {c.get('name') for c in as_list(content.get('characters')) if isinstance(c, dict)}
            missing_chars = [c for c in o.get('characters') or [] if c not in built_chars]
            if missing_chars:
                findings.append({'kind': 'missing_character', 'node_ids': [nid],
                                 'issue': f'outline characters {missing_chars} are absent from the build',
                                 'fix': 'place each one in a room with an agenda, a talk interaction, and moved_by'})
            for room in as_list(content.get('rooms')):
                if not isinstance(room, dict):
                    continue
                for it in as_list(room.get('interactions')):
                    if not isinstance(it, dict):
                        continue
                    if MENU_RE.search(str(it.get('action', ''))) or MENU_RE.match(str(it.get('target', ''))):
                        findings.append({'kind': 'menu', 'node_ids': [nid],
                                         'issue': f"interaction '{it.get('action')}' on '{it.get('target')}' in {room.get('room')} is a menu pick",
                                         'fix': 'replace it with the acts in the world that bring the outcome about, each setting its own state'})
                    if not satisfiable(it.get('requires') or []):
                        findings.append({'kind': 'unsatisfiable_requires', 'node_ids': [nid],
                                         'issue': f"interaction '{it.get('action')}' on '{it.get('target')}' requires "
                                                  f"{[c['variable'] for c in it.get('requires') or []]}, which nothing earlier sets",
                                         'fix': 'drop the requirement or add the interaction that sets it'})
                if not [it for it in as_list(room.get('interactions')) if isinstance(it, dict)]:
                    findings.append({'kind': 'empty_room', 'node_ids': [nid],
                                     'issue': f"room {room.get('room')} has no interactions in this node",
                                     'fix': 'give it at least two interactions that serve the goal'})
        used_rooms = set()
        seen_chars = set()
        for nid in self.node_order:
            used_rooms |= set(self.nodes[nid]['outline'].get('rooms') or [])
            seen_chars |= set(self.nodes[nid]['outline'].get('characters') or [])
        notes = {
            'rooms_never_used': [r for r in self.room_ids() if r not in used_rooms],
            'characters_never_present': [c for c in self.character_names() if c not in seen_chars],
        }
        return {'findings': findings, 'notes': notes}

    # ------------------------------------------------------------------ 4d

    def review(self, n, computed, round_no=0):
        u = self.upstream()
        premise = u['premise'] or {}
        shape = dict(u['shape'])
        shape['through_lines_built'] = len(self.lines)
        it_nodes = [nid for nid in self.node_order if self.nodes[nid]['iteration'] == n]
        line = self.iterations[-1]['line_id'] if self.iterations and self.iterations[-1]['iteration'] == n else f'T{n}'
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$THIS_ITERATION_JSON$$': self.gen.to_json({
                'iteration': n, 'line_id': line, 'new_node_ids': it_nodes, 'review_round': round_no,
            }),
            '$$BRIEF_LITE_JSON$$': self.gen.to_json(u['brief_lite']),
            '$$TURNS_JSON$$': self.gen.to_json({'turns': premise.get('turns'), 'mediation': premise.get('mediation')}),
            '$$ESCALATION_JSON$$': self.gen.to_json((u['craft'] or {}).get('escalation_shape')),
            '$$STORY_DIGEST_JSON$$': self.gen.to_json(self.digest(with_interactions=True)),
            '$$CAST_AND_ROOMS_JSON$$': self.gen.to_json({'characters': self.character_names(), 'rooms': self.room_ids()}),
            '$$COMPUTED_CHECKS_JSON$$': self.gen.to_json(computed),
            '$$SHAPE_JSON$$': self.gen.to_json(shape),
        }
        prefix = f's4d_i{n}' + (f'_r{round_no}' if round_no else '')
        return self.gen.run_prompt(prefix, 'review', repl, prompt_file='s4d_review.prompt',
                                   validator=self.gen.require_keys('earned_choices', 'continuity', 'cast_and_rooms',
                                                                   'through_line_novelty', 'pacing', 'termination'))

    def collect_findings(self, review, computed):
        by_node = {}
        for f in computed.get('findings') or []:
            for nid in f.get('node_ids') or []:
                if nid in self.nodes:
                    by_node.setdefault(nid, []).append({'section': 'computed:' + f.get('kind', ''),
                                                        'issue': f.get('issue', ''), 'fix': f.get('fix', '')})
        for section in ('earned_choices', 'continuity', 'cast_and_rooms', 'through_line_novelty', 'pacing'):
            block = review.get(section) or {}
            if not isinstance(block, dict):
                continue
            for finding in as_list(block.get('findings')):
                if not isinstance(finding, dict):
                    continue
                ids = [b for b in as_list(finding.get('node_ids')) if b in self.nodes]
                for nid in ids:
                    by_node.setdefault(nid, []).append({'section': section,
                                                        'issue': finding.get('issue', ''),
                                                        'fix': finding.get('fix', '')})
        return by_node

    def repair_nodes(self, n, review, computed):
        by_node = self.collect_findings(review, computed)
        repaired = []
        for nid in [b for b in self.node_order if b in by_node][:self.max_repair_nodes]:
            node = self.nodes[nid]
            if node['content'] is None:
                continue
            line_id = self.line_containing(nid)['id']
            revision = {'prior_node': node['content'], 'findings': by_node[nid]}
            self.build_node(n, nid, line_id, revision=revision, round_no=len(node['revisions']) + 1)
            repaired.append(nid)
        skipped = [b for b in by_node if b not in repaired]
        if skipped:
            self.warnings.append(f'iteration {n}: findings on {skipped} left for the next review '
                                 f'(--max-repair-nodes={self.max_repair_nodes})')
        return repaired

    # ------------------------------------------------------------------ computed views

    def node_digest(self, nid, with_interactions=False):
        node = self.nodes[nid]
        o, c = node['outline'], node['content'] or {}
        built_exits = {ex.get('id'): ex for ex in c.get('exits') or [] if isinstance(ex, dict)}
        exits = []
        for ex in o.get('exits') or []:
            b = built_exits.get(ex.get('id')) or {}
            exits.append({'id': ex.get('id'), 'summary': ex.get('summary'), 'leads_to': ex.get('leads_to'),
                          'when': b.get('when'), 'transition': b.get('transition')})
        d = {
            'id': nid, 'title': o.get('title'), 'goal': o.get('goal'), 'turn_ref': o.get('turn_ref'),
            'rooms': o.get('rooms'), 'characters': o.get('characters'), 'pressure': o.get('pressure'),
            'on_lines': node['line_ids'], 'built': node['content'] is not None,
            'exits': exits, 'is_ending': not (o.get('exits') or []),
            'failure_exit': o.get('failure_exit'),
            'clock': c.get('clock'), 'ending_variants': c.get('ending_variants'),
        }
        if with_interactions and c:
            d['interactions'] = [
                f"{room.get('room')}: {it.get('action')} {it.get('target')}"
                + (f" -> {', '.join(w['variable'] + '=' + w['value'] for w in it.get('sets') or [])}" if it.get('sets') else '')
                for room in as_list(c.get('rooms')) if isinstance(room, dict)
                for it in as_list(room.get('interactions')) if isinstance(it, dict)
            ]
            d['characters_built'] = [{'name': ch.get('name'), 'agenda': ch.get('agenda'), 'moved_by': ch.get('moved_by')}
                                     for ch in as_list(c.get('characters')) if isinstance(ch, dict)]
        return d

    def digest(self, with_interactions=False):
        open_exits = []
        for nid in self.node_order:
            for ex in self.nodes[nid]['outline'].get('exits') or []:
                if not ex.get('leads_to'):
                    open_exits.append({'node': nid, 'exit_id': ex.get('id'), 'summary': ex.get('summary')})
        return {
            'through_lines': [{'id': l['id'], **l['through_line'], 'ending': l['ending'], 'path': l['path'],
                               'divergence': l['divergence'], 'rejoins_at': l['rejoins_at']}
                              for l in self.lines.values()],
            'nodes': [self.node_digest(nid, with_interactions) for nid in self.node_order],
            'open_exits': open_exits,
        }

    # ------------------------------------------------------------------ output

    def story_json(self):
        u = self.upstream()
        return {
            'story_id': self.gen.story_id,
            'kernel': u['kernel'],
            'shape': u['shape'],
            'through_lines': self.lines,
            'nodes': {nid: {'outline': b['outline'], 'content': b['content'], 'line_ids': b['line_ids'],
                            'iteration': b['iteration'], 'revisions': b['revisions'], 'changes': b.get('changes', [])}
                      for nid, b in self.nodes.items()},
            'node_order': self.node_order,
            'cast': u['cast'],
            'world': u['world'],
            'state_variables': self.state_variables,
            'iterations': self.iterations,
            'stop_reason': self.stop_reason,
            'warnings': self.warnings,
        }

    def save_story(self):
        self.gen.save_story_json('s4_story.json', self.story_json())
        self.gen.save_story_file('s4_story.md', self.story_markdown())

    def story_markdown(self):
        u = self.upstream()
        out = [f'# {self.gen.story_id} - step 4 story', '']
        out.append(f'Kernel: {(u["kernel"] or "").strip()}')
        out.append('')
        out.append('## Through-lines')
        for l in self.lines.values():
            tl, e = l['through_line'], l.get('ending') or {}
            out.append(f"- **{l['id']} {tl.get('title', '')}**: {tl.get('motivation', '')} / strategy: {tl.get('strategy', '')}")
            out.append(f"  path: {' -> '.join(l['path'])}")
            out.append(f"  ending {e.get('id', '')} {e.get('title', '')}: {e.get('summary', '')}")
            if l.get('divergence'):
                dv = l['divergence']
                out.append(f"  diverges at {dv.get('node')} ({dv.get('kind')}): {dv.get('how_the_shift_is_explained', '')}")
        out.append('')
        out.append('## Cast')
        for c in as_list((u['cast'] or {}).get('characters')):
            if isinstance(c, dict):
                out.append(f"- **{c.get('name')}** ({c.get('role', '')}): wants {c.get('wants', '')}; holds {c.get('holds', '')}"
                           + (f"; speaks for {c['speaks_for']}" if c.get('speaks_for') else ''))
        for c in as_list((u['cast'] or {}).get('crowds')):
            if isinstance(c, dict):
                out.append(f"- crowd **{c.get('name')}**: {c.get('who', '')} (represented by {', '.join(as_list(c.get('representatives')))})")
        out.append('')
        out.append('## Rooms')
        pres = (u['world'] or {}).get('protagonist_presence') or {}
        if pres:
            out.append(f"Protagonist presence: {pres.get('how', '')}")
        for r in as_list((u['world'] or {}).get('rooms')):
            if isinstance(r, dict):
                out.append(f"- **{r.get('id')} {r.get('name')}**: {r.get('purpose', '')}; fixtures {', '.join(as_list(r.get('fixtures')))}; "
                           f"connects {', '.join(as_list(r.get('connections')))}")
        out.append('')
        out.append('## Nodes')
        for nid in self.node_order:
            b = self.nodes[nid]
            o, c = b['outline'], b['content'] or {}
            flags = []
            if o.get('turn_ref') is not None:
                flags.append(f"turn {o['turn_ref']}")
            if not (o.get('exits') or []):
                flags.append('ENDING')
            out.append(f"### {nid} - {o.get('title', '')} {'[' + ', '.join(flags) + ']' if flags else ''}")
            out.append(f"lines: {', '.join(b['line_ids'])}; rooms: {', '.join(as_list(o.get('rooms')))}; "
                       f"characters: {', '.join(as_list(o.get('characters')))}")
            out.append('')
            out.append(f"Goal: {o.get('goal', '')}")
            if o.get('what_happens'):
                out.append(f"On the line: {o['what_happens']}")
            if c.get('arrival'):
                out.append('')
                out.append(c['arrival'])
            for room in as_list(c.get('rooms')):
                if not isinstance(room, dict):
                    continue
                out.append('')
                out.append(f"**{room.get('room')}** ({room.get('now', '')})")
                for it in as_list(room.get('interactions')):
                    if isinstance(it, dict):
                        sets = ', '.join(f"{w['variable']}={w['value']}" for w in it.get('sets') or [])
                        req = ', '.join(f"{w['variable']}={w['value']}" for w in it.get('requires') or [])
                        out.append(f"- {it.get('action')} {it.get('target')}: {it.get('result', '')}"
                                   + (f" [sets {sets}]" if sets else '') + (f" [requires {req}]" if req else ''))
            for ch in as_list(c.get('characters')):
                if isinstance(ch, dict):
                    out.append(f"- {ch.get('name')} in {ch.get('in_room')}: {ch.get('agenda', '')} (moved by: {ch.get('moved_by', '')})")
            if c.get('clock'):
                out.append(f"Clock: {json.dumps(c['clock'], ensure_ascii=False)}")
            built = {ex.get('id'): ex for ex in c.get('exits') or [] if isinstance(ex, dict)}
            for ex in o.get('exits') or []:
                bx = built.get(ex.get('id')) or {}
                when = ', '.join(f"{w['variable']}={w['value']}" for w in bx.get('when') or [])
                out.append(f"- exit {ex.get('id')} -> {ex.get('leads_to') or '(open)'}: {ex.get('summary', '')}"
                           + (f" [when {when}]" if when else '') + (f" {bx.get('transition', '')}" if bx.get('transition') else ''))
            if c.get('failure_exit'):
                out.append(f"Failure exit: {json.dumps(c['failure_exit'], ensure_ascii=False)}")
            if c.get('ending_variants'):
                out.append('Ending variants: ' + json.dumps(c['ending_variants'], ensure_ascii=False))
            out.append('')
        out.append('## Iterations')
        for it in self.iterations:
            t = it.get('termination') or {}
            out.append(f"- iteration {it['iteration']} ({it['line_id']}): new {it['new_node_ids']}, modified {it['modified_node_ids']}, "
                       f"repaired {it['repaired_node_ids']}; review: {t.get('recommendation', '')} - {t.get('reasoning', '')}")
        out.append('')
        out.append(f'Stop reason: {self.stop_reason}')
        if self.warnings:
            out.append('')
            out.append('Warnings:')
            for w in self.warnings:
                out.append(f'- {w}')
        return '\n'.join(out) + '\n'
