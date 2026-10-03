"""Step 4: the outline loop.

The product is a STORY GRAPH at summary level: what happens, in what
order, where the branches are, and which characters and places are needed.
Not how a scene plays: no rooms, fixtures, interactions, state variables or
exit conditions. Those belong to the later stages (docs/later_stages.md).

Units
  BEAT   a slot of the chosen framework (config/frameworks.json): a job in
         the story, with no content of its own.
  NODE   one beat filled on one line: a short summary of what happens,
         where (location sketches) and who (character sketches).
  LINE   a through-line: a motivation, a strategy, an ending, and a path of
         nodes. The main line is laid down first; every later line leaves
         an existing line at a node, on a plain-language trigger, and ends
         in its own ending or rejoins.

One iteration
  iteration 1   4a main line   the through-line, the framework's beats
                               adapted to this story, the premise's turns
                               placed in them
  iteration n   4c divergence  a seed (motivation, strategy, where it
                               leaves) grown into a line plan
  every one     4b line nodes  each new node filled: title, summary, where,
                               who; characters and locations registered as
                               they are needed
                computed       graph integrity, beat coverage, turn
                               placement, branch reachability, register use
                               (generator/checks.py)
                4d next line   one small judgment: is another line worth
                               building, and what is its seed

Every structural rule is enforced by the validator of the call that could
break it, so a bad answer is rejected and re-asked with the complaint in
hand; nothing waits for a review pass. What the validators cannot decide is
reported as notes in the story document.

Call prefixes: s4a_i1, s4c_i<n>, s4b_i<n> (and s4b_i<n>_p2 ... when a line
has more than four new nodes), s4d_i<n>. State is rebuilt by
replaying this driver over the saved files, so a rerun makes no model call.
The story document (<id>_story.json / .md) is rewritten after every
iteration and is the one file the later stages read and annotate.
"""

import json

from brief import brief_lite, shape_targets
from stats import SCHEMA_VERSION
import checks
import example_guard
import frameworks
import schemas


FILL_CHUNK = 4      # nodes filled per 4b call


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compact_json(obj):
    """JSON a model can read without the indentation tax: top-level keys on
    their own lines, each list item on one line. Still valid JSON."""
    def item(v):
        return json.dumps(v, ensure_ascii=False)

    def value(v):
        if isinstance(v, list) and v and all(isinstance(i, (dict, list)) for i in v):
            return '[\n' + ',\n'.join('   ' + item(i) for i in v) + '\n ]'
        return item(v)

    if isinstance(obj, dict):
        return '{\n' + ',\n'.join(f' {json.dumps(k)}: {value(v)}' for k, v in obj.items()) + '\n}'
    return value(obj)


norm = checks.norm


def to_int(value):
    """An integer, or None for null / 'null' / '' / anything else. 2.0 and
    "2.0" are 2; 2.5 is nothing."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number == int(number) else None


class OutlineBuilder:

    def __init__(self, gen, max_iterations=4):
        self.gen = gen
        self.max_iterations = max_iterations

        self.framework = gen.analysis.get('framework') or {}
        self.beats = [b['id'] for b in self.framework.get('beats') or []]
        self.premise = gen.analysis.get('s3_5_premise') or {}
        self.turns = [t for t in self.premise.get('turns') or [] if isinstance(t, dict)]
        self.turn_ids = [t.get('id') for t in self.turns]

        self.lines = {}
        self.line_order = []
        self.nodes = {}
        self.node_order = []
        self.characters = {}
        self.locations = {}
        self.iterations = []
        self.stop_reason = None
        self.warnings = []

        self.shape = self.targets()
        self.register_premise_cast()

    # ------------------------------------------------------------------ inputs

    def targets(self):
        """Advisory numbers: how many lines the Kernel's shape suggests, and
        a node range that is never below the framework's required beats."""
        shape = shape_targets(self.gen.shape)
        fw = {'beats': self.framework.get('beats') or []}
        lo, hi = frameworks.node_range(fw, shape['nodes_min'], shape['nodes_max'])
        shape['nodes_min'], shape['nodes_max'] = lo, hi
        return shape

    def premise_digest(self):
        """The engine as the line-planning prompts need it: no bookkeeping
        tags, the ways of each turn numbered so a line can say which one it
        takes."""
        p = self.premise
        med = p.get('mediation') or {}

        def pick(d, *keys):
            d = d if isinstance(d, dict) else {}
            return {k: d.get(k) for k in keys}

        return {
            'protagonist': pick(p.get('protagonist'), 'who', 'wants', 'can_do', 'cannot_do'),
            'pressure': (p.get('pressure') or {}).get('description'),
            'opposition': pick(p.get('opposition'), 'who_or_what', 'wants', 'means'),
            'question': med.get('question'),
            'pole_a': pick(med.get('to_reach_pole_a'), 'pole', 'what_you_must_do', 'cost'),
            'pole_b': pick(med.get('to_reach_pole_b'), 'pole', 'what_you_must_do', 'cost'),
            'levers': med.get('levers'),
            'turns': [{'id': t.get('id'), 'form': t.get('form'), 'situation': t.get('situation'),
                       'what_you_must_do': t.get('what_you_must_do'),
                       'ways': [f"{i}. {w.get('way')} (cost: {w.get('cost')})"
                                for i, w in enumerate(as_list(t.get('ways_through')), 1) if isinstance(w, dict)],
                       'involves': t.get('involves')} for t in self.turns],
            'complications': [c.get('description') for c in as_list(p.get('complications')) if isinstance(c, dict)],
        }

    def framework_block(self):
        fw = self.framework
        mod = fw.get('modifier') or {}
        return {
            'framework': fw.get('name'),
            'shape': fw.get('shape'),
            'what_kind_of_story': fw.get('reading'),
            'modifier': (f"{mod.get('name')}: {mod.get('effect')}" if mod.get('id') not in (None, 'none') else 'none'),
            'beats': [{'id': b['id'], 'job': b['job'], 'required': b.get('required', True)} for b in fw.get('beats') or []],
        }

    def brief_lite_json(self):
        return compact_json(brief_lite(self.gen.analysis.get('s3_brief')))

    def beat(self, beat_id):
        for b in self.framework.get('beats') or []:
            if b['id'] == beat_id:
                return b
        return None

    def beat_index(self, beat_id):
        return self.beats.index(beat_id) if beat_id in self.beats else -1

    def normalize_beat(self, value):
        """Accept a beat by id or by name ('Opening crisis')."""
        v = str(value or '').strip()
        if v in self.beats:
            return v
        key = norm(v).replace(' ', '_')
        for b in self.framework.get('beats') or []:
            if key == b['id'] or norm(v) == norm(b['name']):
                return b['id']
        return v

    def turn(self, turn_id):
        for t in self.turns:
            if str(t.get('id')) == str(turn_id):
                return t
        return None

    # ------------------------------------------------------------------ registers

    def register_premise_cast(self):
        for seed in as_list(self.premise.get('cast_seeds')):
            if isinstance(seed, dict) and seed.get('role'):
                self.add_character({'label': seed['role'], 'kind': seed.get('kind'), 'speaks_for': seed.get('speaks_for'),
                                    'wants': seed.get('wants'), 'holds': seed.get('holds'),
                                    'opposition': seed.get('opposition'), 'why': '',
                                    'matters_to_turns': seed.get('matters_to_turns') or []}, source='premise')

    def add_character(self, c, source):
        cid = f'C{len(self.characters) + 1:02d}'
        self.characters[cid] = {
            'id': cid, 'label': str(c.get('label')).strip(),
            'kind': 'crowd' if str(c.get('kind') or '').lower() == 'crowd' else 'individual',
            'speaks_for': c.get('speaks_for') or None, 'wants': c.get('wants') or '', 'holds': c.get('holds') or '',
            'opposition': bool(c.get('opposition')), 'why': c.get('why') or '',
            'matters_to_turns': c.get('matters_to_turns') or [], 'source': source, 'nodes': [],
            # filled by the character buildout (stage B)
            'name': None, 'profile': None, 'packet': None,
        }
        return cid

    def add_location(self, loc, source):
        lid = f'L{len(self.locations) + 1:02d}'
        self.locations[lid] = {
            'id': lid, 'name': str(loc.get('name')).strip(), 'kind': loc.get('kind') or '', 'why': loc.get('why') or '',
            'source': source, 'nodes': [],
            # filled by the setting buildout (stage B)
            'rooms': None, 'packet': None,
        }
        return lid

    @staticmethod
    def match(name, table, key, shortened=False):
        """Resolve a name the model wrote against a register. The same name
        up to case, punctuation and a leading article is the same entry.
        Nothing looser is ever applied to a DECLARATION, so "Sector B" is
        never folded into "Sector A" and "the widow's son" never into "the
        widow". With shortened=True (a reference from a node, never a
        declaration) a name whose words all appear, in order, in exactly one
        registered name also resolves ("the overseer" for "the life-support
        overseer"); the caller reports it. Returns the id or None."""
        want = norm(name)
        if not want:
            return None
        for rid, r in table.items():
            if norm(r.get(key)) == want:
                return rid
        if shortened:
            words = want.split()
            hits = []
            for rid, r in table.items():
                have = iter(norm(r.get(key)).split())
                if all(w in have for w in words):
                    hits.append(rid)
            if len(hits) == 1:
                return hits[0]
        return None

    def representatives(self, crowd_label, table=None):
        table = table if table is not None else self.characters
        return [cid for cid, c in table.items() if checks.speaks_for(c, {'label': crowd_label})]

    def register_view(self):
        return {
            'characters': [{'label': c['label'], 'kind': c['kind'], 'speaks_for': c['speaks_for'],
                            'wants': c['wants'], 'holds': c['holds']} for c in self.characters.values()],
            'locations': [{'name': l['name'], 'kind': l['kind'], 'why': l['why']} for l in self.locations.values()],
        }

    # ------------------------------------------------------------------ main loop

    def run(self):
        n = 1
        while n <= self.max_iterations:
            print(f'--- step 4, iteration {n}')
            if n == 1:
                line, new_ids = self.apply_main_line(self.main_line())
            else:
                seed = (self.iterations[-1].get('judge') or {}).get('seed')
                proposal = self.divergence(n, seed)
                if proposal.get('status') != 'proposed':
                    self.stop_reason = (f"4c found the seed did not hold at iteration {n}: "
                                        f"{proposal.get('why', '')}")
                    break
                line, new_ids = self.apply_divergence(n, proposal)

            for part, chunk in enumerate(self.fill_chunks(new_ids), 1):
                self.apply_fill(line, chunk, self.fill(n, line, chunk, part))
            record = {'iteration': n, 'line': line['id'], 'new_nodes': new_ids, 'judge': None}
            self.iterations.append(record)

            if self.shape['through_lines'] <= 1:
                self.stop_reason = 'the Kernel asked for one ending; one line was built'
            elif n >= self.max_iterations:
                self.stop_reason = f'reached --max-iterations ({self.max_iterations})'
            else:
                self.save_story()
                judge = self.next_line(n)
                record['judge'] = judge
                if str(judge.get('recommendation', '')).lower() != 'continue':
                    self.stop_reason = f"4d recommended stopping after iteration {n}: {judge.get('assessment', '')}"
            self.save_story()
            if self.stop_reason:
                break
            n += 1

        if not self.stop_reason:
            self.stop_reason = 'loop ended'
        story = self.save_story()
        print(f'--- step 4 done: {self.stop_reason}')
        for f in story['checks']['findings']:
            print(f"  CHECK FAILED ({f['kind']}): {f['issue']}")
        print(f"  {len(self.lines)} line(s), {len(self.nodes)} node(s), {len(self.characters)} character(s), "
              f"{len(self.locations)} location(s); {len(story['checks']['notes'])} note(s) in the story document")
        return story

    # ------------------------------------------------------------------ plan validation (shared by 4a and 4c)

    def check_beat_entries(self, entries, problems, first_index=0, taken_turns=(), label='beats'):
        """Normalizes a plan's beat entries in place and appends what is
        wrong with them to `problems`: an unknown beat, beats out of
        framework order, a turn that does not exist, is repeated, is out of
        order or was already played on the shared part of the path, a way
        the turn does not have."""
        if not isinstance(entries, list):
            problems.append(f'{label} must be a list')
            return
        last_index = first_index
        last_turn_pos = max([self.turn_ids.index(t) for t in taken_turns if t in self.turn_ids], default=-1)
        seen_turns = set(taken_turns)
        per_beat = {}
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                problems.append(f'{label}[{i}] must be an object')
                continue
            e['beat'] = self.normalize_beat(e.get('beat'))
            if e['beat'] not in self.beats:
                problems.append(f"{label}[{i}].beat \"{e['beat']}\" is not a beat of this framework; the beats are {self.beats}")
                continue
            idx = self.beats.index(e['beat'])
            if idx < last_index:
                ahead = 'the node this line leaves from' if i == 0 else 'the entry ahead of it'
                problems.append(f"{label}[{i}] is beat {e['beat']}, which comes before the beat of {ahead}; "
                                f"entries follow the framework's order {self.beats}")
            last_index = max(last_index, idx)
            per_beat[e['beat']] = per_beat.get(e['beat'], 0) + 1
            if per_beat[e['beat']] == 3:
                problems.append(f"three entries share beat {e['beat']}; a beat holds one node, or two when two turns fall in it")
            turn = to_int(e.get('turn'))
            e['turn'] = turn
            e['way'] = to_int(e.get('way'))
            if turn is None:
                e['way'] = None
            elif turn not in self.turn_ids:
                problems.append(f'{label}[{i}].turn {turn} is not a premise turn; the turns are {self.turn_ids}')
            elif turn in seen_turns:
                problems.append(f'premise turn {turn} is already played earlier on this line; a line plays each turn once')
            else:
                pos = self.turn_ids.index(turn)
                if pos < last_turn_pos:
                    problems.append(f'premise turn {turn} is placed after a later turn; turns keep their order')
                last_turn_pos = max(last_turn_pos, pos)
                seen_turns.add(turn)
                ways = len(as_list((self.turn(turn) or {}).get('ways_through')))
                if e['way'] is not None and not (1 <= e['way'] <= ways):
                    problems.append(f"{label}[{i}].way {e['way']}: turn {turn} has ways 1 to {ways}; use null if the line "
                                    f"resolves the turn some other way")
            if not str(e.get('adapted') or '').strip():
                problems.append(f'{label}[{i}].adapted is empty')

    @staticmethod
    def check_through_line(parsed, problems, need=('title', 'motivation', 'strategy')):
        tl = parsed.get('through_line')
        if not isinstance(tl, dict):
            problems.append('through_line must be an object')
        else:
            for k in need:
                if not str(tl.get(k) or '').strip():
                    problems.append(f'through_line.{k} is empty')
        ending = parsed.get('ending')
        if not isinstance(ending, dict) or not str(ending.get('summary') or '').strip():
            problems.append('ending needs a summary')

    def normalize_skips(self, parsed):
        skips = []
        for s in as_list(parsed.get('skipped_beats')):
            if isinstance(s, dict) and self.normalize_beat(s.get('beat')) in self.beats:
                skips.append({'beat': self.normalize_beat(s.get('beat')), 'reason': str(s.get('reason') or '').strip()})
        parsed['skipped_beats'] = skips
        return {s['beat']: s['reason'] for s in skips}

    # ------------------------------------------------------------------ 4a: the main line

    def craft_json(self):
        """The optional craft spine (main.py --craft-spine), cut to what a
        line call uses; the literal string none when it did not run."""
        c = self.gen.analysis.get('s3_75_craft_spine')
        if not isinstance(c, dict):
            return 'none'
        wn = c.get('want_need_tension') or {}
        want, need = wn.get('want'), wn.get('need')
        return compact_json({
            'want': want.get('restated') if isinstance(want, dict) else want,
            'need': need.get('description') if isinstance(need, dict) else need,
            'tension': wn.get('tension'),
            'irony': (c.get('irony_mode') or {}).get('device'),
            'setup_payoff': [{'setup': p.get('setup'), 'payoff': p.get('payoff')}
                             for p in c.get('setup_payoff_pairs') or [] if isinstance(p, dict)],
        })

    def check_example_copy(self, parsed, prompt_file, problems):
        """Reject an answer that reuses the prompt's illustration (see
        example_guard.py). The kernel, the brief and the premise are the
        context the answer may legitimately echo."""
        hits = example_guard.copied_phrases(
            parsed, [prompt_file],
            [self.gen.kernel or '', json.dumps(self.gen.analysis.get('s3_brief') or {}), json.dumps(self.premise)])
        if len(hits) >= example_guard.MIN_HITS:
            problems.append(f"the answer copies the prompt's illustration ({len(hits)} of its phrases, e.g. "
                            f"{'; '.join(hits[:4])}); write this story's own content")

    def main_line(self):
        required = frameworks.required_beats({'beats': self.framework.get('beats') or []})

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            problems = []
            self.check_through_line(parsed, problems)
            self.check_beat_entries(parsed.get('beats'), problems)
            entries = [e for e in as_list(parsed.get('beats')) if isinstance(e, dict)]
            self.normalize_skips(parsed)
            covered = {e.get('beat') for e in entries}
            missing = [b for b in required if b not in covered]
            if missing:
                problems.append(f'the main line has no entry for required beat(s) {missing}')
            placed = [e.get('turn') for e in entries if e.get('turn') is not None]
            unplaced = [t for t in self.turn_ids if t not in placed]
            if unplaced:
                problems.append(f'premise turn(s) {unplaced} are not placed; the main line plays every turn once')
            if len(entries) > self.shape['nodes_max'] + 3:
                problems.append(f"{len(entries)} entries; aim for {self.shape['nodes_min']} to {self.shape['nodes_max']}")
            self.check_example_copy(parsed, 's4a_main_line.prompt', problems)
            if problems:
                raise ValueError('; '.join(problems))

        return self.gen.run_prompt('s4a_i1', 'main_line', {
            '$$KERNEL$$': self.gen.kernel,
            '$$BRIEF_LITE_JSON$$': self.brief_lite_json(),
            '$$PREMISE_JSON$$': compact_json(self.premise_digest()),
            '$$FRAMEWORK_JSON$$': compact_json(self.framework_block()),
            '$$CRAFT_JSON$$': self.craft_json(),
            '$$NODES_MIN$$': str(self.shape['nodes_min']),
            '$$NODES_MAX$$': str(self.shape['nodes_max']),
        }, prompt_file='s4a_main_line.prompt', validator=validate, klass='build', schema=schemas.MAIN_LINE)

    def apply_main_line(self, plan):
        entries = [e for e in plan['beats'] if isinstance(e, dict)]
        ids = []
        for i, e in enumerate(entries, 1):
            nid = f'N{i:02d}'
            self.new_node(nid, 'T1', 1, e)
            ids.append(nid)
        self.nodes[ids[-1]]['is_ending'] = True
        tl = plan['through_line']
        self.lines['T1'] = {
            'id': 'T1', 'iteration': 1, 'title': tl.get('title'), 'motivation': tl.get('motivation'),
            'strategy': tl.get('strategy'), 'turning_point': tl.get('turning_point'), 'differs_from': None,
            'ending': {'title': (plan.get('ending') or {}).get('title'), 'summary': (plan.get('ending') or {}).get('summary'),
                       'node': ids[-1]},
            'path': list(ids), 'new_nodes': list(ids), 'parent': None, 'divergence': None, 'rejoins_at': None,
            'skipped_beats': plan.get('skipped_beats') or [],
        }
        self.line_order.append('T1')
        return self.lines['T1'], ids

    def new_node(self, nid, line_id, iteration, entry):
        self.nodes[nid] = {
            'id': nid, 'line': line_id, 'iteration': iteration,
            'beat': entry['beat'], 'turn': entry.get('turn'), 'way': entry.get('way'),
            'adapted': str(entry.get('adapted') or '').strip(),
            'title': '', 'summary': '', 'where': [], 'who': [],
            'is_ending': False, 'lines': [line_id],
            # what a later line needs this node to contain for its trigger to be possible
            'additions': [],
            # later stages write here: 'expansion' (stage A), 'build' (stage D)
            'annotations': {},
        }
        self.node_order.append(nid)

    # ------------------------------------------------------------------ digests

    def line_containing(self, node_id):
        for lid in self.line_order:
            if node_id in self.lines[lid]['path']:
                return self.lines[lid]
        raise ValueError(f'no line contains node {node_id}')

    def digest(self):
        """The story so far, at one entry per node: what the planning and
        judging prompts read instead of the story."""
        lines = []
        for lid in self.line_order:
            l = self.lines[lid]
            dv = l.get('divergence') or {}
            entry = {'id': lid, 'title': l.get('title'), 'motivation': l.get('motivation'),
                     'strategy': l.get('strategy'), 'ending': (l.get('ending') or {}).get('summary'),
                     'path': l.get('path')}
            if dv:
                entry['leaves'] = f"{l.get('parent')} after {dv.get('diverges_at')} when: {dv.get('trigger')}"
            if l.get('rejoins_at'):
                entry['rejoins_at'] = l['rejoins_at']
            lines.append(entry)
        nodes = []
        for nid in self.node_order:
            node = self.nodes[nid]
            entry = {'id': nid, 'beat': node['beat']}
            if node['turn'] is not None:
                entry['turn'], entry['way'] = node['turn'], node['way']
            if node['is_ending']:
                entry['ending'] = True
            entry['what'] = (node['title'] + ': ' if node['title'] else '') + node['adapted']
            nodes.append(entry)
        return {'lines': lines, 'nodes': nodes}

    def divergence_nodes(self):
        """Where a new line may leave. Under a linear shape, only the last
        node before the main line's ending: one road, many endings."""
        if self.shape.get('linear'):
            path = self.lines['T1']['path']
            return path[-2:-1] if len(path) > 1 else []
        return [nid for nid in self.node_order if not self.nodes[nid]['is_ending']]

    def shape_note(self):
        """The one paragraph of the judge's and the planner's prompts that
        depends on the Kernel's stated shape."""
        if self.shape.get('linear'):
            at = self.divergence_nodes()
            return ("LINEAR SHAPE. The Kernel asked for one road with no forks. A new line may leave the main line "
                    f"only at {at[0] if at else 'the last node before the ending'}, the last node before the ending. "
                    "Its trigger is the pattern of what the player did across the earlier nodes (an \"accumulated\" "
                    "trigger), not a single act there, and it adds exactly one node: its own ending.")
        return ("BRANCHING SHAPE. A new line may leave the story after any node listed as a valid divergence node. "
                "Its trigger is normally something the player did in that node.")

    def hooks(self):
        return checks.derive_hooks(self.story_json(light=True))

    # ------------------------------------------------------------------ 4d: is another line worth building

    def next_line(self, n):
        valid = self.divergence_nodes()
        med = self.premise.get('mediation') or {}

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            rec = str(parsed.get('recommendation') or '').strip().lower()
            if rec not in ('continue', 'stop'):
                raise ValueError('recommendation must be "continue" or "stop"')
            parsed['recommendation'] = rec
            if rec == 'stop':
                parsed['seed'] = None
                return
            seed = parsed.get('seed')
            if not isinstance(seed, dict):
                raise ValueError('recommendation is "continue", so seed must be an object')
            problems = []
            for k in ('motivation', 'strategy', 'trigger'):
                if not str(seed.get(k) or '').strip():
                    problems.append(f'seed.{k} is empty')
            if seed.get('diverges_at') not in valid:
                problems.append(f"seed.diverges_at \"{seed.get('diverges_at')}\" is not a node a line may leave from; "
                                f"valid nodes are {valid}")
            self.check_example_copy(parsed, 's4d_next_line.prompt', problems)
            if problems:
                raise ValueError('; '.join(problems))

        return self.gen.run_prompt(f's4d_i{n}', 'next_line', {
            '$$QUESTION_JSON$$': self.gen.to_json({
                'question': med.get('question'),
                'pole_a': (med.get('to_reach_pole_a') or {}).get('pole'),
                'pole_b': (med.get('to_reach_pole_b') or {}).get('pole'),
                'protagonist_wants': (self.premise.get('protagonist') or {}).get('wants'),
                'opposition_wants': (self.premise.get('opposition') or {}).get('wants'),
            }),
            '$$STORY_DIGEST_JSON$$': compact_json(self.digest()),
            '$$HOOKS_JSON$$': compact_json({'unused_ways': self.hooks()}),
            '$$COUNTS_JSON$$': self.gen.to_json({
                'lines_built': len(self.lines),
                'lines_the_kernel_suggests': self.shape['through_lines'],
                'valid_divergence_nodes': valid,
            }),
            '$$SHAPE_NOTE$$': self.shape_note(),
        }, prompt_file='s4d_next_line.prompt', validator=validate, klass='judge', schema=schemas.NEXT_LINE)

    # ------------------------------------------------------------------ 4c: a divergent line

    def divergence(self, n, seed):
        valid = self.divergence_nodes()
        linear = bool(self.shape.get('linear'))

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            status = str(parsed.get('status') or '').strip().lower()
            if status not in ('proposed', 'nothing_worth_building'):
                raise ValueError('status must be "proposed" or "nothing_worth_building"')
            parsed['status'] = status
            if status != 'proposed':
                return
            problems = []
            self.check_through_line(parsed, problems)
            if isinstance(parsed.get('through_line'), dict) and not str(parsed['through_line'].get('differs_from') or '').strip():
                problems.append('through_line.differs_from is empty: say how this line differs in kind from each existing line')
            dv = parsed.get('divergence')
            if not isinstance(dv, dict):
                raise ValueError('divergence must be an object')
            at = dv.get('diverges_at')
            if at not in valid:
                raise ValueError(f'divergence.diverges_at "{at}" is not a node a line may leave from; valid nodes are {valid}')
            if not str(dv.get('trigger') or '').strip():
                problems.append('divergence.trigger is empty')
            kind = str(dv.get('trigger_kind') or 'act').strip().lower()
            dv['trigger_kind'] = 'accumulated' if (linear or kind.startswith('acc')) else 'act'
            parent = self.line_containing(at)
            prefix = parent['path'][:parent['path'].index(at) + 1]
            taken = [self.nodes[x]['turn'] for x in prefix if self.nodes[x]['turn'] is not None]
            at_turn = self.nodes[at]['turn']
            dv['way'] = to_int(dv.get('way'))
            if dv['way'] is not None:
                ways = len(as_list((self.turn(at_turn) or {}).get('ways_through'))) if at_turn is not None else 0
                if not (1 <= dv['way'] <= ways):
                    dv['way'] = None
                elif dv['way'] == self.nodes[at]['way'] and at in parent['path']:
                    problems.append(f"divergence.way {dv['way']} is the way the existing line already takes at {at}; a new "
                                    f"line leaves by a different way, or by something else (way null)")
                elif any((self.lines[l].get('divergence') or {}).get('diverges_at') == at
                         and (self.lines[l].get('divergence') or {}).get('way') == dv['way'] for l in self.line_order):
                    problems.append(f"another line already leaves {at} by way {dv['way']}")
            entries = parsed.get('beats')
            self.check_beat_entries(entries, problems, first_index=self.beat_index(self.nodes[at]['beat']),
                                    taken_turns=taken)
            entries = [e for e in as_list(entries) if isinstance(e, dict)]
            if not entries:
                problems.append('beats is empty: a new line adds at least one node of its own')
            if len(entries) > 5:
                problems.append(f'{len(entries)} new nodes; a divergent line adds one to five')
            rejoin = parsed.get('rejoins_at') or None
            if isinstance(rejoin, str) and rejoin.strip().lower() in ('', 'null', 'none'):
                rejoin = None
            parsed['rejoins_at'] = rejoin
            if linear:
                if rejoin:
                    problems.append('under a linear shape a new line does not rejoin; it is one ending node')
                if len(entries) != 1:
                    problems.append('under a linear shape a new line adds exactly one node: its ending')
            if rejoin:
                if rejoin not in self.nodes:
                    problems.append(f'rejoins_at "{rejoin}" is not an existing node')
                elif rejoin in prefix:
                    problems.append(f'rejoins_at {rejoin} is on the part of the path the line shares before it leaves; '
                                    f'a line rejoins further on')
                else:
                    last = entries[-1].get('beat') if entries else self.nodes[at]['beat']
                    if self.beat_index(self.nodes[rejoin]['beat']) < self.beat_index(last):
                        problems.append(f"rejoins_at {rejoin} is at beat {self.nodes[rejoin]['beat']}, earlier than this "
                                        f"line's last new beat {last}")
                    # the line's whole path is prefix + new nodes + the tail from the
                    # rejoin on; it must not pass a node twice, and its turns must
                    # still come once each and in order
                    tail_line = self.line_containing(rejoin)
                    tail = tail_line['path'][tail_line['path'].index(rejoin):]
                    again = [x for x in tail if x in prefix]
                    if again:
                        problems.append(f'after rejoining at {rejoin} the line would pass through {again} a second time; '
                                        f'rejoin at a node whose onward path does not lead back')
                    new_turns = [e.get('turn') for e in entries if e.get('turn') is not None]
                    tail_turns = [self.nodes[x]['turn'] for x in tail if self.nodes[x]['turn'] is not None]
                    clash = [t for t in tail_turns if t in taken + new_turns]
                    if clash:
                        problems.append(f'after rejoining at {rejoin} the line would play turn(s) {clash} a second time')
                    else:
                        order = [self.turn_ids.index(t) for t in taken + new_turns + tail_turns if t in self.turn_ids]
                        if any(b < a for a, b in zip(order, order[1:])):
                            problems.append(f'after rejoining at {rejoin} the line would play its turns out of order '
                                            f'({taken + new_turns + tail_turns}); rejoin after the turns it has already played')
            skips = self.normalize_skips(parsed)
            if entries:
                covered = {e.get('beat') for e in entries} | {self.nodes[x]['beat'] for x in prefix}
                if rejoin in self.nodes:
                    tail_line = self.line_containing(rejoin)
                    covered |= {self.nodes[x]['beat'] for x in tail_line['path'][tail_line['path'].index(rejoin):]}
                required = frameworks.required_beats({'beats': self.framework.get('beats') or []})
                missing = [b for b in required if b not in covered and not skips.get(b)]
                if missing:
                    problems.append(f'required beat(s) {missing} are neither on this line\'s path nor listed in '
                                    f'skipped_beats with a reason')
            self.check_example_copy(parsed, 's4c_divergence.prompt', problems)
            if problems:
                raise ValueError('; '.join(problems))

        return self.gen.run_prompt(f's4c_i{n}', 'divergence', {
            '$$KERNEL$$': self.gen.kernel,
            '$$BRIEF_LITE_JSON$$': self.brief_lite_json(),
            '$$PREMISE_JSON$$': compact_json(self.premise_digest()),
            '$$FRAMEWORK_JSON$$': compact_json(self.framework_block()),
            '$$CRAFT_JSON$$': self.craft_json(),
            '$$STORY_DIGEST_JSON$$': compact_json(self.digest()),
            '$$HOOKS_JSON$$': compact_json({'unused_ways': self.hooks()}),
            '$$SEED_JSON$$': self.gen.to_json(seed),
            '$$VALID_NODES$$': ', '.join(valid),
            '$$SHAPE_NOTE$$': self.shape_note(),
            '$$ITERATION$$': str(n),
        }, prompt_file='s4c_divergence.prompt', validator=validate, klass='build', schema=schemas.DIVERGENCE)

    def apply_divergence(self, n, p):
        line_id = f'T{n}'
        dv = p['divergence']
        at = dv['diverges_at']
        parent = self.line_containing(at)
        prefix = parent['path'][:parent['path'].index(at) + 1]
        entries = [e for e in p['beats'] if isinstance(e, dict)]
        new_ids = []
        for i, e in enumerate(entries, 1):
            nid = f'{line_id}N{i:02d}'
            self.new_node(nid, line_id, n, e)
            new_ids.append(nid)
        rejoin = p.get('rejoins_at') or None
        tail = []
        if rejoin:
            tail_line = self.line_containing(rejoin)
            tail = tail_line['path'][tail_line['path'].index(rejoin):]
        else:
            self.nodes[new_ids[-1]]['is_ending'] = True
        path = prefix + new_ids + tail
        for nid in prefix + tail:
            if line_id not in self.nodes[nid]['lines']:
                self.nodes[nid]['lines'].append(line_id)
        if str(dv.get('opportunity') or '').strip().lower() not in ('', 'null', 'none'):
            self.nodes[at]['additions'].append({'line': line_id, 'text': str(dv['opportunity']).strip()})
        else:
            dv['opportunity'] = None
        tl = p['through_line']
        self.lines[line_id] = {
            'id': line_id, 'iteration': n, 'title': tl.get('title'), 'motivation': tl.get('motivation'),
            'strategy': tl.get('strategy'), 'turning_point': tl.get('turning_point'),
            'differs_from': tl.get('differs_from'),
            'ending': {'title': (p.get('ending') or {}).get('title'), 'summary': (p.get('ending') or {}).get('summary'),
                       'node': path[-1]},
            'path': path, 'new_nodes': new_ids, 'parent': parent['id'],
            'divergence': {'diverges_at': at, 'trigger': str(dv.get('trigger')).strip(),
                           'trigger_kind': dv.get('trigger_kind') or 'act', 'way': dv.get('way'),
                           'instead_of': str(dv.get('instead_of') or '').strip(),
                           'opportunity': dv.get('opportunity'), 'shift': str(dv.get('shift') or '').strip()},
            'rejoins_at': rejoin, 'skipped_beats': p.get('skipped_beats') or [], 'why': p.get('why'),
        }
        self.line_order.append(line_id)
        return self.lines[line_id], new_ids

    # ------------------------------------------------------------------ 4b: fill the line's nodes

    def fill_packet(self, line, new_ids):
        nodes = []
        for nid in new_ids:
            node = self.nodes[nid]
            b = self.beat(node['beat']) or {}
            entry = {'id': nid, 'beat': f"{b.get('name')}: {b.get('job')}", 'plan': node['adapted']}
            if node['turn'] is not None:
                t = self.turn(node['turn']) or {}
                ways = as_list(t.get('ways_through'))
                way = ways[node['way'] - 1] if node['way'] and node['way'] <= len(ways) else None
                entry['turn'] = {'situation': t.get('situation'), 'what_you_must_do': t.get('what_you_must_do'),
                                 'the_way_this_line_takes': (f"{way.get('way')} (cost: {way.get('cost')})"
                                                             if isinstance(way, dict) else 'its own; see the plan'),
                                 'involves': t.get('involves')}
            if node['is_ending']:
                entry['this_is_the_ending'] = (line.get('ending') or {}).get('summary')
            nodes.append(entry)
        # what came before: the two nodes just ahead in full, the rest at one line each
        earlier = [nid for nid in line['path'][:line['path'].index(new_ids[0])]]
        before = [{'id': nid, 'what': (self.nodes[nid]['title'] + ': ' if self.nodes[nid]['title'] else '')
                   + ((self.nodes[nid]['summary'] if nid in earlier[-2:] else '') or self.nodes[nid]['adapted'])}
                  for nid in earlier]
        dv = line.get('divergence') or {}
        packet = {
            'line': {'id': line['id'], 'title': line.get('title'), 'motivation': line.get('motivation'),
                     'strategy': line.get('strategy'), 'turning_point': line.get('turning_point')},
            'already_told': before,
        }
        if dv:
            packet['this_line_leaves_when'] = dv.get('trigger')
        if line.get('rejoins_at'):
            r = self.nodes[line['rejoins_at']]
            packet['then_rejoins'] = f"{line['rejoins_at']}: {r['title'] or r['adapted']}"
        packet['nodes_to_fill'] = nodes
        return packet

    @staticmethod
    def fill_chunks(new_ids):
        """A line's nodes are filled at most FILL_CHUNK to a call, in even
        parts (seven nodes: four, then three). Output size is what the trace
        scales with, and a second call sees the places and summaries the
        first one produced."""
        if len(new_ids) <= FILL_CHUNK:
            return [list(new_ids)]
        parts = -(-len(new_ids) // FILL_CHUNK)
        size = -(-len(new_ids) // parts)
        return [list(new_ids[i:i + size]) for i in range(0, len(new_ids), size)]

    def fill(self, n, line, new_ids, part=1):
        prot = self.premise.get('protagonist') or {}
        f = (self.gen.analysis.get('s3_brief') or {}).get('fields') or {}
        setting = {
            'arena': (self.premise.get('arena') or {}).get('description'),
            'footprint': f"{(f.get('3f.setting_structure') or {}).get('ceiling')} setting, "
                         f"{(f.get('3f.setting_scale') or {}).get('ceiling')} scale",
            'you_are': prot.get('who'), 'you_can': prot.get('can_do'), 'you_cannot': prot.get('cannot_do'),
        }

        def validate(parsed):
            if not isinstance(parsed, dict) or not isinstance(parsed.get('nodes'), list):
                raise ValueError('nodes must be a list')
            got = [x for x in parsed['nodes'] if isinstance(x, dict)]
            if len(got) != len(new_ids):
                raise ValueError(f'nodes must have exactly one entry for each of {new_ids}; got {len(got)}')
            if {x.get('id') for x in got} != set(new_ids):
                for x, nid in zip(got, new_ids):   # right count, drifted ids: take them in order
                    x['id'] = nid
            parsed['nodes'] = got
            parsed['new_locations'] = [x for x in as_list(parsed.get('new_locations')) if isinstance(x, dict) and x.get('name')]
            new_chars = [x for x in as_list(parsed.get('new_characters')) if isinstance(x, dict) and x.get('label')]
            parsed['new_characters'] = new_chars
            trial = dict(self.characters)
            for i, c in enumerate(new_chars):
                if not self.match(c['label'], trial, 'label'):
                    trial[f'new{i}'] = {'label': c['label'], 'speaks_for': c.get('speaks_for'),
                                        'kind': 'crowd' if str(c.get('kind') or '').lower() == 'crowd' else 'individual'}
            problems = []
            for c in new_chars:
                if str(c.get('kind') or '').lower() == 'crowd' and not self.representatives(c['label'], trial):
                    problems.append(f"new crowd \"{c['label']}\" has no individual whose speaks_for names it; a crowd is "
                                    f"never the thing the player talks to")
            for x in got:
                for k in ('title', 'summary'):
                    if not str(x.get(k) or '').strip():
                        problems.append(f"node {x['id']}: {k} is empty")
                x['where'] = [str(w).strip() for w in as_list(x.get('where')) if str(w).strip()]
                x['who'] = [str(w).strip() for w in as_list(x.get('who')) if str(w).strip()]
                if not x['where']:
                    problems.append(f"node {x['id']}: where is empty; every node happens somewhere")
                if len(x['where']) > 3:
                    problems.append(f"node {x['id']}: {len(x['where'])} places; a node plays in one to three")
                unknown = [w for w in x['who'] if not self.match(w, trial, 'label', shortened=True)]
                if unknown:
                    problems.append(f"node {x['id']}: who names {unknown}, who are neither in the character register nor in "
                                    f"new_characters; registered labels are {[c['label'] for c in self.characters.values()]}")
            self.check_example_copy(parsed, 's4b_line_nodes.prompt', problems)
            if problems:
                raise ValueError('; '.join(problems))

        prefix = f's4b_i{n}' + (f'_p{part}' if part > 1 else '')
        return self.gen.run_prompt(prefix, 'line_nodes', {
            '$$BRIEF_LITE_JSON$$': self.brief_lite_json(),
            '$$SETTING_JSON$$': self.gen.to_json(setting),
            '$$PACKET_JSON$$': compact_json(self.fill_packet(line, new_ids)),
            '$$REGISTER_JSON$$': compact_json(self.register_view()),
        }, prompt_file='s4b_line_nodes.prompt', validator=validate, klass='build', schema=schemas.LINE_NODES)

    def apply_fill(self, line, new_ids, fill):
        for loc in fill.get('new_locations') or []:
            if not self.match(loc['name'], self.locations, 'name'):
                self.add_location(loc, source=line['id'])
        for c in fill.get('new_characters') or []:
            if not self.match(c['label'], self.characters, 'label'):
                self.add_character(c, source=line['id'])
        for x in fill['nodes']:
            node = self.nodes[x['id']]
            node['title'] = str(x.get('title')).strip()
            node['summary'] = str(x.get('summary')).strip()
            where = []
            for name in x['where']:
                lid = self.match(name, self.locations, 'name')
                if not lid:
                    lid = self.match(name, self.locations, 'name', shortened=True)
                    if lid:
                        self.warnings.append(f"node {x['id']}: \"{name}\" was read as the registered location "
                                             f"\"{self.locations[lid]['name']}\"")
                if not lid:
                    # used but never declared: register it bare rather than
                    # spend a model call on it; the checks report it
                    lid = self.add_location({'name': name, 'kind': '', 'why': ''}, source=line['id'])
                    self.warnings.append(f"node {x['id']}: location \"{name}\" was used without being declared; registered as {lid}")
                if lid not in where:
                    where.append(lid)
            node['where'] = where
            who = []
            for label in x['who']:
                cid = self.match(label, self.characters, 'label')
                if not cid:
                    cid = self.match(label, self.characters, 'label', shortened=True)
                    if cid:
                        self.warnings.append(f"node {x['id']}: \"{label}\" was read as the registered character "
                                             f"\"{self.characters[cid]['label']}\"")
                if cid and cid not in who:
                    who.append(cid)
            for cid in list(who):
                c = self.characters[cid]
                if c['kind'] == 'crowd' and not set(self.representatives(c['label'])) & set(who):
                    reps = self.representatives(c['label'])
                    if reps:
                        who.append(reps[0])
                        self.warnings.append(f"node {x['id']}: crowd \"{c['label']}\" was present without a voice; "
                                             f"added {self.characters[reps[0]]['label']}")
            node['who'] = who

    # ------------------------------------------------------------------ the story document

    def story_json(self, light=False):
        story = {
            'schema_version': SCHEMA_VERSION,
            'story_id': self.gen.story_id,
            'stage': 'outline',
            'kernel': self.gen.kernel,
            'shape': self.shape,
            'premise': self.premise,
            'framework': self.framework,
            'lines': self.lines,
            'line_order': self.line_order,
            'nodes': self.nodes,
            'node_order': self.node_order,
            'characters': self.characters,
            'locations': self.locations,
        }
        if light:
            return story
        usage = checks.derive_usage(story)
        for cid, c in self.characters.items():
            c['nodes'] = usage['characters'].get(cid, [])
        for lid, l in self.locations.items():
            l['nodes'] = usage['locations'].get(lid, [])
        story['edges'] = checks.derive_edges(story)
        story['grid'] = checks.derive_grid(story)
        story['hooks'] = checks.derive_hooks(story)
        story['checks'] = checks.check_story(story)
        story['iterations'] = self.iterations
        story['stop_reason'] = self.stop_reason
        story['warnings'] = self.warnings
        return story

    def save_story(self):
        story = self.story_json()
        self.gen.save_story_json('story.json', story)
        self.gen.save_story_file('story.md', story_markdown(story))
        return story


# ---------------------------------------------------------------- markdown

def story_markdown(story):
    """The story graph as something a person can read top to bottom."""
    lines, nodes = story['lines'], story['nodes']
    chars, locs = story['characters'], story['locations']
    fw = story.get('framework') or {}
    out = [f"# {story['story_id']}: story outline", '']
    out.append(f"Kernel: {(story.get('kernel') or '').strip()}")
    out.append('')
    mod = fw.get('modifier') or {}
    out.append(f"## Story form: {fw.get('name')}" + (f" + {mod.get('name')}" if mod.get('id') not in (None, 'none') else ''))
    if fw.get('reading'):
        out.append(str(fw['reading']))
    if fw.get('why'):
        out.append(f"Why this form: {fw['why']}")
    out.append('')
    q = ((story.get('premise') or {}).get('mediation') or {}).get('question')
    if q:
        out.append(f'The question: {q}')
        out.append('')

    out.append('## Lines')
    for lid in story['line_order']:
        l = lines[lid]
        out.append(f"### {lid}: {l.get('title')}")
        out.append(f"- motivation: {l.get('motivation')}")
        out.append(f"- strategy: {l.get('strategy')}")
        if l.get('turning_point'):
            out.append(f"- turning point: {l.get('turning_point')}")
        dv = l.get('divergence')
        if dv:
            out.append(f"- leaves {l.get('parent')} after {dv.get('diverges_at')} when: {dv.get('trigger')}"
                       + (f" ({dv.get('trigger_kind')})" if dv.get('trigger_kind') != 'act' else ''))
            if dv.get('instead_of'):
                out.append(f"  - instead of: {dv['instead_of']}")
            if dv.get('opportunity'):
                out.append(f"  - {dv.get('diverges_at')} must now contain: {dv['opportunity']}")
            if dv.get('shift'):
                out.append(f"  - why the shift: {dv['shift']}")
        if l.get('differs_from'):
            out.append(f"- differs: {l['differs_from']}")
        if l.get('rejoins_at'):
            out.append(f"- rejoins at {l['rejoins_at']}")
        e = l.get('ending') or {}
        out.append(f"- ending ({e.get('node')}) {e.get('title') or ''}: {e.get('summary')}")
        out.append(f"- path: {' > '.join(l.get('path') or [])}")
        for s in l.get('skipped_beats') or []:
            out.append(f"- skips beat {s.get('beat')}: {s.get('reason')}")
        out.append('')

    grid = story.get('grid') or {}
    if grid.get('beats'):
        out.append('## Lines x beats')
        out.append('| line | ' + ' | '.join(grid['beats']) + ' |')
        out.append('|---|' + '---|' * len(grid['beats']))
        for lid in story['line_order']:
            row = grid['rows'].get(lid, {})
            skipped = {s.get('beat') for s in grid.get('skipped', {}).get(lid, [])}
            cells = []
            for b in grid['beats']:
                ids = row.get(b) or []
                own = set(lines[lid].get('new_nodes') or [])
                cells.append(', '.join(i if i in own else f'({i})' for i in ids) or ('skipped' if b in skipped else '-'))
            out.append(f'| {lid} | ' + ' | '.join(cells) + ' |')
        out.append('')
        out.append('Parentheses mark a node the line shares with an earlier line.')
        out.append('')

    out.append('## Nodes')
    for nid in story['node_order']:
        n = nodes[nid]
        b = next((x for x in fw.get('beats') or [] if x['id'] == n['beat']), {})
        tags = [b.get('name') or n['beat']]
        if n.get('turn') is not None:
            tags.append(f"turn {n['turn']}" + (f", way {n['way']}" if n.get('way') else ''))
        if n.get('is_ending'):
            tags.append('ENDING')
        out.append(f"### {nid}: {n.get('title') or '(unfilled)'} [{'; '.join(tags)}]")
        out.append(f"lines: {', '.join(n.get('lines') or [])}")
        out.append(f"where: {', '.join(locs[x]['name'] for x in n.get('where') or [] if x in locs) or '-'}")
        out.append(f"who: {', '.join(chars[x]['label'] for x in n.get('who') or [] if x in chars) or '-'}")
        out.append('')
        out.append(n.get('summary') or n.get('adapted') or '')
        for a in n.get('additions') or []:
            out.append('')
            out.append(f"For {a.get('line')}, this node must also contain: {a.get('text')}")
        out.append('')

    edges = story.get('edges') or []
    forks = [nid for nid in story['node_order'] if any(e['from'] == nid and e['kind'] == 'branch' for e in edges)]
    rejoins = [e for e in edges if e['kind'] == 'rejoin']
    if forks or rejoins:
        out.append('## Branch points')
        for nid in forks:
            out.append(f'- after {nid}:')
            for e in [e for e in edges if e['from'] == nid]:
                if e['kind'] == 'branch':
                    t = e.get('trigger') or {}
                    kind = '' if t.get('kind') == 'act' else f" [{t.get('kind')}]"
                    out.append(f"  - when {t.get('text')}{kind} -> {e['to']} ({', '.join(e['lines'])})")
                else:
                    out.append(f"  - otherwise ({'; '.join(e.get('otherwise') or []) or 'the existing line'}) -> {e['to']} ({', '.join(e['lines'])})")
        for e in rejoins:
            out.append(f"- {e['from']} -> {e['to']}: line {', '.join(e['lines'])} rejoins the existing story")
        out.append('')

    out.append('## Characters')
    for c in chars.values():
        bits = [c['kind']]
        if c.get('opposition'):
            bits.append('opposition')
        if c.get('speaks_for'):
            bits.append(f"speaks for {c['speaks_for']}")
        out.append(f"- **{c['label']}** ({', '.join(bits)}): wants {c.get('wants') or '?'}; holds {c.get('holds') or '?'}"
                   + (f"; {c['why']}" if c.get('why') else '')
                   + f" [{', '.join(c.get('nodes') or []) or 'unused'}]")
    out.append('')
    out.append('## Locations')
    for l in locs.values():
        out.append(f"- **{l['name']}**" + (f" ({l['kind']})" if l.get('kind') else '') + f": {l.get('why') or '(not described)'}"
                   f" [{', '.join(l.get('nodes') or []) or 'unused'}]")
    out.append('')

    hooks = story.get('hooks') or []
    if hooks:
        out.append('## Ways no line has taken')
        for h in hooks:
            out.append(f"- {h['node']} (turn {h['turn']}, way {h['way']}): {h['what']} (cost: {h['cost']})")
        out.append('')

    ck = story.get('checks') or {}
    out.append('## Computed checks')
    if not ck.get('findings') and not ck.get('notes'):
        out.append('Nothing to report.')
    for f in ck.get('findings') or []:
        out.append(f"- BROKEN ({f['kind']}): {f['issue']}")
    for f in ck.get('notes') or []:
        out.append(f"- note ({f['kind']}): {f['issue']}")
    out.append('')
    out.append('## Iterations')
    for it in story.get('iterations') or []:
        j = it.get('judge') or {}
        out.append(f"- iteration {it['iteration']}: line {it['line']}, new nodes {', '.join(it['new_nodes'])}"
                   + (f"; next: {j.get('recommendation')} - {j.get('assessment')}" if j else ''))
    out.append('')
    out.append(f"Stop reason: {story.get('stop_reason')}")
    if story.get('warnings'):
        out.append('')
        out.append('Warnings:')
        for w in story['warnings']:
            out.append(f'- {w}')
    return '\n'.join(str(line) for line in out) + '\n'
