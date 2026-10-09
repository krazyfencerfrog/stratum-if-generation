#!/usr/bin/env python3
"""Compare the pipeline against human craft (docs/reference_stories.md).

Each reference kernel (tests/kernels/reference/<id>.txt) has the human
story's structure beside it as an outline (<id>_reference.json). After the
pipeline has run on the kernel (stories/<id>, e.g. via
`batch.py add reference/<id>`):

    python reference.py judge ref_canterville     # the 4e judge on the human outline, with the run's own tone and
                                                  # promises: stories/<id>/<id>_human_eval.json
    python reference.py report                    # every reference: judge scores and metrics, pipeline vs human

The judge sees the human outline exactly as it sees the pipeline's, so the
comparison says how far apart they are on the judge's axes, and whether the
judge can tell a classic from our output at all (if it scores them alike,
the judge is the problem). The human outlines have one line, so agency is
not comparable.
"""

import argparse
import json
import os
import sys

import evaluate
import schemas

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(THIS_DIR, '..', 'tests', 'kernels', 'reference')
STORIES = os.path.join(THIS_DIR, '..', 'stories')


def ref_ids():
    return sorted(f[:-len('_reference.json')] for f in os.listdir(REFS) if f.endswith('_reference.json'))


def load(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def judge(story_id):
    from main import StoryGenerator
    human = load(os.path.join(REFS, f'{story_id}_reference.json'))
    if human is None:
        print(f'no reference outline for {story_id}', file=sys.stderr)
        return 1
    gen = StoryGenerator(story_id=story_id)
    with open(os.path.join(REFS, f'{story_id}.txt'), encoding='utf-8') as f:
        gen.kernel = f.read().strip()
    for key, suffix in (('s3_brief', 's3_brief.json'), ('s3_4_promises', 's3_4_promises.json')):
        value = load(gen.story_file_path(suffix))
        if value is not None:
            gen.analysis[key] = value
    if 's3_brief' not in gen.analysis:
        print(f'stories/{story_id} has no pipeline run yet (needs its brief for the tone); run it first', file=sys.stderr)
        return 1
    result = {'metrics': evaluate.metrics(human, gen.analysis.get('s3_4_promises')), 'judge': gen.run_prompt(
        's4e_human', 'outline_judge', {
            '$$KERNEL$$': gen.kernel,
            '$$TONE$$': gen.tone_line(),
            '$$PROMISES$$': gen.promises_block(),
            '$$OUTLINE$$': evaluate.judge_digest(human),
        }, prompt_file='s4e_outline_judge.prompt', validator=evaluate.judge_validator(human), klass='classify',
        schema=schemas.OUTLINE_JUDGE)}
    gen.save_story_json('human_eval.json', result)
    for line in evaluate.summary_lines(result):
        print(line)
    return 0


def report():
    keys = ('nodes', 'summary_words_mean', 'repeated_phrase_count', 'retold_nodes')
    print(f"{'story':<28} {'who':<9} {'judge':<88} " + ' '.join(f'{k[:12]:>12}' for k in keys))
    for sid in ref_ids():
        for who, suffix in (('pipeline', 'eval.json'), ('human', 'human_eval.json')):
            ev = load(os.path.join(STORIES, sid, f'{sid}_{suffix}'))
            if not ev:
                print(f'{sid:<28} {who:<9} (not run)')
                continue
            m = ev.get('metrics') or {}
            print(f'{sid:<28} {who:<9} {evaluate.judge_brief(ev.get("judge")):<88} '
                  + ' '.join(f'{str(m.get(k, "-")):>12}' for k in keys))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    j = sub.add_parser('judge')
    j.add_argument('story_ids', nargs='*', help='default: every reference that has a pipeline run')
    sub.add_parser('report')
    args = ap.parse_args(argv)
    if args.cmd == 'report':
        return report()
    ids = args.story_ids or [s for s in ref_ids() if os.path.isfile(os.path.join(STORIES, s, f'{s}_s3_brief.json'))]
    return max([judge(s) for s in ids] or [0])


if __name__ == '__main__':
    sys.exit(main())
