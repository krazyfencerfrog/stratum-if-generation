"""Step 4: the iterative outline build-out.

One iteration builds one complete path through the story:

  iteration 1:  4a_first  -> framework, ending mechanism, main-path outline
  iteration n:  4a_next   -> pick an unexplored branch-point outcome, outline
                             the new branch from that beat forward
                (4c5      -> only if 4a_next chose to TRANSFORM the framework)
  every iteration:
                entity_define  for each role-level character/location the
                               outline names that isn't on the roster yet
                beat_generate  for each new beat, in path order
                4d verify      whole-story review + termination judgment
                beat repair    re-generate the beats 4d's findings name
                4d re-verify   (once) so the termination call is made on the
                               repaired story

Everything the model produces goes through StoryGenerator.run_prompt with a
unique prefix per call (s4a_i1, s4e_i1_03, s4b_i2_p2_b04, s4d_i2_r1, ...), so
a rerun replays this driver, finds every file, and rebuilds the same state
without a model call. The assembled story is written to <id>_s4_story.json
(machine) and <id>_s4_story.md (human) after every iteration.

What is computed here rather than asked of the model: the branch-point table
(which outcome values of which branch beats have a path built for them),
the story digest the review and next-outline prompts read (everything but
scene prose), the state-variable registry, and the path bookkeeping. Those
are counts and lookups; the model is spent on outlining, writing and
judging.
"""

import re
import json


ARTICLE_RE = re.compile(r'^(the|a|an|your|our|my)\s+', re.IGNORECASE)


def norm_role(text):
    """Normalized key for matching role-level entity references
    ('the maintenance foreman' == 'Maintenance foreman')."""
    s = (text or '').strip().lower()
    s = ARTICLE_RE.sub('', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return s


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
    """Beat outputs express state writes as [{"variable","value"}]; tolerate
    a bare string ("orientation = collective"), a dict, or a list of
    strings, since a small model will drift on this shape."""
    out = []
    for item in as_list(writes):
        if isinstance(item, dict):
            var = item.get('variable') or item.get('var') or item.get('name')
            if var:
                out.append({'variable': str(var).strip(),
                            'value': '' if item.get('value') is None else str(item.get('value'))})
        elif isinstance(item, str) and item.strip() and item.strip().lower() != 'none':
            m = re.match(r'\s*([^=:]+?)\s*[=:]\s*(.+)$', item)
            if m:
                out.append({'variable': m.group(1).strip(), 'value': m.group(2).strip()})
            else:
                out.append({'variable': item.strip(), 'value': ''})
    return out


class Step4Builder:

    def __init__(self, gen, max_iterations=6, max_repair_beats=6):
        self.gen = gen
        self.max_iterations = max_iterations
        self.max_repair_beats = max_repair_beats

        self.framework = None
        self.ending_mechanism = None
        self.paths = {}          # path_id -> dict
        self.beats = {}          # beat_id -> dict(outline, content, path_ids, iteration)
        self.beat_order = []
        self.roster = {'characters': {}, 'locations': {}}
        self.role_map = {}       # norm_role(role) -> {'kind', 'name', 'decision', 'role'}
        self.state_variables = {}
        self.iterations = []
        self.stop_reason = None
        self.warnings = []

    # ------------------------------------------------------------------ upstream material

    def upstream(self):
        g = self.gen
        return {
            'kernel': g.kernel,
            'bundle': g.step3_bundle_json(),
            'cross_check': g.analysis_json('s3h_cross_check'),
            'premise': g.analysis.get('s3_5_premise_expansion') or {},
            'premise_json': g.analysis_json('s3_5_premise_expansion'),
            'craft': g.analysis.get('s3_75_craft_spine') or {},
            'craft_json': g.analysis_json('s3_75_craft_spine'),
            'failure_model': g.analysis_json('s3_0c_consequence_failure_model'),
            'epistemic': g.analysis_json('s3_0b_identity_epistemic'),
            'affect': g.analysis_json('s3b_affect'),
            'theme': g.analysis_json('s3c_theme'),
            'interactive': g.analysis_json('s3_0a_interactive_question'),
            'complexity': g.analysis_json('s3g_complexity'),
        }

    def budget(self):
        premise = self.gen.analysis.get('s3_5_premise_expansion') or {}
        return str((premise.get('enrichment_budget') or {}).get('level', 'moderate'))

    def instance(self, ref):
        premise = self.gen.analysis.get('s3_5_premise_expansion') or {}
        instances = (premise.get('instance_generator') or {}).get('instances') or []
        if ref is None or ref == '':
            return None
        try:
            index = int(ref)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(instances):
            item = dict(instances[index])
            item['index'] = index
            item['true_state'] = (premise.get('instance_generator') or {}).get('true_state', '')
            return item
        return None

    # ------------------------------------------------------------------ main loop

    def run(self):
        n = 1
        while n <= self.max_iterations:
            print(f'--- step 4, iteration {n}')
            if n == 1:
                outline = self.first_outline()
                new_beats = outline['main_path_outline']
                path = self.register_path(n, new_beats, branch_from=None, reconverges_to=None)
            else:
                if not self.unexplored_candidates():
                    self.stop_reason = 'no unexplored branch-point outcomes remain'
                    break
                try:
                    nxt = self.next_outline(n)
                except ValueError as e:
                    self.stop_reason = f'4a_next produced no usable branch selection: {e}'
                    self.warnings.append(self.stop_reason)
                    break
                if nxt.get('status') != 'branch_selected':
                    self.stop_reason = '4a_next reports no unexplored branch points'
                    break
                new_beats = nxt['new_branch_outline']
                path = self.register_path(n, new_beats,
                                          branch_from=nxt['selected'],
                                          reconverges_to=nxt.get('reconverges_to'))
                decision = (nxt.get('framework_decision') or {}).get('keep_or_transform', 'keep')
                if str(decision).lower().startswith('transform'):
                    path['craft_spine_override'] = self.craft_refresh(n, path, nxt)

            self.resolve_entities(n, new_beats)
            for beat_entry in new_beats:
                self.generate_beat(n, beat_entry['id'], path['id'])
            if path.get('reconverges_to'):
                self.revise_shared_beat(n, path)

            review = self.verify(n, round_no=0)
            repaired = self.repair_beats(n, review)
            if repaired:
                review = self.verify(n, round_no=1)

            self.iterations.append({
                'iteration': n,
                'path_id': path['id'],
                'new_beat_ids': [b['id'] for b in new_beats],
                'repaired_beat_ids': repaired,
                'termination': review.get('termination', {}),
            })
            self.save_story()

            termination = review.get('termination') or {}
            recommendation = str(termination.get('overall_recommendation', '')).lower()
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

    def outline_validator(self, key):
        def validate(parsed):
            beats = parsed.get(key)
            if not isinstance(beats, list) or not beats:
                raise ValueError(f'{key} must be a non-empty list')
            seen = set()
            for b in beats:
                if not isinstance(b, dict):
                    raise ValueError('outline entries must be objects')
                for k in ('id', 'role', 'content_summary'):
                    if not b.get(k):
                        raise ValueError(f'outline entry missing {k}')
                if b['id'] in seen:
                    raise ValueError(f'duplicate beat id {b["id"]} in outline')
                seen.add(b['id'])
                if b.get('is_branch_point') and not isinstance(b.get('branch'), dict):
                    raise ValueError(f'beat {b["id"]} is a branch point but has no "branch" object')
        return validate

    def first_outline(self):
        u = self.upstream()
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$STEP3_BUNDLE_JSON$$': u['bundle'],
            '$$CROSS_CHECK_JSON$$': u['cross_check'],
            '$$PREMISE_EXPANSION_JSON$$': u['premise_json'],
            '$$CRAFT_SPINE_JSON$$': u['craft_json'],
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }
        outline = self.gen.run_prompt('s4a_i1', 'first_outline', repl,
                                      prompt_file='s4a_first_outline.prompt',
                                      validator=self.outline_validator('main_path_outline'))
        self.framework = outline.get('framework_choice')
        self.ending_mechanism = outline.get('ending_mechanism') or {}
        for var in as_list(self.ending_mechanism.get('selector_variables')):
            if isinstance(var, dict) and var.get('name'):
                self.state_variables[var['name']] = {
                    'kind': 'selector',
                    'type': var.get('kind', 'enum'),
                    'values': [str(v) for v in as_list(var.get('values'))],
                    'declared_by': '4a_first',
                    'written_by': [],
                    'read_by': [],
                }
        beats = outline['main_path_outline']
        if not any(b.get('is_terminal') for b in beats):
            beats[-1]['is_terminal'] = True
        return outline

    def next_outline(self, n):
        u = self.upstream()
        table = self.branch_table()
        last_review = self.iterations[-1]['termination'] if self.iterations else {}

        def validate(parsed):
            status = parsed.get('status')
            if status not in ('branch_selected', 'no_unexplored_branch_points'):
                raise ValueError('status must be branch_selected or no_unexplored_branch_points')
            if status == 'no_unexplored_branch_points':
                return
            sel = parsed.get('selected') or {}
            bid, val = sel.get('beat_id'), str(sel.get('outcome_value', ''))
            match = [c for c in table['candidates'] if c['beat_id'] == bid and c['outcome_value'] == val]
            if not match:
                raise ValueError(
                    f'selected {bid}/{val} is not an unexplored candidate; choose from '
                    f'{[(c["beat_id"], c["outcome_value"]) for c in table["candidates"]]}')
            self.outline_validator('new_branch_outline')(parsed)
            for b in parsed['new_branch_outline']:
                if b['id'] in self.beats:
                    raise ValueError(f'new beat id {b["id"]} collides with an existing beat; new ids must be fresh')
            rec = parsed.get('reconverges_to')
            if rec and rec not in self.beats:
                raise ValueError(f'reconverges_to names unknown beat {rec}')

        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$STEP3_BUNDLE_JSON$$': u['bundle'],
            '$$PREMISE_EXPANSION_JSON$$': u['premise_json'],
            '$$CRAFT_SPINE_JSON$$': u['craft_json'],
            '$$FRAMEWORK_JSON$$': self.gen.to_json({'framework_choice': self.framework,
                                                    'ending_mechanism': self.ending_mechanism}),
            '$$STORY_DIGEST_JSON$$': self.gen.to_json(self.digest()),
            '$$BRANCH_POINT_TABLE_JSON$$': self.gen.to_json(table),
            '$$PRIOR_REVIEW_JSON$$': self.gen.to_json(last_review),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
            '$$ITERATION$$': str(n),
        }
        nxt = self.gen.run_prompt(f's4a_i{n}', 'next_outline', repl,
                                  prompt_file='s4a_next_outline.prompt', validator=validate)
        if nxt.get('status') == 'branch_selected':
            beats = nxt['new_branch_outline']
            if not nxt.get('reconverges_to') and not any(b.get('is_terminal') for b in beats):
                beats[-1]['is_terminal'] = True
        return nxt

    def craft_refresh(self, n, path, nxt):
        u = self.upstream()
        prefix_ids = path['beat_ids'][:len(path['beat_ids']) - len(nxt['new_branch_outline'])]
        repl = {
            '$$CRAFT_SPINE_JSON$$': u['craft_json'],
            '$$BRANCH_ID$$': path['id'],
            '$$FRAMEWORK_DECISION_JSON$$': self.gen.to_json(nxt.get('framework_decision')),
            '$$BRANCH_OUTLINE_JSON$$': self.gen.to_json(nxt['new_branch_outline']),
            '$$SHARED_PREFIX_JSON$$': self.gen.to_json([self.beat_digest(b) for b in prefix_ids]),
            '$$EPISTEMIC_GAP_JSON$$': u['epistemic'],
            '$$AFFECT_JSON$$': u['affect'],
            '$$PREMISE_EXPANSION_JSON$$': u['premise_json'],
            '$$STATE_VARIABLES_JSON$$': self.gen.to_json(self.state_variables),
        }
        refresh = self.gen.run_prompt(f's4c5_i{n}', 'craft_refresh', repl,
                                      prompt_file='s4c5_craft_refresh.prompt',
                                      validator=self.gen.require_keys('want_need_tension', 'irony_mode',
                                                                      'escalation_shape', 'setup_payoff_pairs'))
        merged = dict(u['craft'])
        for field in ('want_need_tension', 'irony_mode', 'escalation_shape', 'setup_payoff_pairs', 'motif'):
            entry = refresh.get(field)
            if isinstance(entry, dict) and str(entry.get('status', '')).lower() in ('adjusted', 'refreshed'):
                if entry.get('content_if_changed') is not None:
                    merged[field] = entry['content_if_changed']
        merged['refreshed_for_branch'] = path['id']
        return merged

    # ------------------------------------------------------------------ paths and beats

    def register_path(self, n, new_beats, branch_from, reconverges_to):
        path_id = f'P{n}'
        if branch_from is None:
            beat_ids = []
        else:
            parent = self.path_containing(branch_from['beat_id'])
            ids = parent['beat_ids']
            beat_ids = ids[:ids.index(branch_from['beat_id']) + 1]
            for bid in beat_ids:
                self.beats[bid]['path_ids'].append(path_id)
        for entry in new_beats:
            entry = dict(entry)
            entry.setdefault('is_branch_point', False)
            entry.setdefault('is_terminal', False)
            self.beats[entry['id']] = {
                'outline': entry,
                'content': None,
                'path_ids': [path_id],
                'iteration': n,
                'revisions': [],
            }
            self.beat_order.append(entry['id'])
            beat_ids.append(entry['id'])
        if reconverges_to:
            rec_path = self.path_containing(reconverges_to)
            tail = rec_path['beat_ids'][rec_path['beat_ids'].index(reconverges_to):]
            for bid in tail:
                self.beats[bid]['path_ids'].append(path_id)
            beat_ids.extend(tail)
        path = {
            'id': path_id,
            'iteration': n,
            'beat_ids': beat_ids,
            'branch_from': branch_from,
            'reconverges_to': reconverges_to,
            'craft_spine_override': None,
        }
        self.paths[path_id] = path
        return path

    def path_containing(self, beat_id):
        for pid in sorted(self.paths, key=lambda p: self.paths[p]['iteration']):
            if beat_id in self.paths[pid]['beat_ids']:
                return self.paths[pid]
        raise ValueError(f'no path contains beat {beat_id}')

    def path_follows(self, beat_id, path_id):
        """Which outcome value of a branch beat this path continues along."""
        outline = self.beats[beat_id]['outline']
        branch = outline.get('branch') or {}
        path = self.paths[path_id]
        bf = path.get('branch_from')
        if bf and bf.get('beat_id') == beat_id:
            return str(bf.get('outcome_value', ''))
        # inherited: whichever path first contained this beat
        origin = self.path_containing(beat_id)
        obf = origin.get('branch_from')
        if obf and obf.get('beat_id') == beat_id:
            return str(obf.get('outcome_value', ''))
        return str(branch.get('path_follows', ''))

    def previous_beat_id(self, beat_id, path_id):
        ids = self.paths[path_id]['beat_ids']
        i = ids.index(beat_id)
        return ids[i - 1] if i > 0 else None

    def next_outline_entry(self, beat_id, path_id):
        ids = self.paths[path_id]['beat_ids']
        i = ids.index(beat_id)
        if i + 1 < len(ids):
            nxt = self.beats[ids[i + 1]]['outline']
            return {'id': nxt['id'], 'role': nxt.get('role'), 'content_summary': nxt.get('content_summary')}
        return None

    # ------------------------------------------------------------------ entities

    def resolve_entities(self, n, new_beats):
        counter = 0
        for entry in new_beats:
            requests = []
            if entry.get('location'):
                requests.append(('location', entry['location']))
            for c in as_list(entry.get('characters')):
                if isinstance(c, str) and c.strip():
                    requests.append(('character', c))
            for kind, role in requests:
                key = norm_role(role)
                if not key or key in self.role_map:
                    continue
                existing = self.find_roster_name(kind, role)
                if existing:
                    self.role_map[key] = {'kind': kind, 'name': existing, 'decision': 'roster_name', 'role': role}
                    continue
                counter += 1
                self.define_entity(n, counter, kind, role, entry)

    def find_roster_name(self, kind, role):
        bucket = 'characters' if kind == 'character' else 'locations'
        key = norm_role(role)
        for name in self.roster[bucket]:
            if norm_role(name) == key:
                return name
        return None

    def define_entity(self, n, k, kind, role, entry):
        u = self.upstream()
        repl = {
            '$$ENTITY_REQUEST_JSON$$': self.gen.to_json({'kind': kind, 'role': role,
                                                         'requested_by_beat': entry['id']}),
            '$$BEAT_OUTLINE_JSON$$': self.gen.to_json(entry),
            '$$ROSTER_JSON$$': self.gen.to_json(self.roster),
            '$$STATE_VARIABLES_JSON$$': self.gen.to_json(self.state_variables),
            '$$CRAFT_SPINE_JSON$$': u['craft_json'],
            '$$PREMISE_EXPANSION_JSON$$': u['premise_json'],
            '$$THEME_JSON$$': u['theme'],
            '$$INTERACTIVE_QUESTION_JSON$$': u['interactive'],
            '$$ENRICHMENT_BUDGET$$': self.budget(),
            '$$KERNEL$$': u['kernel'],
        }

        def validate(parsed):
            d = parsed.get('decision')
            if d not in ('reuse', 'new_character', 'new_location', 'none_needed'):
                raise ValueError('decision must be reuse / new_character / new_location / none_needed')
            if d == 'reuse' and not parsed.get('existing_entity'):
                raise ValueError('reuse needs existing_entity')
            if d in ('new_character', 'new_location') and not parsed.get('name'):
                raise ValueError('a new entity needs a name')
            if kind == 'location' and d == 'none_needed':
                raise ValueError('a location cannot be none_needed; reuse one or define one')

        prefix = f's4e_i{n}_{k:02d}_{slug(role)[:24]}'
        out = self.gen.run_prompt(prefix, 'entity', repl,
                                  prompt_file='s4_entity_define.prompt', validator=validate)
        key = norm_role(role)
        decision = out['decision']
        if decision == 'reuse':
            name = self.find_roster_name(kind, out['existing_entity']) or out['existing_entity']
            if not self.find_roster_name(kind, name):
                self.warnings.append(f'{prefix}: reused "{name}" which is not on the roster; mapped by name anyway')
            self.role_map[key] = {'kind': kind, 'name': name, 'decision': 'reuse', 'role': role}
        elif decision == 'none_needed':
            self.role_map[key] = {'kind': kind, 'name': None, 'decision': 'none_needed', 'role': role,
                                  'why': out.get('why', '')}
        else:
            bucket = 'characters' if decision == 'new_character' else 'locations'
            record = {k2: v for k2, v in out.items() if k2 != 'decision'}
            record['roles'] = [role]
            record['defined_in'] = prefix
            self.roster[bucket][out['name']] = record
            self.role_map[key] = {'kind': kind, 'name': out['name'], 'decision': decision, 'role': role}
            for flag in as_list(out.get('local_state')):
                if isinstance(flag, dict) and flag.get('key'):
                    self.state_variables.setdefault(flag['key'], {
                        'kind': 'local', 'type': flag.get('type', 'bool'),
                        'values': [], 'initial': flag.get('initial'),
                        'declared_by': out['name'], 'written_by': [], 'read_by': [],
                        'traces_to': flag.get('traces_to', ''),
                    })

    def resolved_entities(self, entry):
        """The roster entries a beat's outline references, resolved."""
        location = None
        chars = []
        notes = []
        if entry.get('location'):
            m = self.role_map.get(norm_role(entry['location']))
            if m and m.get('name'):
                location = m['name']
        for c in as_list(entry.get('characters')):
            m = self.role_map.get(norm_role(c)) if isinstance(c, str) else None
            if m is None:
                continue
            if m.get('name'):
                chars.append(m['name'])
            else:
                notes.append(f'"{c}": none_needed - {m.get("why", "deliver through the environment")}')
        return location, chars, notes

    # ------------------------------------------------------------------ beats

    def beat_validator(self, expected_id):
        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected an object')
            if not parsed.get('scene'):
                raise ValueError('beat needs scene text')
            actions = parsed.get('available_actions')
            if not isinstance(actions, list) or not [a for a in actions if str(a).strip()]:
                raise ValueError('available_actions must be a non-empty list')
            if 'decision' not in parsed:
                raise ValueError('decision is required ("none" or an object)')
            d = parsed['decision']
            if isinstance(d, dict) and not isinstance(d.get('outcomes'), list):
                raise ValueError('decision.outcomes must be a list')
        return validate

    def generate_beat(self, n, beat_id, path_id, revision=None, round_no=0):
        u = self.upstream()
        beat = self.beats[beat_id]
        entry = beat['outline']
        path = self.paths[path_id]
        location, chars, notes = self.resolved_entities(entry)
        prev_id = self.previous_beat_id(beat_id, path_id)

        roster_packet = {
            'this_beat': {
                'location': self.roster['locations'].get(location) if location else None,
                'characters': {c: self.roster['characters'].get(c) for c in chars},
                'entity_notes': notes,
            },
            'all_names': {
                'characters': sorted(self.roster['characters']),
                'locations': sorted(self.roster['locations']),
            },
        }
        outline_packet = dict(entry)
        outline_packet['resolved_location'] = location
        outline_packet['resolved_characters'] = chars
        outline_packet['path_id'] = path_id
        outline_packet['shared_with_paths'] = [p for p in beat['path_ids'] if p != path_id]
        outline_packet['position'] = f"{path['beat_ids'].index(beat_id) + 1} of {len(path['beat_ids'])}"
        outline_packet['next_beat'] = self.next_outline_entry(beat_id, path_id)
        if entry.get('is_branch_point'):
            outline_packet['this_path_follows'] = self.path_follows(beat_id, path_id)

        craft = path.get('craft_spine_override') or u['craft']
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$BEAT_OUTLINE_JSON$$': self.gen.to_json(outline_packet),
            '$$PREVIOUS_BEAT_JSON$$': self.gen.to_json(self.beat_digest(prev_id)) if prev_id else 'none',
            '$$ROSTER_JSON$$': self.gen.to_json(roster_packet),
            '$$INSTANCE_JSON$$': self.gen.to_json(self.instance(entry.get('instance_ref'))),
            '$$STATE_VARIABLES_JSON$$': self.gen.to_json(self.state_variables),
            '$$CRAFT_SPINE_JSON$$': self.gen.to_json(craft),
            '$$FAILURE_MODEL_JSON$$': u['failure_model'],
            '$$ENRICHMENT_BUDGET$$': self.budget(),
            '$$REVISION_JSON$$': self.gen.to_json(revision) if revision else 'none',
        }
        prefix = f's4b_i{n}_{slug(beat_id)}'
        if round_no:
            prefix += f'_r{round_no}'
        content = self.gen.run_prompt(prefix, 'beat', repl, prompt_file='s4_beat_generate.prompt',
                                      validator=self.beat_validator(beat_id))
        content = dict(content)
        content['id'] = beat_id
        if beat['content'] is not None:
            beat['revisions'].append({'prefix': prefix, 'reason': revision})
        beat['content'] = content
        self.register_state(beat_id, content)
        return content

    def register_state(self, beat_id, content):
        decision = content.get('decision')
        if isinstance(decision, dict):
            for outcome in as_list(decision.get('outcomes')):
                if not isinstance(outcome, dict):
                    continue
                writes = normalize_writes(outcome.get('writes'))
                outcome['writes'] = writes
                for w in writes:
                    self.touch_variable(w['variable'], w['value'], beat_id, 'written_by')
        effects = normalize_writes(content.get('state_effects'))
        content['state_effects'] = effects
        for w in effects:
            self.touch_variable(w['variable'], w['value'], beat_id, 'written_by')
        reads = []
        for r in as_list(content.get('reads')):
            if isinstance(r, dict) and r.get('variable'):
                reads.append({'variable': str(r['variable']), 'condition': str(r.get('condition', ''))})
            elif isinstance(r, str) and r.strip():
                reads.append({'variable': r.strip(), 'condition': ''})
        content['reads'] = reads
        for r in reads:
            self.touch_variable(r['variable'], None, beat_id, 'read_by')

    def touch_variable(self, name, value, beat_id, relation):
        var = self.state_variables.setdefault(name, {
            'kind': 'local', 'type': 'flag', 'values': [],
            'declared_by': beat_id, 'written_by': [], 'read_by': [],
        })
        if value not in (None, '') and str(value) not in var['values']:
            var['values'].append(str(value))
        if beat_id not in var[relation]:
            var[relation].append(beat_id)

    def revise_shared_beat(self, n, path):
        """A path that reconverges onto an existing beat makes that beat a
        shared terminal; regenerate it once with that fact as a revision
        request so its content varies by final state."""
        bid = path['reconverges_to']
        beat = self.beats[bid]
        if beat['content'] is None:
            return
        revision = {
            'prior_beat': beat['content'],
            'findings': [{
                'issue': f"This beat is now shared: path {path['id']} reaches it via "
                         f"{path['branch_from']['beat_id']} = {path['branch_from']['outcome_value']}, "
                         f"in addition to {[p for p in beat['path_ids'] if p != path['id']]}.",
                'fix': 'Keep the beat, but describe how its content varies by the final state each '
                       'arriving path carries (shared_terminal_variants), reading the selector '
                       'variables rather than assuming one path.',
            }],
        }
        origin = self.path_containing(bid)
        self.generate_beat(n, bid, origin['id'], revision=revision, round_no=len(beat['revisions']) + 1)

    # ------------------------------------------------------------------ 4d

    def verify(self, n, round_no=0):
        u = self.upstream()
        it_beats = [bid for bid in self.beat_order if self.beats[bid]['iteration'] == n]
        repl = {
            '$$KERNEL$$': u['kernel'],
            '$$STORY_DIGEST_JSON$$': self.gen.to_json(self.digest()),
            '$$STATE_VARIABLES_JSON$$': self.gen.to_json(self.state_variables),
            '$$ROSTER_JSON$$': self.gen.to_json(self.roster),
            '$$BRANCH_POINT_TABLE_JSON$$': self.gen.to_json(self.branch_table()),
            '$$PREMISE_EXPANSION_JSON$$': u['premise_json'],
            '$$COMPLEXITY_JSON$$': u['complexity'],
            '$$THEME_JSON$$': u['theme'],
            '$$THIS_ITERATION_JSON$$': self.gen.to_json({
                'iteration': n, 'path_id': f'P{n}', 'new_beat_ids': it_beats,
                'review_round': round_no,
            }),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }
        prefix = f's4d_i{n}' + (f'_r{round_no}' if round_no else '')
        return self.gen.run_prompt(prefix, 'verify', repl, prompt_file='s4d_verify.prompt',
                                   validator=self.gen.require_keys('consistency', 'coherence_and_novelty',
                                                                   'pacing_and_arcs', 'state_validity',
                                                                   'termination'))

    def collect_findings(self, review):
        """Findings that name beats, grouped by beat id, from every section."""
        by_beat = {}
        for section in ('consistency', 'coherence_and_novelty', 'pacing_and_arcs', 'state_validity'):
            block = review.get(section) or {}
            if not isinstance(block, dict):
                continue
            verdicts = [str(block.get(k, '')).lower() for k in ('verdict', 'coherence_verdict', 'novelty_verdict')]
            for finding in as_list(block.get('findings')):
                if not isinstance(finding, dict):
                    continue
                ids = [b for b in as_list(finding.get('beat_ids')) if b in self.beats]
                if not ids:
                    continue
                if 'flagged' not in verdicts and not finding.get('fix'):
                    continue
                for bid in ids:
                    by_beat.setdefault(bid, []).append({
                        'section': section,
                        'issue': finding.get('issue', ''),
                        'fix': finding.get('fix', ''),
                        'affected_paths': as_list(finding.get('affected_paths')),
                    })
        return by_beat

    def repair_beats(self, n, review):
        by_beat = self.collect_findings(review)
        repaired = []
        for bid in [b for b in self.beat_order if b in by_beat][:self.max_repair_beats]:
            beat = self.beats[bid]
            if beat['content'] is None:
                continue
            path_id = self.path_containing(bid)['id']
            revision = {'prior_beat': beat['content'], 'findings': by_beat[bid]}
            self.generate_beat(n, bid, path_id, revision=revision, round_no=len(beat['revisions']) + 1)
            repaired.append(bid)
        skipped = [b for b in by_beat if b not in repaired]
        if skipped:
            self.warnings.append(f'iteration {n}: findings on {skipped} left for the next review '
                                 f'(--max-repair-beats={self.max_repair_beats})')
        return repaired

    # ------------------------------------------------------------------ computed views

    def branch_table(self):
        selector_names = {k for k, v in self.state_variables.items() if v.get('kind') == 'selector'}
        rows = []
        candidates = []
        for bid in self.beat_order:
            outline = self.beats[bid]['outline']
            if not outline.get('is_branch_point'):
                continue
            branch = outline.get('branch') or {}
            values = [str(v) for v in as_list(branch.get('outcome_values'))]
            explored = {}
            for pid in self.beats[bid]['path_ids']:
                val = self.path_follows(bid, pid)
                if val:
                    explored.setdefault(val, []).append(pid)
            unexplored = [v for v in values if v not in explored]
            rows.append({'beat_id': bid, 'variable': branch.get('variable'), 'outcome_values': values,
                         'explored': explored, 'unexplored': unexplored,
                         'paths_through': self.beats[bid]['path_ids']})
            for v in unexplored:
                candidates.append({'beat_id': bid, 'variable': branch.get('variable'), 'outcome_value': v})
        unmarked = []
        for bid in self.beat_order:
            content = self.beats[bid]['content'] or {}
            outline = self.beats[bid]['outline']
            if outline.get('is_branch_point') or not isinstance(content.get('decision'), dict):
                continue
            for outcome in as_list(content['decision'].get('outcomes')):
                for w in as_list((outcome or {}).get('writes')):
                    if isinstance(w, dict) and w.get('variable') in selector_names:
                        unmarked.append({'beat_id': bid, 'variable': w['variable'],
                                         'note': 'writes an ending-selector variable but was not outlined as a branch point'})
        return {'branch_points': rows, 'candidates': candidates,
                'unmarked_selector_writes': unmarked}

    def unexplored_candidates(self):
        return self.branch_table()['candidates']

    def beat_digest(self, bid):
        if not bid or bid not in self.beats:
            return None
        beat = self.beats[bid]
        o = beat['outline']
        c = beat['content'] or {}
        decision = c.get('decision')
        if isinstance(decision, dict):
            decision = {'action': decision.get('action'),
                        'outcomes': [{'choice': oc.get('choice'), 'writes': oc.get('writes'),
                                      'meaning': oc.get('meaning')}
                                     for oc in as_list(decision.get('outcomes')) if isinstance(oc, dict)]}
        return {
            'id': bid,
            'path_ids': beat['path_ids'],
            'role': o.get('role'),
            'content_summary': o.get('content_summary'),
            'location': c.get('location') or o.get('location'),
            'characters': c.get('characters') or o.get('characters'),
            'instance_ref': o.get('instance_ref'),
            'is_branch_point': o.get('is_branch_point', False),
            'branch': o.get('branch'),
            'is_terminal': o.get('is_terminal', False),
            'failure_exit': o.get('failure_exit'),
            'generated': beat['content'] is not None,
            'available_actions': c.get('available_actions'),
            'decision': decision if decision is not None else ('none' if beat['content'] else None),
            'state_effects': c.get('state_effects'),
            'reads': c.get('reads'),
            'shared_terminal_variants': c.get('shared_terminal_variants'),
            'design_note': c.get('design_note'),
        }

    def digest(self):
        return {
            'framework_choice': self.framework,
            'ending_mechanism': self.ending_mechanism,
            'paths': [{'id': p['id'], 'iteration': p['iteration'], 'beat_ids': p['beat_ids'],
                       'branch_from': p['branch_from'], 'reconverges_to': p['reconverges_to'],
                       'terminal_beat': p['beat_ids'][-1] if p['beat_ids'] else None,
                       'framework_transformed': p['craft_spine_override'] is not None}
                      for p in self.paths.values()],
            'beats': [self.beat_digest(b) for b in self.beat_order],
        }

    # ------------------------------------------------------------------ output

    def story_json(self):
        return {
            'story_id': self.gen.story_id,
            'framework_choice': self.framework,
            'ending_mechanism': self.ending_mechanism,
            'paths': self.paths,
            'beats': {bid: {'outline': b['outline'], 'content': b['content'], 'path_ids': b['path_ids'],
                            'iteration': b['iteration'], 'revisions': b['revisions']}
                      for bid, b in self.beats.items()},
            'beat_order': self.beat_order,
            'roster': self.roster,
            'role_map': self.role_map,
            'state_variables': self.state_variables,
            'iterations': self.iterations,
            'stop_reason': self.stop_reason,
            'warnings': self.warnings,
        }

    def save_story(self):
        self.gen.save_story_json('s4_story.json', self.story_json())
        self.gen.save_story_file('s4_story.md', self.story_markdown())

    def story_markdown(self):
        out = [f'# {self.gen.story_id} - step 4 outline', '']
        out.append(f'Kernel: {self.gen.kernel.strip()}')
        out.append('')
        if self.framework:
            out.append(f"Framework: **{self.framework.get('value', '')}** - {self.framework.get('why', '')}")
        if self.ending_mechanism:
            out.append(f"Ending mechanism: {self.ending_mechanism.get('type', '')} - {self.ending_mechanism.get('note', '')}")
        out.append('')
        out.append('## Paths')
        for p in self.paths.values():
            bf = p['branch_from']
            src = f" (branches from {bf['beat_id']} = {bf['outcome_value']})" if bf else ' (main path)'
            rec = f", reconverges to {p['reconverges_to']}" if p['reconverges_to'] else ''
            out.append(f"- **{p['id']}**{src}{rec}: {' -> '.join(p['beat_ids'])}")
        out.append('')
        out.append('## Roster')
        for name, c in self.roster['characters'].items():
            out.append(f"- character **{name}**: {c.get('manner', '')} (topics: {', '.join(as_list(c.get('baseline_topics')))})")
        for name, l in self.roster['locations'].items():
            out.append(f"- location **{name}**: objects {', '.join(as_list(l.get('static_objects')))}; exits {', '.join(as_list(l.get('exits')))}")
        out.append('')
        out.append('## Beats')
        for bid in self.beat_order:
            b = self.beats[bid]
            o, c = b['outline'], b['content'] or {}
            flags = []
            if o.get('is_branch_point'):
                flags.append('BRANCH POINT')
            if o.get('is_terminal'):
                flags.append('TERMINAL')
            out.append(f"### {bid} - {o.get('role', '')} {'[' + ', '.join(flags) + ']' if flags else ''}")
            out.append(f"paths: {', '.join(b['path_ids'])}; location: {c.get('location') or o.get('location')}; "
                       f"characters: {', '.join(as_list(c.get('characters') or o.get('characters')))}")
            out.append('')
            out.append(o.get('content_summary', ''))
            if c.get('scene'):
                out.append('')
                out.append(c['scene'])
            if c.get('available_actions'):
                out.append('')
                out.append('Actions: ' + '; '.join(str(a) for a in c['available_actions']))
            d = c.get('decision')
            if isinstance(d, dict):
                out.append('')
                out.append(f"Decision: {d.get('action', '')}")
                for oc in as_list(d.get('outcomes')):
                    if isinstance(oc, dict):
                        writes = ', '.join(f"{w['variable']}={w['value']}" for w in as_list(oc.get('writes')) if isinstance(w, dict))
                        out.append(f"  - {oc.get('choice', '')} -> {writes} ({oc.get('meaning', '')})")
            if c.get('shared_terminal_variants'):
                out.append('')
                out.append('Shared terminal variants: ' + json.dumps(c['shared_terminal_variants'], ensure_ascii=False))
            out.append('')
        out.append('## Iterations')
        for it in self.iterations:
            t = it.get('termination') or {}
            out.append(f"- iteration {it['iteration']} ({it['path_id']}): new beats {it['new_beat_ids']}, "
                       f"repaired {it['repaired_beat_ids']}; review says: {t.get('overall_recommendation', '')} "
                       f"- {t.get('reasoning', '')}")
        out.append('')
        out.append(f'Stop reason: {self.stop_reason}')
        if self.warnings:
            out.append('')
            out.append('Warnings:')
            for w in self.warnings:
                out.append(f'- {w}')
        return '\n'.join(out) + '\n'
