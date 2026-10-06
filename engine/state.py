"""Game state: everything that changes during play, and nothing else.

The story package is read-only; this is the part a save holds and a rewind
restores. Arc states are kept as two counts (up and down), not a net value,
so a condition can ask for a pattern of play rather than a sum.
"""

import copy
import random


class GameState:
    def __init__(self):
        self.scene = None             # current scene id
        self.room = None              # the player's room
        self.ending = None            # set when an ending is reached
        self.flags = {}
        self.stats = {}
        self.arcs = {}                # state name -> {'up': n, 'down': n}
        self.locations = {}           # object id -> room id, character id, 'player' or None
        self.placements = {}          # character id -> room id (set by the scene)
        self.visited = set()          # rooms and scenes entered
        self.used = set()             # interaction ids of `once` interactions already used
        self.fired = set()            # event and nudge ids already fired
        self.seen = set()             # characters and objects the player has encountered
        self.heard = set()            # what the player has read: examined, asked, thought; 'room:<id>' described
        self.introduced = set()       # characters whose names the player has learned
        self.moments = {}             # moment id -> actions since its options were first offered
        self.turns = 0                # time that has passed (actions that changed something, moves, waits)
        self.turns_in_scene = 0
        self.idle = 0                 # actions in this scene since one last changed anything
        self.actions = 0              # every action taken, timed or not
        self.seed = random.random()

    # ------------------------------------------------------------ reads

    def arc(self, name):
        a = self.arcs.get(name) or {}
        return a.get('up', 0), a.get('down', 0)

    def stat(self, name):
        """A stat; `<state>_up` and `<state>_down` read an arc state's counts."""
        for direction in ('up', 'down'):
            base = name[:-len(direction) - 1]
            if name.endswith('_' + direction) and base in self.arcs:
                return self.arcs[base].get(direction, 0)
        return self.stats.get(name, 0)

    def where_is(self, character_id):
        return self.placements.get(character_id)

    # ------------------------------------------------------------ writes

    def move_arc(self, name, direction):
        a = self.arcs.setdefault(name, {'up': 0, 'down': 0})
        a['up' if direction == 'up' else 'down'] += 1

    def new_seed(self):
        self.seed = random.random()

    # ------------------------------------------------------------ saves

    def clone(self):
        c = GameState.__new__(GameState)
        c.__dict__.update(self.__dict__)
        for key in ('flags', 'stats', 'locations', 'placements'):
            setattr(c, key, dict(getattr(self, key)))
        for key in ('visited', 'used', 'fired', 'seen', 'heard', 'introduced'):
            setattr(c, key, set(getattr(self, key)))
        c.arcs = {k: dict(v) for k, v in self.arcs.items()}
        c.moments = dict(self.moments)
        return c

    def to_dict(self):
        return {'scene': self.scene, 'room': self.room, 'ending': self.ending, 'flags': dict(self.flags),
                'stats': dict(self.stats), 'arcs': copy.deepcopy(self.arcs), 'locations': dict(self.locations),
                'placements': dict(self.placements), 'visited': sorted(self.visited), 'used': sorted(self.used),
                'fired': sorted(self.fired), 'seen': sorted(self.seen), 'heard': sorted(self.heard), 'introduced': sorted(self.introduced), 'moments': dict(self.moments),
                'turns': self.turns, 'turns_in_scene': self.turns_in_scene,
                'idle': self.idle, 'actions': self.actions, 'seed': self.seed}

    @staticmethod
    def from_dict(data):
        s = GameState()
        for key in ('scene', 'room', 'ending', 'turns', 'turns_in_scene', 'idle', 'actions', 'seed'):
            setattr(s, key, data.get(key, getattr(s, key)))
        s.flags = dict(data.get('flags') or {})
        s.stats = dict(data.get('stats') or {})
        s.arcs = copy.deepcopy(data.get('arcs') or {})
        s.locations = dict(data.get('locations') or {})
        s.placements = dict(data.get('placements') or {})
        s.visited = set(data.get('visited') or [])
        s.used = set(data.get('used') or [])
        s.fired = set(data.get('fired') or [])
        s.seen = set(data.get('seen') or [])
        s.heard = set(data.get('heard') or [])
        s.introduced = set(data.get('introduced') or [])
        s.moments = dict(data.get('moments') or {})
        return s
