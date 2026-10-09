#!/usr/bin/env python3
"""Two outlines side by side (step 4f): which does each thing better.

    python compare.py kernel35_f5 kernel35_f6               # two runs (story ids, or paths to *_story.json)
    python compare.py ref_canterville ref:ref_canterville --main-line   # ours against the human outline

The 4e judge reads one outline at a time and reports facts; this asks the
questions a comparison needs (which cost lands, which setup decides the
crisis, which opposition is dangerous, which turn recasts, which can be
pictured, which you would rather play) of the two together. Every question
is asked twice with the outlines in both orders, and an outline wins it
only if it wins both ways: a model reading two texts favours one position,
and a split is the honest answer when the two readings disagree.
--main-line compares the first line of each only (the human references are
linear, so a branching outline should not win on size). The calls are
logged in the first story's directory and replay when run again.
Writes <id>_compare_<tag>.json there and prints the verdicts.
"""

import argparse
import hashlib
import json
import os
import sys

import evaluate
import schemas

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES = os.path.join(THIS_DIR, '..', 'stories')
REFS = os.path.join(THIS_DIR, '..', 'tests', 'kernels', 'reference')
QUESTIONS = ('cost', 'setups', 'opposition', 'turn', 'picture', 'play')


def resolve(spec):
    """(story id or None, path to the outline). 'ref:<id>' is a human
    reference outline; a bare id is stories/<id>/<id>_story.json."""
    if spec.startswith('ref:'):
        rid = spec[4:]
        return None, os.path.join(REFS, f'{rid}_reference.json')
    if os.path.isfile(spec):
        base = os.path.basename(spec)
        return (base[:-len('_story.json')] if base.endswith('_story.json') else None), spec
    return spec, os.path.join(STORIES, spec, f'{spec}_story.json')


def main_line_only(story):
    order = story.get('line_order') or list(story.get('lines') or {})
    if not order:
        return story
    first = order[0]
    path = story['lines'][first].get('path') or []
    return dict(story, lines={first: story['lines'][first]}, line_order=[first],
                nodes={n: story['nodes'][n] for n in path if n in story.get('nodes', {})},
                node_order=[n for n in (story.get('node_order') or path) if n in path])


def validator(digests):
    def validate(parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected a JSON object')
        problems = []
        for q in QUESTIONS:
            a = parsed.get(q)
            if not isinstance(a, dict):
                problems.append(f'{q} is missing')
                continue
            w = str(a.get('winner') or '').strip().lower().replace('outline', '').strip()
            if w not in ('1', '2', 'same'):
                problems.append(f'{q}.winner must be "1", "2" or "same", not {a.get("winner")!r}')
                continue
            a['winner'] = w
            a['why'] = str(a.get('why') or '').strip()
            a['quote'] = str(a.get('quote') or '').strip()
            a['verified'] = w == 'same' or evaluate._quote_in(a['quote'], evaluate._plain(digests[int(w) - 1]))
        if problems:
            raise ValueError('; '.join(problems))
    return validate


def verdicts(first, second):
    """first: answers with A as outline 1; second: with B as outline 1.
    Per question: 'A' or 'B' when it wins both readings, 'same' when both
    say so, 'split' otherwise."""
    out = {}
    for q in QUESTIONS:
        a = {'1': 'A', '2': 'B', 'same': 'same'}[first[q]['winner']]
        b = {'1': 'B', '2': 'A', 'same': 'same'}[second[q]['winner']]
        out[q] = a if a == b else 'split'
    return out


def compare(spec_a, spec_b, main_line=False, gen=None):
    sid_a, path_a = resolve(spec_a)
    sid_b, path_b = resolve(spec_b)
    stories = []
    for path in (path_a, path_b):
        if not os.path.isfile(path):
            raise SystemExit(f'no outline at {path}')
        with open(path, encoding='utf-8') as f:
            story = json.load(f)
        stories.append(main_line_only(story) if main_line else story)
    home = sid_a or sid_b
    if not home:
        raise SystemExit('one of the two must be a pipeline story (its directory holds the calls)')
    if gen is None:
        from main import StoryGenerator
        gen = StoryGenerator(story_id=home)
    kernel_file = gen.story_file_path('s1_kernel.txt')
    gen.kernel = (open(kernel_file, encoding='utf-8').read().strip() if os.path.isfile(kernel_file)
                  else stories[0].get('kernel') or '')
    digests = [evaluate.judge_digest(s) for s in stories]
    tag = hashlib.md5(f'{spec_a}|{spec_b}|{main_line}'.encode()).hexdigest()[:8]
    answers = []
    for order, (one, two) in enumerate(((0, 1), (1, 0))):
        answers.append(gen.run_prompt(f's4f_{tag}_{order + 1}', 'compare', {
            '$$KERNEL$$': gen.kernel, '$$OUTLINE_1$$': digests[one], '$$OUTLINE_2$$': digests[two],
        }, prompt_file='s4f_compare.prompt', validator=validator([digests[one], digests[two]]), klass='classify',
            schema=schemas.COMPARE))
    result = {'a': spec_a, 'b': spec_b, 'main_line': main_line, 'verdicts': verdicts(*answers),
              'readings': {'a_first': answers[0], 'b_first': answers[1]}}
    gen.save_story_json(f'compare_{tag}.json', result)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--main-line', action='store_true', help='compare the first line of each only')
    args = ap.parse_args(argv)
    result = compare(args.a, args.b, args.main_line)
    print(f"A = {args.a}, B = {args.b}" + (' (main lines)' if args.main_line else ''))
    for q in QUESTIONS:
        v = result['verdicts'][q]
        why = result['readings']['a_first'][q]['why'] if v != 'split' else 'the two readings disagree'
        print(f'  {q:<11} {v:<6} {why[:110]}')
    wins = {s: sum(1 for v in result['verdicts'].values() if v == s) for s in ('A', 'B', 'same', 'split')}
    print(f"  A {wins['A']}, B {wins['B']}, same {wins['same']}, split {wins['split']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
