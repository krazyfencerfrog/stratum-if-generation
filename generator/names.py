"""Names for the cast, assigned in Python rather than by the model.

A local model asked for names collapses onto the same few (and a ban list
only moves it to the next favourites), so the construction prompts name
people by ROLE and this module gives each individual a name drawn from a
pool chosen by the story's genre. The role stays the key every step matches
on; the name rides along in the cast seed and the character register, so a
later stage (or a person) can replace it in one place.

Deterministic: the same story id and role always get the same name.
"""

import json
import random
import re
from pathlib import Path

POOLS = json.loads((Path(__file__).resolve().parent.parent / 'config' / 'names.json').read_text(encoding='utf-8'))

# what the model reaches for when it names people itself; kept out of every pool
AVOID = {'elara', 'kael', 'lyra', 'thorne', 'aria', 'seraphina', 'aldric', 'elias', 'voss', 'chen', 'kira',
         'mira', 'zara', 'finn', 'rowan blackwood', 'eldon', 'thalia', 'cassian', 'orin', 'vex', 'nova'}

# keyword -> pool; whole words only. The kernel's own words count three
# times; the premise's once. The pool with the most hits wins.
GENRE_WORDS = {
    pool: r'\b(?:' + words + r')\b' for pool, words in {
        'fantasy': r'fantasy|dragons?|witch(?:es)?|hedge-witch|wizards?|mages?|magic(?:al)?|swords?|elf|elves|dwarf|dwarves|'
                   r'kingdoms?|quests?|dungeons?|sorcer\w*|fae|curse[sd]?|knights?|castles?|realms?|spells?|'
                   r'enchant\w*|goblins?|trolls?|necromanc\w*|prophec\w*',
        'medieval': r'medieval|monaster\w*|abbey|plague|feudal|crusade|serfs?|barons?|pirates?|galleons?|'
                    r'royal navy|buccaneers?',
        'scifi': r'sci-fi|science fiction|starships?|spaceships?|generation(?:al)? ship|space station|planets?|colon(?:y|ies)|androids?|'
                 r'robots?|ai|cyber\w*|orbit\w*|asteroids?|arcology|hull|airlocks?|reactors?|drones?|'
                 r'terraform\w*|interstellar',
        'period': r'1[89][0-9]0s|steampunk|noir|cold war|victorian|edwardian|prohibition|wartime|detectives?',
    }.items()
}

# roles that are not people, or not one person: they keep their role
NOT_A_PERSON = re.compile(r"\b(dragon|sword|blade|ai|ship|computer|machine|beast|creature|spirit|ghost|wolf|hound|"
                          r"horse|storm|council|crowd|crew|families|villagers|guards|navy|army|mob|house|tower|"
                          r"system|core|voice|swarm|hive)\b", re.I)


def pool_for(kernel, *texts):
    scores = {pool: 3 * len(re.findall(rx, (kernel or '').lower()))
              + sum(len(re.findall(rx, (t or '').lower())) for t in texts)
              for pool, rx in GENRE_WORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return 'modern'
    if best == 'medieval' and scores['fantasy'] >= scores['medieval']:
        return 'fantasy'
    return best


def gender_hint(role, texts):
    """'f', 'm' or 'n' from the pronouns in the sentences that mention the
    role. Weak evidence on purpose: anything unclear gives 'n'."""
    head = re.sub(r"^(the|a|an)\s+", '', role.lower()).split("'")[0].strip()
    if not head:
        return 'n'
    f = m = 0
    for text in texts:
        for sentence in re.split(r'(?<=[.;!?])\s+', text or ''):
            if head in sentence.lower():
                f += len(re.findall(r'\b(she|her|hers|herself)\b', sentence, re.I))
                m += len(re.findall(r'\b(he|him|his|himself)\b', sentence, re.I))
    if f > m:
        return 'f'
    if m > f:
        return 'm'
    return 'n'


def wants_a_name(seed):
    return (isinstance(seed, dict) and seed.get('role') and seed.get('kind') != 'crowd'
            and not NOT_A_PERSON.search(str(seed['role']))
            and re.sub(r'^(the|a|an)\s+', '', str(seed['role']).strip().lower()) not in ('protagonist', 'you', 'player'))


def pick(story_id, role, pool_name, gender, taken):
    """One name not yet taken in this story: given name and surname both
    unused, drawn deterministically from the story id and the role."""
    pool = POOLS.get(pool_name) or POOLS['modern']
    rng = random.Random(f'{story_id}|{role.lower()}')
    if gender == 'n':
        givens = (pool.get('n') or []) + pool['f'] + pool['m']
    else:
        givens = (pool.get(gender) or []) + (pool.get('n') or [])
    givens = [g for g in givens if g.lower() not in AVOID]
    surnames = [s for s in pool.get('surnames') or [] if s.lower() not in AVOID]
    used = {part.lower() for name in taken for part in name.split()}
    for _ in range(200):
        given = rng.choice(givens)
        surname = rng.choice(surnames) if surnames else ''
        if given.lower() in used or (surname and surname.split()[-1].lower() in used):
            continue
        return f'{given} {surname}'.strip()
    return f'{rng.choice(givens)} {rng.choice(surnames) if surnames else ""}'.strip()


def assign_names(seeds, story_id, texts, pool_name=None):
    """Gives every individual seed that is a person a 'name', keeping any it
    already has. texts: the kernel first, then premise text, for the genre
    and for pronoun hints. Returns the pool used."""
    pool_name = pool_name or pool_for(*texts)
    taken = [s['name'] for s in seeds if isinstance(s, dict) and s.get('name')]
    for s in seeds:
        if wants_a_name(s) and not s.get('name'):
            s['name'] = pick(story_id, str(s['role']), pool_name, gender_hint(str(s['role']), texts), taken)
            taken.append(s['name'])
    return pool_name
