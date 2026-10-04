#!/usr/bin/python
"""Story generator for the stratum-if engine.

Reads a kernel on stdin and runs the pipeline:

  s1 kernel -> s2 rating filter + shape split (content kernel / shape prefs)
  -> phase 3 extraction (blind, nine steps) -> s3h cross-check
  -> constraint map + story brief (computed)
  -> s3.4 genre promises: what the Kernel's audience expects and the
     Kernel leaves open (thinking off; defaults the Kernel always beats)
  -> s3.5 premise: the dramatic engine, in three small builds
        3.5a engine (protagonist, pressure, opposition, events, mediation)
        3.5b turns  (the situations the story passes through)
        3.5c cast   (rough character sketches the turns need)
     then computed checks + 3.5v audit -> 3.5r repair -> re-audit
  -> s3.8 story form: a framework chosen from a computed shortlist
  -> step 4, the outline loop (generator/outline.py): the main line, then
     a branch plan (every divergence and its ending world designed
     together), then one divergent line per iteration, each laid over the
     framework's beats and filled at summary level; every check is computed
  -> s4e outline judge: one cheap scoring call over the finished outline

The product is a story graph: <id>_story.json and <id>_story.md.

Every model call is resumable: its output is saved under stories/<id>/ and
skipped on the next run if the file exists. Every attempt is recorded in
<id>_run_stats.json (see report.py). docs/outline_design.md describes the
pipeline; CLAUDE.md the file naming and how to re-run a step.
"""

import os
import sys
import time
import random
import re
import json
import argparse
import contextlib
from pathlib import Path

from llm_client import LlmCallError
from errors import SoftReject, PipelineHalt
from brief import (build_brief, brief_lines, constraint_fields, kernel_clauses,
                   valid_serves, ending_tier_from_stated, promises_lines, shape_targets)
from stats import RunStats, call_profile, sampler_for, step_of, SCHEMA_VERSION
import frameworks
import schemas
from outline import OutlineBuilder, compact_json, norm
from craft_checks import spine_findings
import evaluate
import arcs
import example_guard
import names

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(THIS_DIR, "..", "prompts")

# the phase-3 extraction steps, in the order they run, paired with the short
#  field id the later prompts (3h, the brief) refer to them by
STEP3_STEPS = [
    ('s3_0a_interactive_question', '3-0a'),
    ('s3_0b_identity_epistemic',   '3-0b'),
    ('s3_0c_consequence_failure_model', '3-0c'),
    ('s3b_affect',    '3b'),
    ('s3c_theme',     '3c'),
    ('s3d_viewpoint', '3d'),
    ('s3e_timeline',  '3e'),
    ('s3f_setting',   '3f'),
    ('s3g_complexity','3g'),
]

# how an evidence tier reads to the phases that CONSTRUCT rather than extract:
#  a constraint may not be contradicted, a default may be replaced with
#  something more specific, a free variable is theirs to fill.
EVIDENCE_CLASS = {
    'explicit':          'constraint',
    'strong_inference':  'constraint',
    'mixed':             'constraint',
    'genre_association': 'default',
    'no_signal':         'free',
}

# how much each tier constrains the construction phase's TEXTURE budget
CONSTRAINT_WEIGHT = {
    'explicit':         1.0,
    'mixed':            1.0,
    'strong_inference': 0.5,
    'genre_association': 0.0,
    'no_signal':        0.0,
}

BUDGET_RULE = ('weighted constraint_share (explicit 1.0, strong_inference 0.5) '
               '>= 0.5 -> minimal; >= 0.2 -> moderate; otherwise generous')

DEFAULT_RATING = 'UNRATED'
DEFAULT_MAX_REPAIRS = 2

PLACEHOLDER_RE = re.compile(r'\$\$[A-Z0-9_]+\$\$')

SHAPE_TIERS = {
    'endings': ('one', 'few', 'several', 'many', 'unstated'),
    'linearity': ('linear', 'branching', 'unstated'),
    'choice_density': ('sparse', 'moderate', 'dense', 'unstated'),
    'length': ('short', 'medium', 'long', 'unstated'),
}

TURN_FORMS = tuple(schemas.TURN_FORMS)      # one list, in schemas.py
# A complication is craft, not invention against the Kernel: even a tightly
# specified Kernel gets two (one of them a reversal).
COMPLICATION_BUDGET = {'minimal': 2, 'moderate': 3, 'generous': 4}
COMPLICATION_TEXT = {'minimal': 'exactly 2', 'moderate': '2 or 3', 'generous': '3 or 4'}
PREMISE_KEYS = ('protagonist', 'arena', 'pressure', 'opposition', 'events', 'hidden_truth', 'mediation', 'turns',
                'complications', 'cast_seeds')
EVENT_WHEN = ('early', 'middle', 'late')

# Files a story directory from before this schema would contain. Phase-3
# outputs (and step 2's) have not changed shape and may be kept.
STALE_FILE_RE = re.compile(r'_(s3_4_|s3_5_|s3_5v_|s3_5r\d|s3_6_|s3_7_|s3_75|s4a_|s4b_|s4c_|s4d_|s4p_|s4e_|s4_story)')
STAMP_FILE = 'pipeline.json'

RETRY_MARKER = '--- YOUR PREVIOUS ANSWER WAS REJECTED ---'


# A way through written as a menu pick: the question is not the verb.
MENU_VERB = re.compile(r"\byou (?:choose|chose|decide|decided|pick|picked|opt|opted|elect|elected)\b|"
                       r"\b(?:choose|decide|elect|opt) (?:to|whether|between)\b", re.I)




def get_client():
    """STRATUM_CLIENT=stub selects the model-free stub without needing a
    dynamic_config.py at all; otherwise the local dynamic_config decides."""
    if os.environ.get('STRATUM_CLIENT') == 'stub':
        from stub_client import StubClient
        return StubClient()
    import dynamic_config
    return dynamic_config.get_client()


class StoryGenerator:
    def __init__(self, story_id, max_repairs=DEFAULT_MAX_REPAIRS, no_think_steps=(), think_steps=(),
                 breakers=True, framework_override=None, force_answer=True, promises=True,
                 branching='plan', outline_judge=True):
        self.story_id = story_id
        self.max_repairs = max_repairs
        self.no_think_steps = set(no_think_steps or ())
        self.think_steps = set(think_steps or ())
        self.breakers = breakers
        self.force_answer = force_answer
        self.framework_override = framework_override
        self.promises_on = promises          # --no-promises skips 3.4; the prompts get "none"
        self.branching = branching           # 'plan' (4p designs every divergence) or 'judge' (4d, one seed per iteration)
        self.outline_judge = outline_judge   # --no-outline-judge skips 4e

        self.story_path_str = os.path.join(THIS_DIR, "..", "stories", self.story_id)
        self.story_path = Path(self.story_path_str)
        self.story_path.mkdir(parents=True, exist_ok=True)
        self.check_schema_stamp()

        self.kernel_full = None   # as the user wrote it
        self.kernel = None        # the content kernel every later step reads
        self.shape = {}           # step 2's shape preferences
        self.rating = DEFAULT_RATING
        self.analysis = dict()
        self.client = None
        self.stats = RunStats(self.story_file_path('run_stats.json'), self.story_id)

    # ------------------------------------------------------------------ files

    def story_file_path(self, file_suffix):
        return os.path.join(self.story_path_str, f'{self.story_id}_{file_suffix}')

    def load_story_file(self, file_suffix):
        value = ''
        path = Path(self.story_file_path(file_suffix))
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                value = f.read()
            if not value:
                raise ValueError(f"{path} exists, but not loaded with valid value")
        return value

    def save_story_file(self, file_suffix, value):
        path = Path(self.story_file_path(file_suffix))
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)

    def save_story_json(self, file_suffix, value):
        self.save_story_file(file_suffix, json.dumps(value, indent=2, ensure_ascii=False))

    def story_create_log(self, file_suffix):
        file_suffix = f"{file_suffix}_{int(time.time()*1000)}.log"
        return Path(self.story_file_path(file_suffix))

    def load_prompt(self, file_name):
        with open(os.path.join(PROMPT_DIR, file_name), encoding="utf-8") as f:
            value = f.read()
        if not value:
            raise ValueError(f"prompt {file_name} not found (or empty) in prompt directory {PROMPT_DIR}")
        return value

    def check_schema_stamp(self):
        """Every story directory is stamped with the schema version that
        wrote it. A directory stamped with another version, or an unstamped
        one that holds outputs of the steps this schema replaced, stops the
        run and names what to delete. Phase-3 outputs are unchanged across
        schemas, so an unstamped directory holding only those is adopted."""
        stamp_path = Path(self.story_file_path(STAMP_FILE))
        if stamp_path.is_file():
            try:
                stamp = json.loads(stamp_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                stamp = {}
            if stamp.get('schema_version') != SCHEMA_VERSION:
                raise PipelineHalt(
                    f"{self.story_path_str} was written by pipeline schema {stamp.get('schema_version')}; "
                    f"this pipeline is schema {SCHEMA_VERSION}. Delete the directory, or keep its phase-3 work "
                    f"and delete only what this schema replaced:\n"
                    f"  cd {self.story_path_str} && rm -f *_s3_4* *_s3_5* *_s3_6_* *_s3_7_* *_s3_75* *_s4* "
                    f"*_story.json *_story.md *_eval.json {stamp_path.name}"
                )
            return
        stale = sorted(p.name for p in self.story_path.iterdir() if STALE_FILE_RE.search(p.name))
        if stale:
            shown = ', '.join(stale[:6]) + (f', ... ({len(stale)} files)' if len(stale) > 6 else '')
            raise PipelineHalt(
                f"{self.story_path_str} holds outputs from an older pipeline schema ({shown}). "
                f"Delete the directory for a fresh run. To keep its phase-3 work (unchanged in this "
                f"schema), delete only the stale files:\n"
                f"  cd {self.story_path_str} && rm -f *_s3_4* *_s3_5* *_s3_6_* *_s3_7_* *_s3_75* *_s4*"
            )
        stamp_path.write_text(json.dumps({'schema_version': SCHEMA_VERSION,
                                          'created': time.strftime('%Y-%m-%dT%H:%M:%S')}, indent=2),
                              encoding='utf-8')

    # ------------------------------------------------------------------ json

    def lenient_json_loads(self, text):
        """Tries a straight parse first; on failure, strips markdown fences and
        any prose around the outermost object, then repairs the most common
        small-model slip-ups (smart quotes, trailing commas) and tries again."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        cleaned = text.strip()
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        cleaned = cleaned.replace("“", '"').replace("”", '"')
        cleaned = cleaned.replace("‘", "'").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(cleaned)

    @staticmethod
    def to_json(value, indent=2):
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    # ------------------------------------------------------------------ the model call

    def think_for(self, prefix, name, klass):
        """None (the model's default: thinking on) or False (off). The call
        class decides; --think-steps and --no-think-steps override it by
        prefix (s4a_i1), step (s4a) or step_name (s2_shape)."""
        step = step_of(prefix)
        keys = {prefix, step, f'{prefix}_{name}', f'{step}_{name}'}
        if keys & self.think_steps:
            return None
        if keys & self.no_think_steps:
            return False
        return call_profile(klass)['think']

    def limits_for(self, klass, think):
        profile = call_profile(klass)
        if not self.breakers:
            return {}
        limits = {
            'max_thinking_bytes': profile['limit_thinking_bytes'],
            'max_response_bytes': profile['limit_response_bytes'],
            'max_seconds': profile['limit_seconds'],
            'num_predict': profile['num_predict'],
            'detect_loops': True,
        }
        if think is not False and self.force_answer and profile.get('force_answer'):
            limits['force_answer'] = True
        if think is False and klass != 'classify' and limits.get('num_predict'):
            # the fallback run of a thinking call: only the answer is wanted
            limits['num_predict'] = 6000
        return {k: v for k, v in limits.items() if v}

    def run_prompt(self,
                   prefix,
                   name,
                   replacement_mapping,
                   is_json=True,
                   prompt_file=None,
                   validator=None,
                   retries=1,
                   klass='extract',
                   schema=None):
        """One resumable model call.

        prefix + name decide the output file (<id>_<prefix>_<name>.json) and
        the in-memory key (self.analysis['<prefix>_<name>']). The prompt file
        defaults to <prefix>_<name>.prompt. Returns the parsed output.

        klass picks the call's budget (stats.CALL_CLASSES): whether it
        thinks, what it should cost, and where the circuit breakers sit. A
        thinking call that trips a breaker is run once more with thinking
        off. schema is the JSON schema for structured output; the client
        decides whether the server can take it.

        validator(parsed) may raise ValueError to reject an answer. A
        rejected answer is retried up to `retries` times, and the retry is
        told what was wrong and shown its previous answer. A saved output
        that fails the validator is reported as stale (the schema changed
        under it) and named, so the file can be deleted."""
        output_file_name = f'{prefix}_{name}.{"json" if is_json else "txt"}'
        output_member_name = f'{prefix}_{name}'
        prompt_file_name = prompt_file or f'{prefix}_{name}.prompt'
        print(f'out: {output_file_name}')
        val = self.load_story_file(output_file_name)
        if val:
            parsed = self.lenient_json_loads(val) if is_json else val
            if validator is not None and is_json:
                try:
                    validator(parsed)
                except SoftReject:
                    pass
                except (ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
                    raise ValueError(
                        f"{self.story_file_path(output_file_name)} no longer matches the schema this "
                        f"pipeline expects ({e}). Delete it (and everything downstream of it) to re-run."
                    )
            self.analysis[output_member_name] = parsed
            return parsed

        prompt = self.load_prompt(prompt_file_name)
        for k, v in replacement_mapping.items():
            if v is None:
                v = 'none'
            prompt = prompt.replace(k, v)
        leftover = sorted(set(PLACEHOLDER_RE.findall(prompt)))
        if leftover:
            raise ValueError(f"{prompt_file_name}: unfilled placeholders {leftover} for {output_member_name}")

        if self.client is None:
            self.client = get_client()
        profile = call_profile(klass)
        think = self.think_for(prefix, name, klass)

        last_error = None
        feedback = ''
        fallback_used = False
        loop_seed = None        # set after a loop: the retry samples from a new seed
        attempts_left = retries + 1
        attempt = 0
        while attempts_left > 0:
            attempts_left -= 1
            attempt += 1
            mode = 'no_think' if think is False else 'think'
            kwargs = {'options': sampler_for(think), 'limits': self.limits_for(klass, think)}
            if loop_seed is not None:
                kwargs['options'] = dict(kwargs['options'], seed=loop_seed)
            if think is False:
                kwargs['think'] = False
            if schema is not None and is_json:
                kwargs['format'] = schema
            full_prompt = prompt + feedback
            rec = {'prefix': prefix, 'name': name, 'step': step_of(prefix), 'klass': klass, 'mode': mode,
                   'attempt': attempt, 'prompt_file': prompt_file_name, 'prompt_chars': len(full_prompt),
                   'ok': False, 'breaker': None, 'error': None}
            if loop_seed is not None:
                rec['seed'] = loop_seed
            # what was actually sent, beside the trace it produced
            self.save_story_file(f'{prefix}_raw_input_prompt.txt', full_prompt)
            log_path = self.story_create_log(prefix)
            started = time.time()
            stamp = int(started * 1000)     # names this attempt's partial trace if it is cut
            thinking, response, call_error = '', '', None
            if hasattr(self.client, 'last_call'):
                self.client.last_call = {}
            with open(log_path, "w", encoding="utf-8") as f:
                with contextlib.redirect_stdout(f):
                    try:
                        (thinking, response) = self.client.run_prompt(full_prompt, **kwargs)
                    except LlmCallError as e:
                        thinking, response, call_error = e.thinking, e.response, e
            info = getattr(self.client, 'last_call', None) or {}
            thinking, response = thinking or '', response or ''
            rec.update({
                'seconds': round(time.time() - started, 2),
                'thinking_bytes': len(thinking.encode('utf-8')),
                'response_bytes': len(response.encode('utf-8')),
                'done_reason': info.get('done_reason'),
                'prompt_tokens': info.get('prompt_tokens'),
                'output_tokens': info.get('output_tokens'),
                'format_sent': info.get('format_sent'),
            })
            if info.get('forced_answer'):
                rec['forced_answer'] = True
                rec['thinking_at_force'] = info.get('thinking_at_force')
            breaker = info.get('aborted') or ('num_predict' if info.get('done_reason') == 'length' else None)

            if call_error is not None:
                # keep what streamed before the failure, then stop: a
                # transport failure is not something a retry in this
                # process is likely to fix
                self.save_story_file(f'{prefix}_raw_output_thinking_cut_{stamp}.txt', thinking)
                self.save_story_file(f'{prefix}_raw_output_response_cut_{stamp}.txt', response)
                rec['error'] = str(call_error)
                self.stats.record(**rec)
                raise call_error

            if breaker:
                rec['breaker'] = breaker
                rec['error'] = f'cut off by the {breaker} circuit breaker'
                if info.get('loop_line'):
                    rec['loop_line'] = info['loop_line'][:200]
                self.stats.record(**rec)
                cut_name = f'{prefix}_raw_output_thinking_cut_{stamp}.txt'
                self.save_story_file(cut_name, thinking)
                self.save_story_file(f'{prefix}_raw_output_response_cut_{stamp}.txt', response)
                print(f'  attempt {attempt} for {output_member_name}: {rec["error"]} '
                      f'({rec["thinking_bytes"]} thinking bytes, {rec["seconds"]:.0f}s)')
                if breaker == 'loop' and loop_seed is None:
                    # a loop is the sampler's bad luck more than the prompt's:
                    # the same call from another seed usually runs clean, and
                    # keeps its thinking. A second loop falls through to the
                    # class's fallback below.
                    loop_seed = random.randrange(1, 2 ** 31)
                    print(f'  re-running {output_member_name} from seed {loop_seed}')
                    attempts_left += 1
                    continue
                if (breaker != 'max_duration' and think is not False
                        and profile.get('fallback') == 'no_think' and not fallback_used):
                    print(f'  re-running {output_member_name} with thinking off')
                    fallback_used = True
                    think = False
                    attempts_left += 1
                    continue
                # Nothing different to try: the same call would be cut the
                # same way. Stop here rather than spend the time twice.
                hint = ("the client's own max_duration; raise it in dynamic_config.py"
                        if breaker == 'max_duration' else
                        "its class limit in generator/stats.py; see the partial trace, or run with --no-breakers")
                raise ValueError(
                    f"{output_member_name}: {rec['error']} with nothing left to fall back to ({hint}). "
                    f"Partial trace: {self.story_file_path(cut_name)}"
                )

            self.save_story_file(f'{prefix}_raw_output_thinking.txt', thinking)
            self.save_story_file(f'{prefix}_raw_output_response.txt', response)
            try:
                if is_json:
                    parsed = self.lenient_json_loads(response)
                    if validator is not None:
                        validator(parsed)
                else:
                    parsed = response
                    if not parsed.strip():
                        raise ValueError('the response was empty')
            except SoftReject as e:
                if attempts_left > 0:
                    last_error = e
                    rec['error'] = str(e)
                    self.keep_rejected(prefix, attempt, thinking, response)
                    self.stats.record(**rec)
                    print(f'  attempt {attempt} for {output_member_name} rejected: {e}')
                    feedback = self.retry_feedback(e, response)
                    continue
                rec['soft_problems'] = str(e)
                print(f'  attempt {attempt} for {output_member_name} accepted with problems left to the next check: {e}')
            except (json.JSONDecodeError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
                last_error = e
                rec['error'] = str(e)
                self.keep_rejected(prefix, attempt, thinking, response)
                self.stats.record(**rec)
                print(f'  attempt {attempt} for {output_member_name} rejected: {e}')
                feedback = self.retry_feedback(e, response)
                continue
            rec['ok'] = True
            self.stats.record(**rec)
            self.analysis[output_member_name] = parsed
            if is_json:
                self.save_story_json(output_file_name, parsed)
            else:
                self.save_story_file(output_file_name, parsed)
            return parsed

        raise ValueError(
            f"{output_member_name}: model output failed validation after "
            f"{attempt} attempts (last error: {last_error}); see "
            f"{self.story_file_path(prefix + '_raw_output_response.txt')}"
        )

    def keep_rejected(self, prefix, attempt, thinking, response):
        """A rejected attempt's output is kept beside the accepted one (the
        retry overwrites the plain raw_output files), so a retry can be
        examined afterwards: what the model wrote, and what the check said."""
        self.save_story_file(f'{prefix}_raw_output_thinking_rejected_{attempt}.txt', thinking)
        self.save_story_file(f'{prefix}_raw_output_response_rejected_{attempt}.txt', response)

    @staticmethod
    def retry_feedback(error, response):
        """What a retry is told: the computed check's complaint and its own
        previous answer, with the instruction to change only what is named.
        Repair receives the violation list; it is never a blind re-roll."""
        problem = ('it was not valid JSON (' + str(error) + ')') if isinstance(error, json.JSONDecodeError) else str(error)
        previous = (response or '').strip()
        if len(previous) > 12000:
            previous = previous[:12000] + '\n... (truncated)'
        return (f"\n\n{RETRY_MARKER}\nA computed check found this wrong with it:\n - {problem}\n"
                f"Return the whole JSON again with only that fixed. Keep everything else exactly as it was.\n"
                f"Your previous answer:\n{previous}\n")

    # ------------------------------------------------------------------ s1 / s2

    def s1_take_kernel(self, kernel):
        self.kernel_full = self.load_story_file('s1_kernel.txt')
        if not self.kernel_full:
            self.kernel_full = kernel
            if not self.kernel_full:
                raise ValueError("could not find kernel (check stdin)")
            self.save_story_file('s1_kernel.txt', self.kernel_full)
        self.kernel = self.kernel_full

    def s2_apply_rating(self, rating=DEFAULT_RATING):
        """Content-rating filter over the kernel, when a rating is given."""
        saved = self.load_story_file('s2_rating.txt')
        if saved:
            self.rating = saved
        else:
            self.rating = rating or DEFAULT_RATING
            # recorded first, so a run interrupted during the filter does
            # not resume as an unrated story
            self.save_story_file('s2_rating.txt', self.rating)
        if self.rating != 'UNRATED':
            rated = self.run_prompt('s2', 'rated_kernel', {
                '$$KERNEL$$': self.kernel_full,
                '$$TARGET_RATING$$': self.rating,
            }, is_json=False, prompt_file='s2_filter.prompt')
            self.kernel = rated.strip()
        else:
            self.kernel = self.kernel_full

    def validate_shape(self, parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        content = parsed.get('content_kernel')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('content_kernel must be a non-empty string')
        if len(content) > len(self.kernel) * 1.15 + 40:
            raise ValueError('content_kernel is longer than the kernel; it may only remove shape clauses')
        shape = parsed.get('shape')
        if not isinstance(shape, dict):
            raise ValueError('shape must be an object')
        endings = shape.get('endings')
        if not isinstance(endings, dict):
            shape['endings'] = endings = {'tier': 'unstated', 'stated': ''}
        for key, allowed in SHAPE_TIERS.items():
            value = endings.get('tier') if key == 'endings' else shape.get(key)
            value = str(value or 'unstated').lower().strip()
            if value not in allowed:
                value = 'unstated'
            if key == 'endings':
                endings['tier'] = value
            else:
                shape[key] = value
        # a stated number decides the tier by lookup, whatever the model said
        computed = ending_tier_from_stated(endings.get('stated'))
        if computed:
            endings['tier'] = computed
        shape.setdefault('removed_clauses', [])

    def s2_split_shape(self):
        """Separate the kernel's shape preferences (ending count, branchiness,
        length) from its content. Every later step reads the content kernel;
        the shape reaches only step 4 as a soft target."""
        rated = self.kernel
        parsed = self.run_prompt('s2', 'shape', {'$$KERNEL$$': rated},
                                 prompt_file='s2_shape_split.prompt', validator=self.validate_shape,
                                 klass='classify', schema=schemas.SHAPE)
        self.shape = parsed['shape']
        self.kernel = parsed['content_kernel'].strip()
        self.save_story_file('s2_kernel.txt', self.kernel)

    # ------------------------------------------------------------------ phase 3 helpers

    def step3_bundle(self):
        bundle = dict()
        for member_name, field_id in STEP3_STEPS:
            if member_name in self.analysis:
                bundle[field_id] = self.analysis[member_name]
        return bundle

    def step3_bundle_json(self):
        return json.dumps(self.step3_bundle(), indent=2, ensure_ascii=False)

    def build_constraint_map(self):
        """Walk every scored judgment in the phase-3 bundle and sort it by
        evidence tier into constraint / default / free, then derive 3.5's
        texture budget from the mix. Computed, not asked."""
        fields = dict()

        def walk(node, path):
            if isinstance(node, dict):
                basis = node.get('evidence_basis')
                if isinstance(basis, str):
                    fields[path] = {
                        'evidence_basis': basis,
                        'class': EVIDENCE_CLASS.get(basis, 'default'),
                    }
                for key, value in node.items():
                    if key in ('evidence_basis', 'note'):
                        continue
                    if isinstance(value, (dict, list)):
                        walk(value, f'{path}.{key}' if path else key)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    if isinstance(item, (dict, list)):
                        walk(item, f'{path}[{index}]')

        for member_name, field_id in STEP3_STEPS:
            if member_name in self.analysis:
                walk(self.analysis[member_name], field_id)

        counts = dict()
        for entry in fields.values():
            counts[entry['evidence_basis']] = counts.get(entry['evidence_basis'], 0) + 1
        total = len(fields)
        constraints = sum(1 for e in fields.values() if e['class'] == 'constraint')
        weighted = sum(CONSTRAINT_WEIGHT.get(e['evidence_basis'], 0.0) for e in fields.values())
        share = (weighted / total) if total else 0.0
        if share >= 0.5:
            budget = 'minimal'
        elif share >= 0.2:
            budget = 'moderate'
        else:
            budget = 'generous'

        constraint_map = {
            'fields': fields,
            'counts': counts,
            'total_scored_judgments': total,
            'constraint_count': constraints,
            'constraint_share': round(share, 3),
            'suggested_budget': budget,
            'budget_rule': BUDGET_RULE,
        }
        self.analysis['s3h_constraint_map'] = constraint_map
        self.save_story_json('s3h_constraint_map.json', constraint_map)
        return constraint_map

    def build_story_brief(self):
        """The compact digest every later prompt reads instead of the bundle:
        each field's value and binding class, the cross-check's resolutions,
        the budget. Recomputed every run."""
        brief = build_brief(self.step3_bundle(), self.analysis.get('s3h_constraint_map'),
                            self.analysis.get('s3h_cross_check'))
        self.analysis['s3_brief'] = brief
        self.save_story_json('s3_brief.json', brief)
        return brief

    def budget(self):
        return str((self.analysis.get('s3_brief') or {}).get('enrichment_budget') or 'moderate')

    # ------------------------------------------------------------------ validators

    @staticmethod
    def validate_engine(parsed):
        problems = []
        if not isinstance(parsed, dict):
            raise ValueError('expected a JSON object')
        need = {
            'protagonist': ('who', 'wants', 'can_do', 'cannot_do'),
            'arena': ('description',),
            'pressure': ('description',),
            'opposition': ('who_or_what', 'wants', 'means'),
            'mediation': ('question', 'to_reach_pole_a', 'to_reach_pole_b', 'levers'),
        }
        for key, subkeys in need.items():
            block = parsed.get(key)
            if not isinstance(block, dict):
                problems.append(f'{key} must be an object')
                continue
            for sk in subkeys:
                if block.get(sk) in (None, '', [], {}):
                    problems.append(f'{key}.{sk} is missing or empty')
        events = parsed.get('events')
        events = events if isinstance(events, list) else ([events] if isinstance(events, dict) else [])
        clean = []
        for e in events:
            if isinstance(e, dict) and str(e.get('what') or '').strip():
                when = str(e.get('when') or '').strip().lower()
                e['when'] = when if when in EVENT_WHEN else 'middle'
                clean.append(e)
        parsed['events'] = clean
        hidden = parsed.get('hidden_truth')
        if hidden in ('', {}, [], 'null', 'none'):
            parsed['hidden_truth'] = hidden = None
        if hidden is not None and not (isinstance(hidden, dict) and str(hidden.get('truth') or '').strip()):
            problems.append('hidden_truth must be null or an object whose "truth" states the truth itself')
        med = parsed.get('mediation') if isinstance(parsed.get('mediation'), dict) else {}
        for pole in ('to_reach_pole_a', 'to_reach_pole_b'):
            p = med.get(pole)
            if isinstance(p, dict):
                for sk in ('pole', 'what_you_must_do', 'cost'):
                    if not p.get(sk):
                        problems.append(f'mediation.{pole}.{sk} is missing or empty')
            elif p not in (None, '', [], {}):
                problems.append(f'mediation.{pole} must be an object with pole, what_you_must_do and cost')
        if isinstance(med.get('levers'), str):
            med['levers'] = [med['levers']]
        if problems:
            raise ValueError('; '.join(problems))

    @staticmethod
    def validate_turns(parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected a JSON object')
        turns = parsed.get('turns')
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError('turns must be a list of at least two turns')
        problems = []
        for i, t in enumerate(turns):
            if not isinstance(t, dict):
                raise ValueError('each turn must be an object')
            t['id'] = i + 1
            for k in ('situation', 'what_you_must_do'):
                if not t.get(k):
                    problems.append(f'turn {i + 1}: {k} is missing')
            ways = t.get('ways_through')
            if not isinstance(ways, list) or not all(isinstance(w, dict) and w.get('way') for w in ways):
                problems.append(f'turn {i + 1}: ways_through must be a list of {{"way", "cost"}} objects')
            involves = t.get('involves')
            involves = involves if isinstance(involves, list) else ([involves] if involves else [])
            t['involves'] = [str(r).strip() for r in involves if str(r).strip()]
            t['form'] = str(t.get('form') or '').strip().lower()
            sp = t.get('set_piece')
            t['set_piece'] = str(sp).strip() if isinstance(sp, str) and sp.strip().lower() not in ('', 'null', 'none') else None
        if not isinstance(parsed.get('complications'), list):
            parsed['complications'] = []
        if problems:
            raise ValueError('; '.join(problems))

    def with_echo_check(self, validator, keys):
        """Wraps a construction validator with the brief-echo check: a
        phrase of five or more words copied from the brief's own field text
        into the named sections ("the sword's stated desire to be returned",
        used as a lever and then in every node) is a SoftReject: re-asked
        once with the complaint, accepted if it comes back the same."""
        brief = self.analysis.get('s3_brief')

        def validate(parsed):
            validator(parsed)
            echoes = example_guard.brief_echoes({k: parsed.get(k) for k in keys if isinstance(parsed, dict)}, brief)
            if echoes:
                raise SoftReject('these phrases are the brief\'s own wording copied in as if they were things in the '
                                 'story: ' + '; '.join(f'"{e}"' for e in echoes[:4]) + '. Name each thing in the '
                                 'story\'s own words (what it is, what it does when used), everywhere it appears')
        return validate

    def cast_validator(self, turns):
        """Rejects a cast that leaves a role the turns name without a
        sketch, or a crowd without an individual who speaks for it."""
        wanted = {}
        for t in turns:
            for r in t.get('involves') or []:
                wanted.setdefault(norm(r), r)

        def validate(parsed):
            if not isinstance(parsed, dict) or not isinstance(parsed.get('cast_seeds'), list):
                raise ValueError('cast_seeds must be a list')
            seeds = parsed['cast_seeds']
            self.canonical_cast(seeds, wanted)
            roles = [norm(s['role']) for s in seeds]
            problems = []
            missing = [r for k, r in wanted.items() if k not in roles]
            if missing:
                problems.append(f'the turns involve {missing} but no cast seed has that role')
            for s in seeds:
                if s['kind'] == 'crowd':
                    reps = [o for o in seeds if o['kind'] == 'individual'
                            and norm(o.get('speaks_for')) == norm(s['role'])]
                    if not reps:
                        problems.append(f'crowd "{s["role"]}" has no individual seed whose speaks_for names it')
            if problems:
                raise ValueError('; '.join(problems))
        return validate

    @staticmethod
    def canonical_cast(seeds, wanted):
        """Normalizes cast seeds in place. "mill foreman" for "the mill
        foreman" is the same role, and the turns' spelling (`wanted`:
        normalized role -> the spelling to use) is the one everything
        downstream compares against; speaks_for is rewritten to the exact
        role it names. Raises ValueError on a seed without a role or a role
        given twice."""
        roles = []
        for s in seeds:
            if not isinstance(s, dict) or not str(s.get('role') or '').strip():
                raise ValueError('each cast seed needs a role')
            s['role'] = wanted.get(norm(s['role']), str(s['role']).strip())
            s['kind'] = 'crowd' if str(s.get('kind') or '').strip().lower() == 'crowd' else 'individual'
            s['speaks_for'] = str(s['speaks_for']).strip() if isinstance(s.get('speaks_for'), str) and s['speaks_for'].strip().lower() not in ('', 'null', 'none') else None
            for key in ('voice', 'breaking_point'):
                v = s.get(key)
                s[key] = str(v).strip() if isinstance(v, str) and v.strip().lower() not in ('', 'null', 'none') else None
            s['opposition'] = as_bool(s.get('opposition'))
            if norm(s['role']) in roles:
                raise ValueError(f'duplicate role {s["role"]}')
            roles.append(norm(s['role']))
        by_norm = {norm(s['role']): s['role'] for s in seeds}
        for s in seeds:
            if s['speaks_for']:
                s['speaks_for'] = by_norm.get(norm(s['speaks_for']), s['speaks_for'])

    @staticmethod
    def assemble_premise(budget, engine, turns, cast):
        """The premise downstream reads: the three builds side by side, with
        each seed's matters_to_turns looked up from the turns."""
        premise = {'enrichment_budget': {'level': budget}}
        for key in ('protagonist', 'arena', 'pressure', 'opposition', 'events', 'hidden_truth', 'mediation'):
            premise[key] = engine.get(key)
        premise['events'] = premise.get('events') or []
        premise['turns'] = turns.get('turns')
        premise['complications'] = turns.get('complications') or []
        premise['cast_seeds'] = cast.get('cast_seeds') or []
        StoryGenerator.index_cast(premise)
        return premise

    @staticmethod
    def index_cast(premise):
        for s in premise.get('cast_seeds') or []:
            if isinstance(s, dict):
                s['matters_to_turns'] = [t.get('id') for t in premise.get('turns') or []
                                         if isinstance(t, dict)
                                         and norm(s.get('role')) in [norm(r) for r in t.get('involves') or []]]

    # ------------------------------------------------------------------ the pipeline

    def run_phase3(self):
        replace_kernel_only = {'$$KERNEL$$': self.kernel}
        self.run_prompt('s3_0a', 'interactive_question', replace_kernel_only)
        self.run_prompt('s3_0b', 'identity_epistemic', replace_kernel_only)
        self.run_prompt('s3_0c', 'consequence_failure_model', replace_kernel_only)
        self.run_prompt('s3b', 'affect', replace_kernel_only)
        self.run_prompt('s3c', 'theme', replace_kernel_only)
        self.run_prompt('s3d', 'viewpoint', replace_kernel_only)
        self.run_prompt('s3e', 'timeline', replace_kernel_only)
        self.run_prompt('s3f', 'setting', {
            '$$VIEWPOINT_EXCURSIONS_JSON$$': self.to_json(self.analysis.get('s3d_viewpoint')),
            '$$KERNEL$$': self.kernel
        })
        # 3g is chained, not blind: branching density and tracked state aren't
        #  well-defined without the decision (3-0a) and the failure model (3-0c).
        self.run_prompt('s3g', 'complexity', {
            '$$INTERACTIVE_QUESTION_JSON$$': self.to_json(self.analysis.get('s3_0a_interactive_question')),
            '$$FAILURE_MODEL_JSON$$': self.to_json(self.analysis.get('s3_0c_consequence_failure_model')),
            '$$KERNEL$$': self.kernel
        })
        # 3h: the phase's own cross-check. Classification only; fixes nothing.
        self.run_prompt('s3h', 'cross_check', {
            '$$STEP3_BUNDLE_JSON$$': self.step3_bundle_json(),
            '$$KERNEL$$': self.kernel
        })
        self.build_constraint_map()
        self.build_story_brief()

    # ------------------------------------------------------------------ 3.4: genre promises

    @staticmethod
    def validate_promises(parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected a JSON object')
        for key in ('promises', 'set_pieces', 'obligatory_cast', 'must_not'):
            v = parsed.get(key)
            parsed[key] = v if isinstance(v, list) else ([] if v in (None, '', 'none') else [v])
        parsed['promises'] = [p for p in parsed['promises'] if isinstance(p, dict) and str(p.get('what') or '').strip()]
        parsed['set_pieces'] = [p for p in parsed['set_pieces'] if isinstance(p, dict) and str(p.get('scene') or '').strip()]
        parsed['obligatory_cast'] = [str(c).strip() for c in parsed['obligatory_cast'] if str(c or '').strip()]
        parsed['must_not'] = [str(c).strip() for c in parsed['must_not'] if str(c or '').strip()]
        for p in parsed['promises']:
            p['in_kernel'] = as_bool(p.get('in_kernel'))
        if not parsed['promises'] and not parsed['set_pieces']:
            raise ValueError('promises and set_pieces are both empty; every genre owes its audience something')
        if len(parsed['obligatory_cast']) > 3:
            parsed['obligatory_cast'] = parsed['obligatory_cast'][:3]

    def run_promises(self):
        """3.4: what the Kernel's audience expects that the Kernel leaves
        open (set pieces, the tone engine, obligatory cast, what the Kernel
        rules out). Thinking off. The output reaches 3.5a/b and the line
        plans as DEFAULTS; nothing checks the premise against it, so a
        promise can never outrank the Kernel or a brief constraint.
        Skipped with --no-promises, and the prompts get "none"."""
        if not self.promises_on:
            self.analysis['s3_4_promises'] = None
            return None
        return self.run_prompt('s3_4', 'promises', {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_LINES$$': brief_lines(self.analysis.get('s3_brief'),
                                           only=('3b.', '3c.', '3-0c.', '3f.', '3-0a.primary', '3-0b.')),
        }, validator=self.validate_promises, klass='classify', schema=schemas.PROMISES)

    def promises_block(self):
        return promises_lines(self.analysis.get('s3_4_promises'))

    # ------------------------------------------------------------------ 3.5: build

    def build_premise(self):
        """3.5a engine, 3.5b turns, 3.5c cast: three small constructions in
        the order the old single prompt asked the model to think in."""
        brief = self.analysis.get('s3_brief')
        table = brief_lines(brief)
        budget = self.budget()
        engine = self.run_prompt('s3_5a', 'engine', {
            '$$BRIEF_LINES$$': table,
            '$$PROMISES$$': self.promises_block(),
            '$$ENRICHMENT_BUDGET$$': budget,
            '$$KERNEL$$': self.kernel,
        }, validator=self.with_echo_check(self.validate_engine, ('mediation', 'pressure', 'opposition', 'events')),
            klass='build', schema=schemas.ENGINE)
        turns = self.run_prompt('s3_5b', 'turns', {
            '$$BRIEF_LINES$$': table,
            '$$PROMISES$$': self.promises_block(),
            '$$ENRICHMENT_BUDGET$$': budget,
            '$$COMPLICATION_COUNT$$': COMPLICATION_TEXT.get(budget, '2 or 3'),
            '$$ENGINE_JSON$$': self.to_json(engine),
            '$$KERNEL$$': self.kernel,
        }, validator=self.with_echo_check(self.validate_turns, ('turns',)), klass='build', schema=schemas.TURNS)
        roles = []
        for t in turns['turns']:
            for r in t.get('involves') or []:
                if r not in roles:
                    roles.append(r)
        cast = self.run_prompt('s3_5c', 'cast', {
            '$$ENGINE_JSON$$': self.to_json({k: engine.get(k) for k in ('protagonist', 'opposition', 'hidden_truth', 'mediation')}),
            '$$TONE$$': self.tone_line(),
            '$$TURNS_JSON$$': compact_json({'turns': [{'id': t['id'], 'situation': t.get('situation'),
                                                       'involves': t.get('involves')} for t in turns['turns']]}),
            '$$ROLES$$': '\n'.join(f' - {r}' for r in roles) or ' (the turns name nobody)',
            '$$KERNEL$$': self.kernel,
        }, validator=self.cast_validator(turns['turns']), klass='classify', schema=schemas.CAST)
        return self.name_cast(self.assemble_premise(budget, engine, turns, cast))

    def name_cast(self, premise):
        """Names for the cast come from Python (generator/names.py), not the
        model: the role stays the key, the name rides along. Keeps any name a
        seed already has, so a repair that adds a seed names only that one."""
        texts = [self.kernel or ''] + names.premise_texts(premise)
        pool = premise.get('name_pool') or names.with_culture(names.pool_for(*texts), self.story_id, texts)
        identity = ((self.analysis.get('s3_brief') or {}).get('fields') or {}).get('3-0b.protagonist_identity') or {}
        human = str(identity.get('type') or 'human').lower() == 'human'
        you = names.name_protagonist(premise.get('protagonist'), self.story_id, pool, human)
        premise['name_pool'] = names.assign_names(premise.get('cast_seeds') or [], self.story_id, texts, pool,
                                                  reserved=[you] if you else [])
        return premise

    def tone_line(self):
        """The brief's tone and affect in one line, for the calls that need
        only that (the cast sketch, the outline judge)."""
        f = (self.analysis.get('s3_brief') or {}).get('fields') or {}
        tone = ', '.join(str(t) for t in ((f.get('3b.tone') or {}).get('descriptors') or []) if t)
        affect = (f.get('3b.primary_affect') or {}).get('label') or ''
        engine = (self.analysis.get('s3_4_promises') or {}).get('tone_engine') or ''
        return (f"tone: {tone or '(none stated)'}; affect: {affect or '(none)'}"
                + (f"; how the tone is produced: {engine}" if engine else ''))

    # ------------------------------------------------------------------ 3.5: verify

    def premise_computed_findings(self, premise):
        """The half of the old 3.5v audit that is a lookup or a count."""
        brief = self.analysis.get('s3_brief')
        out = []

        def add(where, problem, quote=''):
            out.append({'source': 'computed', 'where': where, 'problem': problem, 'quote': quote})

        events = [e for e in premise.get('events') or [] if isinstance(e, dict) and str(e.get('what') or '').strip()]
        if not events:
            add('events', 'the engine names no event: two or three things the opposition or the pressure brings about '
                          'on their own schedule, whatever "you" do (each a picturable happening, with when it lands)')
        elif len(events) > 4:
            add('events', f'{len(events)} events; the engine names two or three', str(events[4].get('what')))
        promises = self.analysis.get('s3_4_promises')
        turns_all = [t for t in premise.get('turns') or [] if isinstance(t, dict)]
        if isinstance(promises, dict) and promises.get('set_pieces') and turns_all \
                and not any(t.get('set_piece') for t in turns_all):
            add('turns.set_piece', 'no turn names the set piece it delivers; at least one turn is a scene the genre\'s '
                                   'audience came for (one of the listed set pieces, or one of your own), with the world '
                                   'acting, and says so in set_piece')

        prot = premise.get('protagonist') or {}
        cannot = str(prot.get('cannot_do') or '').strip()
        if not cannot or cannot.lower() in ('nothing', 'none', 'n/a'):
            add('protagonist.cannot_do', 'cannot_do names no limit; the obstacle has nowhere to live', cannot)
        elif cannot.lower() == str(prot.get('can_do') or '').strip().lower():
            add('protagonist.cannot_do', 'cannot_do restates can_do', cannot)
        copied = example_guard.copied_phrases(
            premise, ['s3_5a_engine.prompt', 's3_5b_turns.prompt', 's3_5c_cast.prompt'],
            [self.kernel or '', json.dumps(brief or {})])
        if len(copied) >= example_guard.MIN_HITS:
            add('premise', f"the premise copies the prompts' calibration example ({len(copied)} of its phrases); "
                           f"rebuild every section copied from it from this Kernel", '; '.join(copied[:6]))
        gap = ((brief or {}).get('fields') or {}).get('3-0b.epistemic_gap') or {}
        hidden = premise.get('hidden_truth')
        if gap.get('present') is True and not (isinstance(hidden, dict) and str(hidden.get('truth') or '').strip()):
            add('hidden_truth', f'the brief has an epistemic gap ({gap.get("description") or "unnamed"}) but the premise '
                                'states no hidden truth; say what the truth IS, who knows it, and what it changes')
        elif gap.get('present') is False and gap.get('binding') == 'constraint' and isinstance(hidden, dict) and hidden.get('truth'):
            add('hidden_truth', 'the brief rules out a hidden truth (3-0b.epistemic_gap present false), but the premise '
                                'builds one; set hidden_truth to null', str(hidden.get('truth')))
        turns = [t for t in premise.get('turns') or [] if isinstance(t, dict)]
        if len(turns) < 3:
            add('turns', f'there are {len(turns)} turns; a story needs at least 3')
        if len(turns) > 5:
            add('turns', f'there are {len(turns)} turns; the limit is 5')
        seen = {}
        for t in turns:
            form = t.get('form')
            if form not in TURN_FORMS:
                add(f"turns[{t.get('id')}].form", f'"{form}" is not one of the forms: {", ".join(TURN_FORMS)}', str(form))
            elif form in seen:
                add(f"turns[{t.get('id')}].form", f'turns {seen[form]} and {t.get("id")} share the form "{form}"; no two turns may', form)
            else:
                seen[form] = t.get('id')
            ways = [w for w in t.get('ways_through') or [] if isinstance(w, dict)]
            if len(ways) < 2:
                add(f"turns[{t.get('id')}].ways_through", 'a turn needs at least two ways through')
            for w in ways:
                if not str(w.get('cost') or '').strip():
                    add(f"turns[{t.get('id')}].ways_through", 'a way through has no cost', str(w.get('way')))
                if MENU_VERB.search(str(w.get('way') or '')):
                    add(f"turns[{t.get('id')}].ways_through",
                        'a way through is written as a pick ("you choose to ..."); say what you did and what it '
                        'brought about, as the other ways do', str(w.get('way')))
        for key in ('protagonist', 'arena', 'pressure', 'opposition', 'mediation'):
            tag = (premise.get(key) or {}).get('serves')
            if tag and not valid_serves(tag, brief):
                add(f'{key}.serves', 'the serves tag names no field of the brief', str(tag))
        for t in turns:
            if t.get('serves') and not valid_serves(t['serves'], brief):
                add(f"turns[{t.get('id')}].serves", 'the serves tag names no field of the brief', str(t['serves']))
        comps = premise.get('complications') or []
        limit = COMPLICATION_BUDGET.get(self.budget(), 3)
        if len(comps) > limit:
            add('complications', f'{len(comps)} complications; the {self.budget()} budget allows {limit}')
        for c in comps:
            if isinstance(c, dict) and c.get('serves') and not valid_serves(c['serves'], brief):
                add('complications.serves', 'the serves tag names no field of the brief', str(c['serves']))
        seeds = [s for s in premise.get('cast_seeds') or [] if isinstance(s, dict)]
        roles = [norm(s.get('role')) for s in seeds]
        for t in turns:
            for r in t.get('involves') or []:
                if norm(r) not in roles:
                    add(f"turns[{t.get('id')}].involves", f'the turn involves "{r}", who has no cast seed', str(r))
        for s in seeds:
            if s.get('kind') == 'crowd' and not [o for o in seeds if o.get('kind') != 'crowd'
                                                   and norm(o.get('speaks_for')) == norm(s.get('role'))]:
                add('cast_seeds', f'crowd "{s.get("role")}" has no individual who speaks for it', str(s.get('role')))
        return out

    @staticmethod
    def engine_checklist(premise):
        """The judgment half of the engine audit, as a fixed list the model
        answers item by item."""
        items = [
            ('E1', 'protagonist.cannot_do names a real limit: something the protagonist needs the world\'s '
                   'cooperation for. It is not "nothing" and not can_do restated.'),
            ('E2', 'opposition.wants is a want of its own, not "to stop the protagonist", and opposition.means '
                   'can actually act on the protagonist.'),
            ('E3', 'mediation.to_reach_pole_a.what_you_must_do is an action in the world (something found, said, '
                   'done, obtained or endured) with a cost. It is not the pole restated.'),
            ('E4', 'mediation.to_reach_pole_b.what_you_must_do is an action in the world with a cost. It is not '
                   'the pole restated.'),
            ('E5', 'everything the engine and the turns name is something a reader can picture: the levers, the '
                   'pressure, the situations and the ways through are people, places, objects, documents, events or '
                   'things said, not coined abstractions. If one is not, quote it.'),
            ('E6', 'no two turns pose the same choice: their ways are not the same outcomes with different nouns, and '
                   'turns before the last two have local goals of their own rather than the decision axis in another '
                   'form (unless the Kernel itself makes the decision recur). If they do, quote the later turn.'),
        ]
        for t in premise.get('turns') or []:
            if isinstance(t, dict):
                items.append((f"T{t.get('id')}", f"turn {t.get('id')} is not the decision axis handed over as a pick: each of its "
                                                 f"ways_through is something to do that costs something, not a pole to select."))
        return items

    def verify_premise(self, premise, round_no):
        """Computed checks plus the 3.5v audit. Returns the normalized
        finding list; an empty list is a clean verdict. The verdict is
        computed from the model's per-item answers, not asked for."""
        brief = self.analysis.get('s3_brief')
        clauses = kernel_clauses(self.kernel)
        constraints = constraint_fields(brief)
        checklist = self.engine_checklist(premise)

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            problems = []
            for key, wanted, idkey in (('clauses', [n for n, _ in clauses], 'n'),
                                       ('constraints', [n for n, _, _ in constraints], 'n'),
                                       ('engine', [i for i, _ in checklist], 'id')):
                got = parsed.get(key)
                if not isinstance(got, list):
                    problems.append(f'{key} must be a list')
                    continue
                for e in got:
                    if isinstance(e, dict) and idkey == 'id':
                        e['id'] = str(e.get('id') or '').strip().upper()
                have = {str(e.get(idkey)).strip() for e in got if isinstance(e, dict)}
                missing = [w for w in wanted if str(w) not in have]
                if missing:
                    problems.append(f'{key} has no entry for {missing}')
            if not isinstance(parsed.get('mechanics'), list):
                parsed['mechanics'] = []
            if problems:
                raise ValueError('; '.join(problems))

        prefix = 's3_5v' + (f'_r{round_no}' if round_no else '')
        answer = self.run_prompt(prefix, 'premise_check', {
            '$$CLAUSES$$': '\n'.join(f' {n}. {c}' for n, c in clauses),
            '$$CONSTRAINTS$$': '\n'.join(f' {n}. {line}' for n, _, line in constraints) or ' (the brief has no constraint-class field)',
            '$$ENGINE_CHECKS$$': '\n'.join(f' {i}. {text}' for i, text in checklist),
            '$$FAILURE_MODEL$$': brief_lines(brief, only=('3-0c',)),
            '$$PREMISE_JSON$$': self.to_json(premise),
            '$$KERNEL$$': self.kernel,
        }, prompt_file='s3_5v_premise_check.prompt', validator=validate, klass='audit',
            schema=schemas.PREMISE_CHECK)

        findings = self.premise_computed_findings(premise)
        clause_text = {str(n): c for n, c in clauses}
        constraint_text = {str(n): (fid, line) for n, fid, line in constraints}
        check_text = {i: text for i, text in checklist}
        for e in answer.get('clauses') or []:
            if isinstance(e, dict) and as_bool(e.get('contradiction')):
                findings.append({'source': 'kernel clause', 'where': clause_text.get(str(e.get('n')), str(e.get('n'))),
                                 'problem': str(e.get('note') or 'the material contradicts this clause'),
                                 'quote': str(e.get('quote') or '')})
        for e in answer.get('constraints') or []:
            if isinstance(e, dict) and as_bool(e.get('violated')):
                fid, line = constraint_text.get(str(e.get('n')), (str(e.get('n')), ''))
                findings.append({'source': 'brief constraint', 'where': line or fid,
                                 'problem': str(e.get('note') or 'the material contradicts this constraint'),
                                 'quote': str(e.get('quote') or '')})
        for e in answer.get('engine') or []:
            if isinstance(e, dict) and not as_bool(e.get('holds'), default=True):
                findings.append({'source': 'engine check', 'where': check_text.get(str(e.get('id')), str(e.get('id'))),
                                 'problem': str(e.get('note') or 'the check does not hold'), 'quote': str(e.get('quote') or '')})
        for e in answer.get('mechanics') or []:
            if isinstance(e, dict) and str(e.get('material') or '').strip():
                findings.append({'source': 'engine boundary', 'where': 'a system the engine lacks, or a way to lose 3-0c does not name',
                                 'problem': str(e.get('note') or ''), 'quote': str(e.get('material'))})
        return findings

    # ------------------------------------------------------------------ 3.5: the loop

    def run_premise_expansion(self):
        """Build (3.5a/b/c) -> verify (computed + 3.5v) -> repair (3.5r)
        while findings stand, up to --max-repairs rounds. Files:
          s3_5_premise.json            the build as assembled
          s3_5v[_r<n>]_premise_check   the audit's answers per round
          s3_5r<n>_premise_repair      {"repair_log", "revised": changed sections}
          s3_5_premise_accepted.json   what downstream reads
          s3_5_loop.json               the rounds and their findings
        Halts (PipelineHalt) if the last round still has findings.

        A finished loop (s3_5_loop.json and the accepted premise on disk) is
        replayed as it was: the accepted premise is loaded, not re-verified.
        Re-verifying would run TODAY's computed checks over it, and a check
        added since the run could raise a finding and start a repair round,
        a model call in what should be a free replay."""
        loop_record = self.load_story_file('s3_5_loop.json')
        accepted = self.load_story_file('s3_5_premise_accepted.json')
        if loop_record and accepted:
            record = json.loads(loop_record)
            if record.get('still_failing'):
                raise PipelineHalt(
                    f"s3_5 premise: the saved loop ended with findings still standing; inspect "
                    f"{self.story_file_path('s3_5_loop.json')}, then delete the s3_5* files to re-run the loop.")
            premise = json.loads(accepted)
            self.analysis['s3_5_premise'] = premise
            return premise
        premise = self.build_premise()
        self.save_story_json('s3_5_premise.json', premise)
        brief_table = brief_lines(self.analysis.get('s3_brief'))

        findings = self.verify_premise(premise, 0)
        rounds = [{'round': 0, 'source': 's3_5_premise.json', 'findings': findings}]
        n = 0
        while findings and n < self.max_repairs:
            n += 1
            current = premise

            def repair_validator(parsed, current=current):
                if not isinstance(parsed, dict) or not isinstance(parsed.get('revised'), dict):
                    raise ValueError('repair output must carry a "revised" object holding the sections you changed')
                # a model that echoes the whole premise back includes keys that
                # are not sections (the budget); they are ignored, not an error
                parsed['revised'] = {k: v for k, v in parsed['revised'].items() if k in PREMISE_KEYS}
                if not parsed['revised']:
                    raise ValueError(f'"revised" holds none of the sections {list(PREMISE_KEYS)}; return the ones you changed')
                merged = self.merge_premise(current, parsed['revised'])
                self.validate_engine(merged)
                self.validate_turns({'turns': merged['turns'], 'complications': merged['complications']})
                # what the repair broke that the computed checks can see: one
                # retry now is cheaper than a whole audit and repair round
                key = lambda f: (f['where'], f['problem'])
                before = {key(f) for f in self.premise_computed_findings(current)}
                broken = [f for f in self.premise_computed_findings(merged) if key(f) not in before]
                if broken:
                    raise SoftReject('the repair introduced new problems: ' + '; '.join(
                        f"{f['where']}: {f['problem']}" + (f' ("{f["quote"]}")' if f['quote'] else '') for f in broken))

            repaired = self.run_prompt(f's3_5r{n}', 'premise_repair', {
                '$$BRIEF_LINES$$': brief_table,
                '$$PREMISE_JSON$$': self.to_json(premise),
                '$$FINDINGS_JSON$$': self.to_json(findings),
                '$$KERNEL$$': self.kernel,
            }, prompt_file='s3_5r_premise_repair.prompt', validator=repair_validator, klass='build',
                schema=schemas.PREMISE_REPAIR)
            premise = self.name_cast(self.merge_premise(premise, repaired['revised']))
            findings = self.verify_premise(premise, n)
            rounds.append({'round': n, 'source': f's3_5r{n}_premise_repair.json#revised',
                           'changed': sorted(repaired['revised'].keys()),
                           'repair_log': repaired.get('repair_log', []), 'findings': findings})

        self.analysis['s3_5_premise'] = premise
        self.save_story_json('s3_5_premise_accepted.json', premise)
        self.save_story_json('s3_5_loop.json', {
            'accepted_source': rounds[-1]['source'],
            'accepted_copy': 's3_5_premise_accepted.json',
            'repair_rounds_used': n,
            'max_repairs': self.max_repairs,
            'still_failing': bool(findings),
            'rounds': rounds,
        })
        if findings:
            raise PipelineHalt(
                f"s3_5 premise: {len(findings)} finding(s) still stand after {n} repair round(s). Inspect "
                f"{self.story_file_path('s3_5_loop.json')}, fix the prompt or the material, then delete the "
                f"s3_5* files to re-run the loop."
            )
        return premise

    @staticmethod
    def merge_premise(premise, revised):
        """Repair returns only the sections it changed; everything else is
        carried over untouched by construction, not by instruction."""
        merged = json.loads(json.dumps(premise))
        for key, value in (revised or {}).items():
            if key in PREMISE_KEYS:
                merged[key] = value
        for i, t in enumerate(merged.get('turns') or []):
            if isinstance(t, dict):
                t['id'] = i + 1
        if not isinstance(merged.get('cast_seeds'), list):
            merged['cast_seeds'] = []
        wanted = {}
        for t in merged.get('turns') or []:
            if isinstance(t, dict):
                for r in t.get('involves') or []:
                    wanted.setdefault(norm(r), r)
        StoryGenerator.canonical_cast(merged['cast_seeds'], wanted)
        StoryGenerator.index_cast(merged)
        return merged

    # ------------------------------------------------------------------ 3.75: craft spine (opt-in)

    def run_craft_spine(self):
        """Optional (--craft-spine). The craft spine: the protagonist's want
        against an invented inner need, an irony device, an escalation
        shape, one setup/payoff pair. Built over the accepted premise,
        checked in code (craft_checks.py), repaired by a third call while a
        hard finding stands (up to --max-repairs rounds). A finding that
        survives is recorded and the run continues. The outline's line
        calls receive the want, the need and the setup/payoff; without this
        step they receive "none" and each line's motivation carries it.

        Files: s3_75_craft_spine.json (as built), s3_75_check_r<n>.json,
        s3_75r<n>_craft_spine_repair.json, s3_75_craft_spine_accepted.json,
        s3_75_loop.json."""
        brief = self.analysis.get('s3_brief')
        premise = self.analysis.get('s3_5_premise') or {}
        base = {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_JSON$$': self.to_json(brief),
            '$$PREMISE_EXPANSION_JSON$$': self.to_json(premise),
        }
        required = ('invention_ceiling', 'want_need_tension', 'irony_mode', 'escalation_shape', 'setup_payoff_pairs')

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            missing = [k for k in required if k not in parsed]
            if missing:
                raise ValueError(f'missing keys {missing}')

        def validate_repair(parsed):
            if not isinstance(parsed, dict) or not isinstance(parsed.get('revised'), dict):
                raise ValueError('repair output must carry a "revised" object')
            validate(parsed['revised'])

        current = self.run_prompt('s3_75', 'craft_spine', base, validator=validate, klass='build')
        findings = spine_findings(current, brief, premise)
        self.save_story_json('s3_75_check_r0.json', {'findings': findings})
        rounds = [{'round': 0, 'hard': sum(f['severity'] == 'hard' for f in findings)}]
        n = 0
        while any(f['severity'] == 'hard' for f in findings) and n < self.max_repairs:
            n += 1
            repl = dict(base)
            repl['$$CRAFT_SPINE_JSON$$'] = self.to_json(current)
            repl['$$FINDINGS_JSON$$'] = self.to_json({'findings': [f for f in findings if f['severity'] == 'hard']})
            repaired = self.run_prompt(f's3_75r{n}', 'craft_spine_repair', repl,
                                       prompt_file='s3_75r_craft_spine_repair.prompt',
                                       validator=validate_repair, klass='build')
            current = repaired['revised']
            findings = spine_findings(current, brief, premise)
            self.save_story_json(f's3_75_check_r{n}.json', {'findings': findings})
            rounds.append({'round': n, 'hard': sum(f['severity'] == 'hard' for f in findings),
                           'repair_log': repaired.get('repair_log', [])})
        still = [f for f in findings if f['severity'] == 'hard']
        if still:
            print(f'WARNING (continuing): the craft spine still has {len(still)} hard finding(s) after {n} '
                  f'repair round(s); see {self.story_file_path("s3_75_loop.json")}', file=sys.stderr)
        self.save_story_json('s3_75_craft_spine_accepted.json', current)
        self.save_story_json('s3_75_loop.json', {'repair_rounds_used': n, 'still_failing': bool(still),
                                                 'rounds': rounds})
        self.analysis['s3_75_craft_spine'] = current
        return current

    # ------------------------------------------------------------------ 3.8: story form

    def run_story_form(self):
        """Choose the framework the outline loop scaffolds on. The shortlist
        and the available modifiers are computed from the brief; the model
        picks among them with the premise in view (no thinking, a short
        reading first). --framework makes the choice instead: no call is
        made, and no modifier is applied."""
        brief = self.analysis.get('s3_brief')
        premise = self.analysis.get('s3_5_premise') or {}
        short = frameworks.shortlist(brief, self.kernel, self.story_id, length=(self.shape or {}).get('length', 'unstated'))
        modifiers = frameworks.available_modifiers(brief, self.kernel)
        candidate_ids = [c['id'] for c in short['candidates']]
        modifier_ids = [m['id'] for m in modifiers]

        if self.framework_override:
            form = {'framework': self.framework_override, 'modifier': 'none',
                    'reading': '', 'why': 'chosen on the command line (--framework)'}
        else:
            def validate(parsed):
                if not isinstance(parsed, dict):
                    raise ValueError('expected a JSON object')
                fw = str(parsed.get('framework') or '').strip()
                if fw not in candidate_ids:
                    raise ValueError(f'framework must be one of {candidate_ids}; got "{fw}"')
                parsed['framework'] = fw
                mod = str(parsed.get('modifier') or 'none').strip()
                parsed['modifier'] = mod if mod in modifier_ids else 'none'
                for key in ('reading', 'why'):
                    parsed[key] = str(parsed.get(key) or '').strip()

            med = premise.get('mediation') or {}
            digest = {
                'question': med.get('question'),
                'protagonist_wants': (premise.get('protagonist') or {}).get('wants'),
                'protagonist_cannot': (premise.get('protagonist') or {}).get('cannot_do'),
                'opposition_wants': (premise.get('opposition') or {}).get('wants'),
                'pressure': (premise.get('pressure') or {}).get('description'),
                'turns': [f"{t.get('id')}. ({t.get('form')}) {t.get('situation')}" for t in premise.get('turns') or []],
            }
            form = self.run_prompt('s3_8', 'story_form', {
                '$$KERNEL$$': self.kernel,
                '$$BRIEF_LINES$$': brief_lines(brief, only=('3b.', '3c.', '3d.', '3-0b.epistemic', '3-0b.gap', '3-0c.', '3e.', '3f.', '3-0a.decision')),
                '$$PREMISE_DIGEST_JSON$$': self.to_json(digest),
                '$$CANDIDATES_JSON$$': self.to_json(short['candidates']),
                '$$MODIFIERS_JSON$$': compact_json({'modifiers': modifiers}),
            }, validator=validate, klass='classify', schema=schemas.story_form(candidate_ids, modifier_ids))

        fw = frameworks.framework(form['framework'])
        mod = frameworks.modifier(form['modifier'])
        chosen = {
            'id': fw['id'], 'name': fw['name'], 'shape': fw['shape'],
            'modifier': {'id': mod['id'], 'name': mod['name'], 'effect': mod['effect']},
            'reading': form.get('reading'), 'why': form.get('why'),
            'named_in_kernel': short.get('named_in_kernel'),
            'shortlist': candidate_ids, 'scores': short.get('scores'),
            'beats': fw['beats'],
        }
        self.analysis['framework'] = chosen
        self.save_story_json('s3_8_framework.json', chosen)
        return chosen

    # ------------------------------------------------------------------ step 4

    def run_outline(self, max_iterations=None):
        """max_iterations None: derived from the Kernel's shape (brief.shape_targets)."""
        if max_iterations is None:
            max_iterations = shape_targets(self.shape).get('default_max_iterations') or 4
        builder = OutlineBuilder(self, max_iterations=max_iterations, branching=self.branching)
        story = builder.run()
        self.analysis['story'] = story
        return story

    # ------------------------------------------------------------------ 4e: the outline judge

    def run_outline_judge(self):
        """Computed metrics over the finished outline (evaluate.py), plus one
        thinking-off call that scores it on six axes and names the best and
        worst thing in it. Written to <id>_eval.json; report.py and ab.py
        read it. The judge is the same local model grading its own work, so
        its numbers are a weak signal, kept because they are cheap and
        comparable across runs. --no-outline-judge skips the call; the
        metrics are always computed."""
        story = self.analysis.get('story')
        if not story:
            path = Path(self.story_file_path('story.json'))
            if not path.is_file():
                return None
            story = json.loads(path.read_text(encoding='utf-8'))
        result = {'metrics': evaluate.metrics(story, self.analysis.get('s3_4_promises')), 'judge': None}
        if self.outline_judge:
            result['judge'] = self.run_prompt('s4e', 'outline_judge', {
                '$$KERNEL$$': self.kernel,
                '$$TONE$$': self.tone_line(),
                '$$PROMISES$$': self.promises_block(),
                '$$OUTLINE$$': evaluate.judge_digest(story),
            }, prompt_file='s4e_outline_judge.prompt', validator=evaluate.validate_judge, klass='classify',
                schema=schemas.OUTLINE_JUDGE)
        self.save_story_json('eval.json', result)
        for line in evaluate.summary_lines(result):
            print(line)
        return result


    # ------------------------------------------------------------------ stage A: arcs and node expansion

    def run_arcs(self, story=None):
        """Stage A (generator/arcs.py, docs/later_stages.md §2): the arc cast,
        the arc plan, one expansion call per line, then the computed
        thresholds, composed endings, checks and a playtest of the expanded
        graph. Writes <id>_arcs.json and <id>_arcs.md. Every call replays from
        its saved file, so running with --stage-a on a finished story
        directory makes model calls for stage A only."""
        story = story or self.analysis.get('story')
        if not story:
            path = Path(self.story_file_path('story.json'))
            if not path.is_file():
                raise PipelineHalt('stage A needs a finished outline (<id>_story.json)')
            story = json.loads(path.read_text(encoding='utf-8'))
        result = arcs.ArcBuilder(self, story).run()
        self.save_story_json('arcs.json', result)
        self.save_story_file('arcs.md', arcs.arcs_markdown(result, story))
        found = result['checks'] + result['playtest']['findings']
        print(f"stage A: {len(result['minor_nodes'])} minor nodes, {len(result['states'])} states, "
              f"{len(result['pattern_shifts'])} pattern shift(s), {len(found)} finding(s)")
        for f in found:
            print(f'  - {f}')
        return result


def as_bool(value, default=False):
    """A verdict the model wrote: true, "true", "yes". Anything unreadable is
    the default, which each caller sets to the answer that raises no finding
    only where a missing answer is already rejected by its validator."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ('true', 'yes', '1'):
        return True
    if text in ('false', 'no', '0'):
        return False
    return default


def slugify(name):
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def csv(value):
    return [s.strip() for s in (value or '').split(',') if s.strip()]


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--story-id", default='', help="identifier for the story, used for directory and file naming (note will be slugified)")
    parser.add_argument("--rating", default=DEFAULT_RATING, help="(step2 input) US Film Rating to respect for generated story")
    parser.add_argument("--max-repairs", type=int, default=DEFAULT_MAX_REPAIRS,
                        help="repair rounds allowed in the 3.5 build/verify loop before halting (default 2)")
    parser.add_argument("--max-iterations", type=int, default=None,
                        help="step 4: maximum story lines to build, main line included (default: from the Kernel's "
                             "ending tier: one 1, few 2, several 4, many 6, unstated 3; a linear shape gets two more)")
    parser.add_argument("--branching", default='plan', choices=['plan', 'judge'],
                        help="how divergent lines are seeded: 'plan' (default) designs every divergence and its ending "
                             "world in one call after the main line (4p); 'judge' asks after each line whether another "
                             "is worth building (4d), the behaviour before 2026-10-04")
    parser.add_argument("--no-promises", action="store_true",
                        help="skip 3.4 (genre promises); the premise and line prompts get 'none'")
    parser.add_argument("--no-outline-judge", action="store_true",
                        help="skip the 4e scoring call over the finished outline (the computed metrics still run)")
    parser.add_argument("--framework", default='', choices=[''] + frameworks.framework_ids(),
                        help="use this story framework instead of letting 3.8 choose")
    parser.add_argument("--no-think-steps", default='',
                        help="comma-separated steps to run with the model's thinking off, in addition to the "
                             "ones that already do (s2_shape, s3_5c, s3_8). A step is a prefix (s4a_i1), "
                             "a step id (s4a) or step_name (s2_shape).")
    parser.add_argument("--think-steps", default='',
                        help="comma-separated steps to run with thinking ON even though their class turns it "
                             "off (e.g. s3_8)")
    parser.add_argument("--no-force-answer", action="store_true",
                        help="when a thinking call passes its thinking limit, skip budget forcing and go "
                             "straight to the thinking-off re-run")
    parser.add_argument("--no-breakers", action="store_true",
                        help="do not cut off calls that exceed their class's thinking or time limit")
    parser.add_argument("--stop-after", default='',
                        help="stop after this step: 2, 3, 3.4, 3.5, 3.75, 3.8 (default: run through the outline loop)")
    parser.add_argument("--stage-a", action="store_true",
                        help="after the outline, run stage A (arcs and node expansion: <id>_arcs.json, <id>_arcs.md); "
                             "on a finished story directory only stage A makes model calls")
    parser.add_argument("--craft-spine", action="store_true",
                        help="run the craft spine (3.75: want against need, irony, escalation, setup/payoff) after "
                             "the premise and give its want/need to the line calls (default: off)")
    args = parser.parse_args()

    story_id = slugify(args.story_id)
    if not story_id:
        story_id = f'story_{int(time.time())}'

    try:
        gen = StoryGenerator(story_id=story_id, max_repairs=args.max_repairs,
                             no_think_steps=csv(args.no_think_steps), think_steps=csv(args.think_steps),
                             breakers=not args.no_breakers, framework_override=args.framework.strip() or None,
                             force_answer=not args.no_force_answer, promises=not args.no_promises,
                             branching=args.branching, outline_judge=not args.no_outline_judge)
    except PipelineHalt as halt:
        print(f'\nPIPELINE HALTED: {halt}', file=sys.stderr)
        sys.exit(2)

    print('enter kernel and close stdin:')

    def finish(code=0):
        for line in gen.stats.summary_lines():
            print(line)
        sys.exit(code)

    try:
        gen.s1_take_kernel(sys.stdin.read())
        gen.s2_apply_rating(rating=args.rating)

        gen.s2_split_shape()
        if args.stop_after == '2':
            finish()

        gen.run_phase3()
        if args.stop_after == '3':
            finish()

        # 3.4: what the genre owes the audience, as defaults for 3.5 and step 4.
        gen.run_promises()
        if args.stop_after == '3.4':
            finish()

        # 3.5: the first step that CONSTRUCTS. Builds the dramatic engine
        #  (protagonist, pressure, opposition, events, mediation, turns, cast seeds).
        gen.run_premise_expansion()
        if args.stop_after == '3.5':
            finish()

        # 3.75 (opt-in): the craft spine; the line calls read its want/need.
        if args.craft_spine:
            gen.run_craft_spine()
        if args.stop_after == '3.75':
            finish()

        # 3.8: what kind of story this is; the framework the lines are laid over.
        gen.run_story_form()
        if args.stop_after == '3.8':
            finish()

        # step 4: the outline loop. Main line, the branch plan, then one divergent line per iteration.
        gen.run_outline(max_iterations=args.max_iterations)
        # 4e: one cheap scoring call over the finished outline, plus the computed metrics.
        gen.run_outline_judge()
        if args.stage_a:
            gen.run_arcs()
    except PipelineHalt as halt:
        print(f'\nPIPELINE HALTED: {halt}', file=sys.stderr)
        finish(2)
    except Exception:
        # print what ran before the error, then fail with the traceback
        for line in gen.stats.summary_lines():
            print(line)
        raise
    finish()
