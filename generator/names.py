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
# times; the premise's once. Era and culture pools score in full; the two
# tone pools (romance, adventure) at half, so "a romance in Regency London"
# lands in regency and "an epic fantasy adventure" in fantasy. Ties go to
# the earlier pool in PRIORITY.
GENRE_WORDS = {
    pool: r'\b(?:' + words + r')\b' for pool, words in {
        'japanese_historical': r'samurai|shogun\w*|ronin|edo|feudal japan|daimyo|ninjas?|katanas?|geishas?',
        'chinese_historical': r'wuxia|jianghu|kung fu|martial sects?|imperial china|forbidden city|'
                              r'(?:tang|song|ming|qing|han) dynasty',
        'ancient_egyptian': r'egypt\w*|pharaohs?|nile|pyramids?|scarabs?|sphinx|mumm(?:y|ies)|anubis|osiris|hieroglyph\w*',
        'ancient_roman': r'rome|roman|legions?|legionar\w*|centurions?|senat(?:e|or)s?|gladiators?|caesar|praetorians?|'
                         r'pompeii|consuls?|colosseum',
        'ancient_greek': r'ancient greece|greek|athens|athenian|spartans?|sparta|olympus|oracle|delphi|triremes?|'
                         r'hoplites?|agora|minotaur|troy|trojans?',
        'norse': r'vikings?|norse|fjords?|longships?|valhalla|jarls?|skalds?|odin|runes?|sagas?',
        'regency': r'regency|ballrooms?|debutantes?|the ton|almack\w*|dukes?|duchess\w*|earls?|viscounts?|marquess\w*',
        'victorian': r'victorian|edwardian|gaslight|hansom|steampunk|1[89][0-9]0s|nineteenth century',
        'western': r'wild west|western|cowboys?|frontier|sheriffs?|outlaws?|saloons?|ranch\w*|gunslingers?|'
                   r'stagecoach\w*|homestead\w*',
        'age_of_sail': r'pirates?|galleons?|royal navy|buccaneers?|privateers?|frigates?|age of sail|corsairs?',
        'medieval': r'medieval|monaster\w*|abbey|plague|feudal|crusades?|serfs?|barons?|child king|regents?|'
                    r'courtiers?|court intrigue|thrones?|usurp\w*|coronation',
        'scifi': r'sci-fi|science fiction|starships?|spaceships?|generation(?:al)? ship|space station|planets?|'
                 r'colon(?:y|ies)|androids?|robots?|ai|cyber\w*|orbit\w*|asteroids?|arcology|airlocks?|reactors?|'
                 r'drones?|terraform\w*|interstellar',
        'fantasy': r'fantasy|dragons?|witch(?:es)?|hedge-witch|wizards?|mages?|magic(?:al)?|swords?|elf|elves|dwarf|'
                   r'dwarves|kingdoms?|quests?|dungeons?|sorcer\w*|fae|curse[sd]?|knights?|castles?|realms?|spells?|'
                   r'enchant\w*|goblins?|trolls?|orcs?|necromanc\w*|prophec\w*',
        'period': r'19[0-6]0s|noir|cold war|prohibition|wartime|detectives?|gangsters?|speakeas\w*',
        'romance': r'romance|romantic|love story|in love|lovers?|rom-?com|meet-cute|courtship|dating|'
                   r'enemies to lovers|second chance',
        'adventure': r'action|adventures?|treasure|heists?|jungle|expeditions?|mercenar\w*|explorers?|'
                     r'archaeolog\w*|spies|spy|thriller|smugglers?|chase',
    }.items()
}
PRIORITY = list(GENRE_WORDS) + ['modern']
TONE_POOLS = ('romance', 'adventure')

# a character's own people, from words in the role: overrides the story's pool
# for that one character ("the elven archer" in a human fantasy)
RACE_WORDS = [('elven', re.compile(r'\b(elf|elves|elven|elvish)\b', re.I)),
              ('dwarven', re.compile(r'\b(dwarf|dwarves|dwarven|dwarfish)\b', re.I)),
              ('monstrous', re.compile(r'\b(orcs?|orcish|goblins?|trolls?|ogres?|kobolds?|hobgoblins?|gnolls?)\b', re.I))]


def race_pool(role):
    for pool, rx in RACE_WORDS:
        if rx.search(str(role or '')):
            return pool
    return None


# roles that are not people, or not one person: they keep their role
NOT_A_PERSON = re.compile(r"\b(dragon|sword|blade|ai|ship|computer|machine|beast|creature|spirit|ghost|wolf|hound|"
                          r"skeleton|corpse|remains|golem|statue|automaton|construct|idol|wraith|specter|spectre|"
                          r"horse|storm|council|crowd|crew|families|villagers|guards|navy|army|mob|house|tower|"
                          r"system|core|voice|swarm|hive)\b", re.I)


def pool_scores(kernel, *texts):
    return {pool: (0.5 if pool in TONE_POOLS else 1) * (3 * len(re.findall(rx, (kernel or '').lower()))
                                                        + sum(len(re.findall(rx, (t or '').lower())) for t in texts))
            for pool, rx in GENRE_WORDS.items()}


def pool_for(kernel, *texts):
    scores = pool_scores(kernel, *texts)
    best = max(PRIORITY[:-1], key=lambda p: (scores[p], -PRIORITY.index(p)))
    if scores[best] == 0:
        return 'modern'
    if best == 'medieval' and scores['fantasy'] >= scores['medieval']:
        return 'fantasy'
    return best


def gender_hint(role, texts, own=()):
    """'f', 'm' or 'n' from the pronouns in the sentences that mention the
    role, plus every pronoun in the seed's own fields (`own`: its wants,
    edge, tie, voice, breaking point, which are about this person whether
    or not they name the role). Weak evidence on purpose: anything unclear
    gives 'n'."""
    head = re.sub(r"^(the|a|an)\s+", '', role.lower()).split("'")[0].strip()
    if not head:
        return 'n'
    f = m = 0

    def count(sentence):
        nonlocal f, m
        f += len(re.findall(r'\b(she|her|hers|herself)\b', sentence, re.I))
        m += len(re.findall(r'\b(he|him|his|himself)\b', sentence, re.I))

    for text in own:
        count(str(text or ''))
    for text in texts:
        for sentence in re.split(r'(?<=[.;!?])\s+', str(text or '')):
            if head in sentence.lower():
                count(sentence)
    if f > m:
        return 'f'
    if m > f:
        return 'm'
    return 'n'


SEED_OWN_FIELDS = ('wants', 'holds', 'edge', 'tie', 'voice', 'breaking_point')


def premise_texts(premise):
    """The premise's prose, one string per field, for pronoun and genre
    hints. (A JSON dump is one long sentence to the splitter, and every
    pronoun in it would count for every role.)"""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk({k: v for k, v in (premise or {}).items() if k != 'cast_seeds'})
    return out


def head_noun(role):
    """The word a role is about: "the tower warden" -> warden, "the cursed
    talking sword" -> sword, "the keeper of the bridge" -> keeper."""
    words = re.split(r'\s(?:of|in|on|at|from|with|under|behind|beside|by|who|that)\s',
                     re.sub(r"'s\b", '', str(role).lower()))[0].split()
    return words[-1] if words else ''


# made of something no person is made of: "the stone guardian", "the clockwork warden"
NOT_FLESH = re.compile(r"\b(stone|iron|bronze|brass|clockwork|wooden|bone|skeletal|marble|granite|glass|"
                       r"spectral|ghostly|mechanical|crystal|clay)\b", re.I)


def wants_a_name(seed):
    return (isinstance(seed, dict) and seed.get('role') and seed.get('kind') != 'crowd'
            and not NOT_A_PERSON.fullmatch(head_noun(seed['role']))
            and not NOT_FLESH.search(str(seed['role']))
            and re.sub(r'^(the|a|an)\s+', '', str(seed['role']).strip().lower()) not in ('protagonist', 'you', 'player'))


GENDERS = {'f': 'f', 'female': 'f', 'woman': 'f', 'girl': 'f', 'm': 'm', 'male': 'm', 'man': 'm', 'boy': 'm',
           'n': 'n', 'neutral': 'n', 'nonbinary': 'n', 'non-binary': 'n', 'unspecified': 'n', 'any': 'n'}


def seed_gender(seed):
    """The gender the cast step stated for this seed ('f', 'm', 'n'), or None."""
    return GENDERS.get(str((seed or {}).get('gender') or '').strip().lower())


def _feminine(word):
    """Roman women take the feminine form of the family name: Julius -> Julia."""
    return word[:-2] + 'a' if word.endswith('us') else word


def compose(pool, gender, rng):
    """One candidate name in the pool's style, and the parts that must be
    unique within the story (a family name may repeat where the style is
    patronymic or Roman: siblings and clans share it)."""
    style = pool.get('style', 'given_surname')
    if gender == 'n' and not pool.get('n') and style in ('roman', 'patronymic', 'patronymic_of'):
        gender = rng.choice('fm')
    if style == 'roman':
        nomen, cognomen = rng.choice(pool['nomina']), rng.choice(pool['cognomina'])
        if gender == 'f':
            # a Roman woman is called by her family name, so it must be hers alone in the story
            return f'{_feminine(nomen)} {_feminine(cognomen)}', [_feminine(nomen), _feminine(cognomen)]
        return f"{rng.choice(pool['praenomina'])} {nomen} {cognomen}", [cognomen]
    if gender == 'n':
        givens = (pool.get('n') or []) + pool.get('f', []) + pool.get('m', [])
    else:
        givens = (pool.get(gender) or []) + (pool.get('n') or [])
    givens = [g for g in givens if g.lower() not in AVOID] or pool.get('m') or ['Ash']
    given = rng.choice(givens)
    surnames = [x for x in pool.get('surnames') or [] if x.lower() not in AVOID]
    if style == 'single':
        epithets = pool.get('epithets') or []
        if epithets and rng.random() < 0.4:
            return f'{given} {rng.choice(epithets)}', [given]
        return given, [given]
    if style == 'origin':
        return f"{given} of {rng.choice(pool['places'])}", [given]
    if style == 'patronymic':
        father = rng.choice(pool['m'])
        stem = father if father.endswith('s') else father + 's'
        return f"{given} {stem}{'dottir' if gender == 'f' else 'son'}", [given]
    if style == 'patronymic_of':
        father = rng.choice(pool['m'])
        return f"{given} {'daughter' if gender == 'f' else 'son'} of {father}", [given]
    surname = rng.choice(surnames) if surnames else ''
    if style == 'family_first':
        return f'{surname} {given}'.strip(), [given, surname]
    return f'{given} {surname}'.strip(), [given] + ([surname.split()[-1]] if surname else [])


def pick(story_id, role, pool_name, gender, taken):
    """One name not yet taken in this story, drawn deterministically from the
    story id and the role, in the style of the pool (or of the character's
    own people, when the role names one)."""
    pool = POOLS.get(race_pool(role) or pool_name) or POOLS['modern']
    rng = random.Random(f'{story_id}|{role.lower()}')
    used = {part.lower() for name in taken for part in name.split()}
    name = None
    for _ in range(200):
        name, unique = compose(pool, gender, rng)
        if not any(u.lower() in used for u in unique) and name not in taken:
            return name
    return name


def assign_names(seeds, story_id, texts, pool_name=None):
    """Gives every individual seed that is a person a 'name', keeping any it
    already has. texts: the kernel first, then premise text, for the genre
    and for pronoun hints. Returns the pool used."""
    pool_name = pool_name or pool_for(*texts)
    taken = [s['name'] for s in seeds if isinstance(s, dict) and s.get('name')]
    for s in seeds:
        if wants_a_name(s) and not s.get('name'):
            own = [s.get(k) for k in SEED_OWN_FIELDS if s.get(k)]
            gender = seed_gender(s) or gender_hint(str(s['role']), texts, own)
            s['name'] = pick(story_id, str(s['role']), pool_name, gender, taken)
            taken.append(s['name'])
    return pool_name
