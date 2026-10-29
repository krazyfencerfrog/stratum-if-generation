#!/usr/bin/env python3
"""Scripted player over the engine API: acts by substring match on the menu path.

    python play.py <package.json> "cmd1" "cmd2" ...

A command is a substring matched case-insensitively against each leaf's full path
("Talk › Lucius Carrington › about the study key"). "?" prints the current menu leaves.
"way" takes the first leaf the engine marks as a way on. Unmatched commands are reported.
"""
import json
import sys
import os
ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'engine'))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)
from runtime import Engine
from story import Story


def leaves(node, path=()):
    out = []
    for ch in node.get('children', []):
        p = path + (ch.get('label', ''),)
        if 'id' in ch:
            out.append((' › '.join(p), ch['id'], ch))
        else:
            out.extend(leaves(ch, p))
    return out


def text_of(view):
    parts = []
    for key in ('text', 'opening', 'room'):
        v = view.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
        elif isinstance(v, list):
            parts.extend(str(x).strip() for x in v if str(x).strip())
        elif isinstance(v, dict):
            for kk in ('name', 'description', 'text'):
                if v.get(kk):
                    parts.append(str(v[kk]).strip())
    return '\n'.join(parts)


def main():
    pkg = sys.argv[1]
    cmds = sys.argv[2:]
    with open(pkg, encoding='utf-8') as f:
        story = Story(json.load(f))
    eng = Engine(story)
    view = eng.start()
    print('### START')
    print(text_of(view)[:1500])
    print('scene:', view.get('scene'), 'room:', view.get('room', {}).get('name') if isinstance(view.get('room'), dict) else view.get('room'))
    n = 0
    for cmd in cmds:
        lv = leaves(view['menu'])
        if cmd == '?':
            print('--- MENU (%d leaves):' % len(lv))
            for p, i, ch in lv:
                mark = ' →' if ch.get('way') else ''
                mark += ' ◆' if ch.get('weight') == 'major' else ''
                print('   ', p + mark)
            continue
        if cmd == 'way':
            hit = next(((p, i) for p, i, ch in lv if ch.get('way')), None)
        else:
            hit = next(((p, i) for p, i, ch in lv if cmd.lower() in p.lower()), None)
        if not hit:
            print(f'!!! NOT FOUND: {cmd}  (leaves: {len(lv)})')
            for p, i, ch in lv[:60]:
                print('      ', p)
            continue
        n += 1
        print(f'\n### {n}. {hit[0]}')
        view = eng.act(hit[1])
        print(text_of(view)[:1400])
        sc = view.get('scene')
        print(f'[scene {sc} | turns {eng.state.turns if hasattr(eng, "state") else "?"}]')
        if view.get('ending'):
            print('### ENDING', json.dumps(view.get('ending'))[:3000])
            break


if __name__ == '__main__':
    main()
