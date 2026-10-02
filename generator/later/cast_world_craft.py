"""LATER-STAGE MATERIAL (stages A and B). NOT RUN.

Lifted unchanged from generator/main.py as it stood on 2026-09-29, when
these steps ran before the story lines existed:

  3.75 craft spine   -> stage A (beat expansion): the devices are laid over
                        outline nodes instead of premise turns
  3.6  cast          -> stage B (character buildout): names, voice, stance,
                        moved_by, topics, per character, long form + packet
  3.7  world         -> stage B (setting buildout): rooms, fixtures,
                        connections, levers placed, per location

They moved because voice, topics, fixtures and connections are depth, and
depth is only worth paying for once the outline says which people and
places the story actually uses (docs/fable_response_4.md, section 5).

What is here, as methods of the old StoryGenerator (indentation kept so
they can be pasted back into a class):

  validate_craft_spine   shape check for the craft spine
  validate_cast          rejects a crowd without a representative
  validate_world         normalizes the room map (drops unknown
                         connections and names, makes connections mutual)
  run_verified_step      the generic build -> verify -> repair -> re-verify
                         loop the craft spine used (3.5 now has its own,
                         with computed checks and partial repair, in
                         main.py: run_premise_expansion)
  run_craft_spine, run_cast, run_world   the call sites, showing each
                         prompt's placeholders

Prompts: prompts/later/sA_craft_spine*.prompt, sB_cast.prompt,
sB_world.prompt. docs/later_stages.md says how each one's inputs change.
"""


class LaterStageMethods:
    def validate_craft_spine(self, parsed):
        if isinstance(parsed, dict) and parsed.get('status') == 'blocked':
            raise PipelineHalt(
                f"3.75 refused to build: {parsed.get('reason')} / {parsed.get('hard_findings_summary')}"
            )
        self.require_keys('invention_ceiling', 'want_need_tension', 'irony_mode',
                          'escalation_shape', 'setup_payoff_pairs')(parsed)


    @staticmethod
    def validate_cast(parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        chars = parsed.get('characters')
        if not isinstance(chars, list) or not chars:
            raise ValueError('characters must be a non-empty list')
        names = []
        for c in chars:
            if not isinstance(c, dict) or not c.get('name'):
                raise ValueError('each character needs a name')
            if c['name'] in names:
                raise ValueError(f'duplicate character name {c["name"]}')
            names.append(c['name'])
        crowds = parsed.get('crowds')
        if crowds is None:
            parsed['crowds'] = crowds = []
        if not isinstance(crowds, list):
            raise ValueError('crowds must be a list')
        for crowd in crowds:
            if not isinstance(crowd, dict):
                raise ValueError('each crowd must be an object')
            reps = [r for r in (crowd.get('representatives') or []) if r in names]
            if not reps:
                raise ValueError(f'crowd {crowd.get("name")} has no representative among the characters')
            crowd['representatives'] = reps
        parsed.setdefault('protagonist_name', None)


    def validate_world(self, parsed):
        """Rejects a map with no rooms or duplicate ids; normalizes the rest
        (drops unknown connections and names, makes connections mutual)."""
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        rooms = parsed.get('rooms')
        if not isinstance(rooms, list) or len(rooms) < 2:
            raise ValueError('rooms must be a list of at least two rooms')
        ids = []
        for r in rooms:
            if not isinstance(r, dict) or not r.get('id') or not r.get('name'):
                raise ValueError('each room needs an id and a name')
            if r['id'] in ids:
                raise ValueError(f'duplicate room id {r["id"]}')
            ids.append(r['id'])
        cast = self.analysis.get('s3_6_cast') or {}
        names = {c.get('name') for c in (cast.get('characters') or []) if isinstance(c, dict)}
        by_id = {r['id']: r for r in rooms}
        for r in rooms:
            conns = [c for c in (r.get('connections') or []) if isinstance(c, str) and c in by_id and c != r['id']]
            r['connections'] = conns
            r['usually_here'] = [n for n in (r.get('usually_here') or []) if n in names]
            r.setdefault('fixtures', [])
        for r in rooms:
            for c in r['connections']:
                if r['id'] not in by_id[c]['connections']:
                    by_id[c]['connections'].append(r['id'])
        parsed.setdefault('protagonist_presence', {})
        parsed.setdefault('levers_placed', [])


    def run_verified_step(self,
                          build_prefix, build_name, build_replacements,
                          verify_prefix, verify_name, verify_replacements,
                          repair_prefix, repair_name, repair_prompt_file, repair_replacements,
                          needs_repair, build_validator=None, verify_validator=None):
        """build -> verify, then up to self.max_repairs rounds of repair ->
        re-verify while needs_repair(verdict). The repair prompt returns
        {"repair_log", "revised"}; the revised object replaces the build
        output under the build's own key, so downstream reads the accepted
        version without knowing a repair happened.

        Files: <build>.json is the ORIGINAL; repairs <repair_prefix><n>_...;
        re-checks <verify_prefix>_r<n>_...; accepted copy <build>_accepted.json;
        <build_prefix>_loop.json records the rounds. Halts (PipelineHalt) if
        the last verdict still needs repair."""
        member = f'{build_prefix}_{build_name}'
        verify_member = f'{verify_prefix}_{verify_name}'
        verify_prompt_file = f'{verify_prefix}_{verify_name}.prompt'

        current = self.run_prompt(build_prefix, build_name, build_replacements,
                                  validator=build_validator)
        verdict = self.run_prompt(verify_prefix, verify_name, verify_replacements(current),
                                  validator=verify_validator)
        rounds = [{'round': 0, 'source': f'{build_prefix}_{build_name}.json',
                   'verdict': self._verdict_summary(verdict)}]

        def repair_validator(parsed):
            if not isinstance(parsed, dict) or 'revised' not in parsed:
                raise ValueError('repair output must carry a "revised" object')
            if not isinstance(parsed['revised'], dict):
                raise ValueError('"revised" must be an object')
            missing = [k for k in current.keys() if k not in parsed['revised']]
            if missing:
                raise ValueError(f'"revised" is missing top-level keys {missing}')
            if build_validator is not None:
                build_validator(parsed['revised'])

        n = 0
        while needs_repair(verdict) and n < self.max_repairs:
            n += 1
            repaired = self.run_prompt(f'{repair_prefix}{n}', repair_name,
                                       repair_replacements(current, verdict),
                                       prompt_file=repair_prompt_file,
                                       validator=repair_validator)
            current = repaired['revised']
            self.analysis[member] = current
            verdict = self.run_prompt(f'{verify_prefix}_r{n}', verify_name,
                                      verify_replacements(current),
                                      prompt_file=verify_prompt_file,
                                      validator=verify_validator)
            self.analysis[verify_member] = verdict
            rounds.append({'round': n,
                           'source': f'{repair_prefix}{n}_{repair_name}.json#revised',
                           'repair_log': repaired.get('repair_log', []),
                           'verdict': self._verdict_summary(verdict)})

        still_failing = needs_repair(verdict)
        loop = {
            'accepted_source': rounds[-1]['source'],
            'accepted_copy': f'{build_prefix}_{build_name}_accepted.json',
            'repair_rounds_used': n,
            'max_repairs': self.max_repairs,
            'still_failing': still_failing,
            'rounds': rounds,
        }
        self.save_story_json(f'{build_prefix}_{build_name}_accepted.json', current)
        self.save_story_json(f'{build_prefix}_loop.json', loop)
        if still_failing:
            raise PipelineHalt(
                f"{member}: verifier still reports a repair-worthy verdict after "
                f"{n} repair round(s). Inspect {self.story_file_path(build_prefix + '_loop.json')} "
                f"and the last {verify_member} output, fix the prompt or the material, then delete "
                f"the loop's files to re-run it."
            )
        return current, verdict


    def run_craft_spine(self):
        """3.75 build, 3.75v audit, 3.75r repair on a flagged verdict, re-audit."""
        base = {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_JSON$$': self.analysis_json('s3_brief'),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
        }

        def verify_repl(current):
            repl = dict(base)
            repl['$$CRAFT_SPINE_JSON$$'] = self.to_json(current)
            return repl

        def repair_repl(current, verdict):
            repl = dict(base)
            repl['$$CRAFT_SPINE_JSON$$'] = self.to_json(current)
            repl['$$CRAFT_SPINE_FIDELITY_JSON$$'] = self.to_json(verdict)
            return repl

        return self.run_verified_step(
            's3_75', 'craft_spine', base,
            's3_75v', 'fidelity_check', verify_repl,
            's3_75r', 'craft_spine_repair', 's3_75r_craft_spine_repair.prompt', repair_repl,
            needs_repair=self.craft_spine_needs_repair,
            build_validator=self.validate_craft_spine,
            verify_validator=self.require_keys('clause_findings', 'mechanic_findings', 'verdict'),
        )

    def budget(self):
        premise = self.analysis.get('s3_5_premise_expansion') or {}
        return str((premise.get('enrichment_budget') or {}).get('level', 'moderate'))

    def run_cast(self):
        """3.6: the named cast; every crowd gets a representative."""
        return self.run_prompt('s3_6', 'cast', {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_LITE_JSON$$': self.to_json(brief_lite(self.analysis.get('s3_brief'))),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }, validator=self.validate_cast)

    def run_world(self):
        """3.7: the room map, drawn once, with the premise's levers placed."""
        fields = ((self.analysis.get('s3_brief') or {}).get('fields') or {})
        setting_fields = {k: fields.get(k) for k in ('3f.setting_structure', '3f.setting_scale',
                                                       '3d.viewpoint_handoff', '3d.viewpoint_excursions',
                                                       '3e.timeline_structure', '3-0b.protagonist_identity')}
        return self.run_prompt('s3_7', 'world', {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_LITE_JSON$$': self.to_json(brief_lite(self.analysis.get('s3_brief'))),
            '$$SETTING_FIELDS_JSON$$': self.to_json(setting_fields),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
            '$$CAST_JSON$$': self.analysis_json('s3_6_cast'),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }, validator=self.validate_world)

