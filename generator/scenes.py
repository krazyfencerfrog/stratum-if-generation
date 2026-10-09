#!/usr/bin/env python3
"""Stage B0: scenes, subjects and the room target (docs/later_stages.md §3).

Pure Python over the outline and stage A's output; no model calls.

  scenes    the engine's unit of story position (engine_design §2): a major
            node and the minor nodes stage A hung after it, in continuous
            time and place. Minor nodes inherit their major node's places.
            Consecutive groups that every line passes through together in
            the same places are listed as merge candidates (one continuous
            scene, perhaps) for a later review; they are not merged here.
  subjects  everything a player could raise in conversation: people (the
            cast and the functional people stage A named), places (the
            location register) and the world's events, each with the scene
            where it first appears. Objects are left to B2, which builds them
            from the moments.
  rooms     the target room count, from the brief's setting scale and the
            genre: the middle ground at least (about ten rooms), more for
            exploration and adventure (the user's decision, 2026-10-04).

    python scenes.py kernel35_f5     # reads <id>_story.json and <id>_arcs.json, writes <id>_scenes.json
"""

import argparse
import json
import os
import re
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES = os.path.join(THIS_DIR, '..', 'stories')

SCALE_ROOMS = {'room_or_building': (10, 14), 'city_or_region': (12, 24), 'world': (20, 40), 'multi_world': (24, 40)}
MIDDLE_GROUND = 10        # the floor for every story (the user, 2026-10-04): about ten rooms
EXPLORING = re.compile(r'\b(adventure|quest|dungeon|crawl|explor\w*|journey|expedition|treasure|odyssey|travel\w*)\b', re.I)


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def build_scenes(story, arcs):
    """One scene per major node and its minor nodes. Returns (scenes,
    merge_candidates)."""
    nodes = story['nodes']
    graph = (arcs or {}).get('graph') or {}
    minors = (arcs or {}).get('minor_nodes') or {}
    lines = graph.get('lines') or story['lines']
    order = story.get('line_order') or list(lines)
    after = {}
    for mid, m in minors.items():
        after.setdefault(m['after'], []).append(mid)
    for group in after.values():
        group.sort()
    chars = story.get('characters') or {}

    def person(w):
        """A character id for a who entry (major nodes list ids, minor nodes
        names or labels); a functional person stays as written."""
        if w in chars:
            return w
        key = re.sub(r'\(.*?\)', '', str(w)).strip().lower()
        for cid, c in chars.items():
            if key in (str(c.get('name') or '').lower(), str(c.get('label') or '').lower()):
                return cid
        return w
    scenes, by_major = [], {}
    for nid in story.get('node_order') or list(nodes):
        n = nodes[nid]
        group = [nid] + after.get(nid, [])
        who = []
        for x in group:
            for w in as_list((minors.get(x) or n).get('who')):
                w = person(w)
                if w not in who:
                    who.append(w)
        moments = {}
        for x in group[1:]:
            moments.setdefault(minors[x]['kind'], []).append(x)
        sid = f'S_{nid}'
        scene = {'id': sid, 'major': nid, 'nodes': group, 'beat': n.get('beat'), 'title': n.get('title'),
                 'lines': [l for l in order if nid in (story['lines'][l].get('path') or [])],
                 'where': as_list(n.get('where')), 'who': who, 'moments': moments,
                 'event': n.get('event'), 'ending': bool(n.get('is_ending'))}
        scenes.append(scene)
        by_major[nid] = scene
    # what follows each scene, along the outline's edges
    for e in story.get('edges') or []:
        a, b = by_major.get(e['from']), by_major.get(e['to'])
        if a and b:
            a.setdefault('next', [])
            if b['id'] not in a['next']:
                a['next'].append(b['id'])
    merge = []
    for a in scenes:
        nxt = a.get('next') or []
        if len(nxt) == 1:
            b = next(s for s in scenes if s['id'] == nxt[0])
            if set(b['where']) == set(a['where']) and set(b['lines']) == set(a['lines']) and not b['event']:
                merge.append([a['id'], b['id']])
    return scenes, merge


def subjects(story, arcs, scenes):
    """People, places and events, each with the first scene it appears in."""
    first = {}

    def note(key, sid):
        first.setdefault(key, sid)

    for sc in scenes:
        for w in sc['who']:
            note(('person', w), sc['id'])
        for loc in sc['where']:
            note(('place', loc), sc['id'])
        if sc['event'] is not None:
            note(('event', sc['event']), sc['id'])
    out = []
    tiers = (arcs or {}).get('tiers') or {}
    for cid, c in (story.get('characters') or {}).items():
        label, name = c.get('label'), c.get('name')
        sid = first.get(('person', cid))
        out.append({'kind': 'person', 'id': cid, 'name': name or label, 'label': label,
                    'tier': (tiers.get(cid) or {}).get('tier'), 'first_scene': sid})
    for w in (arcs or {}).get('new_functional') or []:
        out.append({'kind': 'person', 'id': None, 'name': w, 'label': w, 'tier': 'functional',
                    'first_scene': first.get(('person', w))})
    for lid, loc in (story.get('locations') or {}).items():
        out.append({'kind': 'place', 'id': lid, 'name': loc.get('name'), 'first_scene': first.get(('place', lid))})
    for i, e in enumerate(as_list((story.get('premise') or {}).get('events')), 1):
        what = e.get('what') if isinstance(e, dict) else e
        out.append({'kind': 'event', 'id': f'E{i}', 'name': what, 'first_scene': first.get(('event', i))})
    return out


def room_target(story, brief=None, promises=None):
    """(min, max) rooms for the whole world: from the setting scale's ceiling,
    never below the middle ground, the upper half for exploring stories."""
    fields = (brief or {}).get('fields') or {}
    scale = fields.get('3f.setting_scale') or {}
    value = scale.get('value') if isinstance(scale, dict) else scale
    ceiling = (value.get('ceiling') if isinstance(value, dict) else value) or 'room_or_building'
    lo, hi = SCALE_ROOMS.get(str(ceiling), SCALE_ROOMS['room_or_building'])
    locations = len(story.get('locations') or {})
    lo = max(lo, MIDDLE_GROUND, locations + 2)
    hi = max(hi, lo + 4)
    genre = ' '.join(str((promises or {}).get(k) or '') for k in ('genre', 'reading', 'player_fantasy'))
    exploring = bool(EXPLORING.search(genre + ' ' + str(story.get('kernel') or '')))
    if exploring:
        lo = (lo + hi) // 2
        hi = max(hi, lo + 8)
    return {'min': lo, 'max': hi, 'scale': ceiling, 'exploring': exploring, 'locations': locations}


def plan(story, arcs, brief=None, promises=None):
    scenes, merge = build_scenes(story, arcs)
    return {'story_id': story.get('story_id'), 'stage': 'B0', 'scenes': scenes, 'merge_candidates': merge,
            'subjects': subjects(story, arcs, scenes), 'rooms': room_target(story, brief, promises)}


def load(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('story_id')
    args = ap.parse_args(argv)
    base = os.path.join(STORIES, args.story_id, args.story_id)
    story, arcs = load(base + '_story.json'), load(base + '_arcs.json')
    if not story:
        print(f'no outline at {base}_story.json', file=sys.stderr)
        return 1
    if not arcs:
        print('no stage A output (<id>_arcs.json): scenes will hold major nodes only', file=sys.stderr)
    result = plan(story, arcs, load(base + '_s3_brief.json'), load(base + '_s3_4_promises.json'))
    with open(base + '_scenes.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    r = result['rooms']
    print(f"{len(result['scenes'])} scenes, {len(result['merge_candidates'])} merge candidate(s), "
          f"{len(result['subjects'])} subjects; rooms {r['min']}-{r['max']} (scale {r['scale']}"
          f"{', exploring' if r['exploring'] else ''}, {r['locations']} locations)")
    for sc in result['scenes']:
        kinds = ', '.join(f'{k} {len(v)}' for k, v in sc['moments'].items()) or 'no minor nodes'
        print(f"  {sc['id']:<10} {sc['title']!s:<34} lines {','.join(sc['lines']):<9} {kinds}; next {sc.get('next') or '-'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
