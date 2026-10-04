#!/usr/bin/env python3
"""Writes the human reference outlines (*_reference.json) beside the
reference kernels: each story's own structure as one line of an outline, its
beats as nodes, in the pipeline's second-person style, so the 4e judge and
evaluate.py can read it (docs/reference_stories.md). Run from this directory."""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def story(sid, question, title, motivation, ending, nodes, cast):
    ids = [f'N{i:02d}' for i in range(1, len(nodes) + 1)]
    with open(os.path.join(HERE, f'{sid}.txt'), encoding='utf-8') as f:
        kernel = f.read().strip()
    return {
        'story_id': sid, 'stage': 'reference', 'source': 'human, public domain',
        'kernel': kernel,
        'premise': {'mediation': {'question': question}},
        'line_order': ['T1'],
        'lines': {'T1': {'id': 'T1', 'title': title, 'motivation': motivation, 'ending': dict(ending, node=ids[-1]),
                         'path': ids}},
        'node_order': ids,
        'nodes': {nid: {'id': nid, 'beat': n[0], 'title': n[1], 'summary': n[2], 'image': n[3], 'lines': ['T1'],
                        'is_ending': nid == ids[-1]} for nid, n in zip(ids, nodes)},
        'characters': {f'C{i:02d}': dict(c, id=f'C{i:02d}', kind='individual') for i, c in enumerate(cast, 1)},
    }


REFS = [
    story(
        'ref_canterville',
        'Can a family that refuses to be frightened give a ghost what he actually needs?',
        'Love Is Stronger Than Death',
        "You start out amused by the ghost like everyone else in your family; you end up the only one who asks what "
        "he wants, and you go where nobody living has gone to give it to him.",
        {'title': 'The Almond Blossoms',
         'summary': "Sir Simon is buried at last under the almond tree that bloomed when you prayed for him; the house "
                    "is quiet, his jewels are yours, and you keep what you learned in the Garden of Death to yourself.",
         'standing': ['Sir Simon de Canterville', 'the Duke of Cheshire'], 'lost': [],
         'changed': 'the ghost sleeps; the house is still; you have seen what death signifies'},
        [('setup', 'The Stain by the Fireplace',
          "Your father buys Canterville Chase ghost and all, laughing at the warnings. In the library the housekeeper "
          "shows you the blood of Lady Eleanore, murdered in 1575; your brother scrubs it away with Pinkerton's "
          "Champion Stain Remover while thunder shakes the windows and the housekeeper faints.",
          "a bottle of Pinkerton's stain remover on the hearth, thunder over the park"),
         ('inciting_incident', 'Oil Your Chains',
          "At one in the morning the ghost clanks down the corridor in rusty fetters, eyes like burning coals. Your "
          "father, in slippers, asks him to oil his chains and leaves him a bottle of Tammany Rising Sun Lubricator; "
          "the twins pelt him with pillows. Three centuries of terror, and nobody screams.",
          'a small bottle of lubricator on the landing in the moonlight'),
         ('rising', 'The Stain Comes Back',
          "Every morning the stain is back, and every morning a new colour: dull red, then vermilion, then emerald "
          "green. Your family bets on the colour at breakfast. Only you will not join in; it upsets you, and on the "
          "morning it turns green you nearly cry.",
          'an emerald-green bloodstain on the library floor'),
         ('rising', 'Ye Otis Ghoste',
          "The ghost plans his greatest night. Turning a corner he meets a horror with a glowing turnip head and a "
          "placard, and flees shaking. By daylight he finds a bed-curtain, a broom and a hollow turnip, the twins' "
          "work: YE OTIS GHOSTE, Beware of Ye Imitationes.",
          'a hollow turnip with a candle inside, a placard pinned to a bed-curtain'),
         ('midpoint', 'Boo',
          "Butter slides, trip-wires and water jugs over doors: the twins hunt him nightly until he dares only his "
          "duty walks. Dressed as Jonas the Graveless he is ambushed with a shout of BOO and escapes up the chimney, "
          "broken. The family decides he has gone, and the young Duke of Cheshire comes to stay.",
          'soot falling from a cold chimney'),
         ('crisis', 'Poor, Poor Ghost',
          "Coming in with your riding habit torn, you find the ghost alone at a window of the Tapestry Chamber. You "
          "scold him for the stain and for the paints he stole from your box, and then you ask why he cannot sleep. "
          "Three hundred years awake, he says, and a garden where he could rest.",
          'the ghost at the window, your torn riding habit'),
         ('climax', 'The Golden Girl',
          "He shows you the old verse on the library window: when a golden girl can win prayer from the lips of sin, "
          "and the barren almond bears, peace will come to Canterville. You must weep for his sins, pray for his "
          "soul, and face what waits in the dark. You give him your hand, and the wall opens.",
          'the prophecy in old letters on the library window; a wall fading like mist'),
         ('resolution', 'The Almond Blossoms',
          "At midnight you come back down the stairs with a casket of jewels and lead your frightened family to a "
          "hidden room: a skeleton chained to the wall, reaching for an empty trencher. You kneel and pray. Through "
          "the window the twins see the old almond tree in blossom under the moon.",
          'a withered almond tree in blossom under the moon')],
        [{'label': 'the Canterville ghost', 'name': 'Sir Simon de Canterville', 'opposition': True,
          'wants': 'to terrify the new owners as he has everyone for three centuries; underneath, to sleep',
          'edge': 'a vain old actor who rehearses his roles and is wounded by bad reviews',
          'voice': 'archaic and grandiloquent, wounded pride in every line',
          'breaking_point': 'gives up haunting when the twins make him a joke'},
         {'label': 'your father, the American Minister', 'name': 'Hiram B. Otis',
          'wants': 'a fine house and no nonsense', 'edge': 'meets every supernatural terror with a practical product',
          'voice': 'courteous, commercial, unshakeable: "I really must insist on your oiling those chains"'},
         {'label': 'the twins', 'name': 'the Stars and Stripes', 'wants': 'fun',
          'edge': "relentless pranksters, the ghost's real opposition", 'voice': 'a shout of BOO from the dark'},
         {'label': 'the young Duke of Cheshire', 'name': 'Cecil', 'wants': 'to marry you',
          'edge': 'a boy in love, honest and patient', 'voice': 'shy and earnest'}]),

    story(
        'ref_speckled_band',
        "What killed Julia Stoner in a locked room, and can you stop it before it kills her sister?",
        'The Speckled Band',
        "You take a frightened woman's case because it is strange; you end it by turning a murderer's own weapon "
        "back on him.",
        {'title': 'Violence Recoils Upon the Violent',
         'summary': "Dr Grimesby Roylott lies dead in his chair with the swamp adder coiled round his brow; Helen "
                    "Stoner is safe, and you admit you were wrong about the gypsies for a while.",
         'standing': ['Helen Stoner', 'Dr Watson'], 'lost': ['Dr Grimesby Roylott'],
         'changed': 'the plot is uncovered and Helen is free to marry'},
        [('setup', 'A Lady in Black',
          "At a quarter past seven Helen Stoner sits at your fire, veiled and shaking. You tell her she came by an "
          "early train and a dog-cart: the return ticket in her glove, the mud on her sleeve. Her twin died two years "
          "ago in a locked room, crying 'the speckled band'; now Helen hears a whistle at night.",
          'a return ticket tucked in a glove; fresh mud spattered on a sleeve'),
         ('inciting_incident', 'The Whistle at Three',
          "She tells it all: a stepfather who fights the villagers and keeps a cheetah and a baboon; gypsies camped "
          "on the land; the low whistle at three in the morning; the metallic clang; Julia dying in the corridor, "
          "pointing. Now Helen, engaged, sleeps in Julia's room for repairs, and last night she heard it.",
          "Julia's hand pointing down the corridor"),
         ('rising', 'The Bent Poker',
          "Dr Grimesby Roylott fills your doorway, huge and scarred; he followed her. You talk about the crocuses. "
          "He bends your steel poker double, warns you to keep out of his grip, and leaves; you straighten it again. "
          "Now you take the case seriously.",
          'a steel poker bent double, straightened again'),
         ('rising', 'The Will',
          "At Doctors' Commons you read the mother's will: an income of eleven hundred pounds a year, from which each "
          "daughter may claim two hundred and fifty on marrying. Two marriages would cripple him. Julia died a "
          "fortnight before her wedding; Helen is now engaged.",
          "a will open on a clerk's desk, the figures underlined"),
         ('midpoint', 'A Bell-Pull That Rings Nothing',
          "At Stoke Moran you find what the coroner missed: a ventilator into the next room instead of outdoors; a "
          "new bell-rope fixed to a hook, ringing nothing; a bed clamped to the floor beneath both. In Roylott's room, "
          "an iron safe, a saucer of milk and a dog lash tied in a loop.",
          'a bell-rope ending at a hook beside a ventilator'),
         ('crisis', 'The Vigil',
          "You and Watson sit in Helen's darkened room without a light, your cane across your knees, for hours. A "
          "dark-lantern glows through the ventilator; hot metal smells; then a soft, steady hiss, like steam from a "
          "kettle.",
          'a gleam of light through a ventilator in the dark'),
         ('climax', 'You See It, Watson?',
          "You strike a match and lash at the bell-rope with your cane until the thing retreats up through the "
          "ventilator. From the next room comes one long scream of pain, fear and anger together, loud enough to wake "
          "the village.",
          'a match flaring, a cane lashing a bell-rope'),
         ('resolution', 'The Speckled Band',
          "Roylott sits dead by the open safe, a yellow band with brownish speckles round his head. It moves: a swamp "
          "adder, trained with milk, called back with a whistle, sent down the rope to the clamped bed. Your blows "
          "drove it back to its master.",
          "a yellow band with brown speckles round a dead man's brow")],
        [{'label': 'the stepfather', 'name': 'Dr Grimesby Roylott', 'opposition': True,
          'wants': "to keep his dead wife's money by stopping his stepdaughters from marrying",
          'edge': 'a violent, brilliant man of a ruined old family who keeps Indian animals',
          'voice': '"Don\'t you dare to meddle with my affairs... See that you keep yourself out of my grip."'},
         {'label': 'your client', 'name': 'Helen Stoner', 'wants': 'to live long enough to marry',
          'edge': 'terrified, and brave enough to defy him', 'voice': 'level and exact, hands shaking'},
         {'label': 'your companion', 'name': 'Dr Watson', 'wants': 'to stand by you',
          'edge': 'brings his revolver and trusts you in the dark', 'voice': 'plain, loyal, a step behind'}]),

    story(
        'ref_monkeys_paw',
        'If fate punishes those who interfere with it, what do you wish for when the first wish has cost everything?',
        'Three Wishes',
        'You start out wanting a little money to clear the house; you end wanting only to undo what you wished.',
        {'title': 'The Empty Road',
         'summary': "The knocking stops. Your wife opens the door on an empty road and a streetlamp flickering on "
                    "nothing; your son stays dead, and you are the one who made sure of it.",
         'standing': ['Mrs White'], 'lost': ['Herbert White'],
         'changed': 'the money is paid, the son is buried, and the last wish was spent to keep him so'},
        [('setup', 'Check',
          "Laburnam Villa, a raw wet night. You play chess with your son Herbert and lose, because you put your king "
          "into needless danger; you grumble about living at the end of a road nobody else lives on. Your wife knits "
          "by the fire and tells you that you'll win next time.",
          'a chessboard by the fire, the king left open'),
         ('inciting_incident', "The Sergeant-Major's Paw",
          "Sergeant-Major Morris, back from twenty-one years in India, drinks your whisky and tells stories, then "
          "shows you a little mummified paw. An old fakir put a spell on it to show that fate rules lives: three men "
          "can have three wishes. The first man's third wish was for death.",
          'a dried, shrivelled paw on the table'),
         ('rising', 'Out of the Fire',
          "Morris throws the paw on the fire. You snatch it out. He begs you to let it burn, then tells you how to "
          "wish, and warns you to wish for something sensible. Herbert laughs: wish to be an emperor, father, then "
          "you won't be henpecked.",
          'a paw snatched from the coals, smelling of smoke'),
         ('rising', 'Two Hundred Pounds',
          "To clear the house you wish for two hundred pounds. The paw twists in your hand like a snake. Nothing "
          "else happens. Herbert jokes about the money in a bag on the bed and something horrible on the wardrobe; "
          "in the dying fire he sees a monkey's face.",
          'the paw twisting like a snake in your hand'),
         ('midpoint', 'Maw and Meggins',
          "A stranger in good clothes walks past your gate three times before opening it. He is from Maw and "
          "Meggins, where Herbert works. Herbert was caught in the machinery. The firm admits no liability, but in "
          "consideration of your son's services offers a sum: two hundred pounds.",
          'a well-dressed man pacing past the gate three times'),
         ('crisis', 'The Second Wish',
          "A week after the funeral your wife wakes you: the paw! Two wishes left. Wish him alive. You tell her he "
          "was ten days dead, that you knew him only by his clothes. She drags you down to the cold parlour, and you "
          "wish your son alive again.",
          'the paw on the mantelpiece in the cold parlour'),
         ('climax', 'The Knocking',
          "A knock at the door, quiet and stealthy. Your wife runs to it crying that it is Herbert; you hold her; she "
          "breaks free and fights the bolt she cannot reach. Knock after knock shakes the house while you crawl on "
          "the floor, hunting for the paw in the dark.",
          'a bolt at the top of the door, too high for her to reach'),
         ('resolution', 'The Empty Road',
          "You find the paw and breathe your third wish as the bolt slides back. The knocking stops. Your wife's long "
          "wail; you run to her and look out at a quiet, empty road under a flickering lamp.",
          'a streetlamp flickering on an empty road')],
        [{'label': 'the old soldier', 'name': 'Sergeant-Major Morris',
          'wants': 'to be rid of the paw and to warn you',
          'edge': 'has used his three wishes and will not say what they were',
          'voice': '"If you must wish, wish for something sensible."'},
         {'label': 'your son', 'name': 'Herbert White', 'wants': 'to laugh at it all',
          'edge': 'a cheerful mocker of fate', 'voice': '"Well, I don\'t see the money, and I bet I never shall."'},
         {'label': 'your wife', 'name': 'Mrs White', 'opposition': True, 'wants': 'her son back at any price',
          'edge': 'grief that will not be argued with',
          'voice': '"Go down and get it quickly, and wish our boy alive again."',
          'breaking_point': 'turns on you when you refuse the second wish'},
         {'label': 'the man from the firm', 'name': 'the man from Maw and Meggins',
          'wants': 'to deliver his message and leave', 'edge': 'kind, careful, and the messenger of the wish',
          'voice': '"I was asked to say..."'}]),

    story(
        'ref_man_who_would_be_king',
        'Can two loafers make themselves kings, and what does the crown cost the friendship that won it?',
        'Kings of Kafiristan',
        "You start out a partner in a scheme to be king; you end carrying your partner's crowned head home, because "
        "you swore never to leave him.",
        {'title': 'And There the Matter Rests',
         'summary': "You come back to the newspaper office a year later, broken and crippled, with Dravot's head in a "
                    "horsehair bag and his gold crown on it, and you die of the sun a few days after. The head is "
                    "never found.",
         'standing': [], 'lost': ['Daniel Dravot', 'Billy Fish'],
         'changed': 'nothing is left of the kingdom but a story the newspaperman can tell'},
        [('setup', 'Brother to a Prince',
          "On a train in Central India you meet a newspaperman and ask him to carry a message to your partner Dravot "
          "at Marwar Junction. You are loafers who blackmail small native states by posing as correspondents; he gets "
          "you both warned off the border.",
          'a red-bearded man leaning from a train window at Marwar Junction'),
         ('inciting_incident', 'The Contrack',
          "Two years later you and Dravot walk into the newspaperman's office at midnight. India is not big enough "
          "for you: you are going to Kafiristan to be kings. You show him your contract: no liquor, no women, and "
          "stand by each other till the work is done.",
          'the contract on the office table, signed Gentlemen at Large'),
         ('rising', 'The Mad Priest',
          "Dravot goes north as a mad priest with whirligigs to sell, you as his servant, twenty Martini rifles "
          "hidden under the toys. Past Jagdallak, the camels left behind, you walk into a country no Englishman has "
          "seen.",
          'whirligigs and mud toys hiding the rifle barrels'),
         ('rising', 'A God in a Valley',
          "You come down into a valley where two villages fight, and Dravot shoots a man at long range. The people "
          "bow down: he is a god, a son of Alexander. Village by village you drill an army, settle quarrels, and make "
          "chiefs of men like Billy Fish.",
          'a crowd kneeling in the snow before a red-bearded man'),
         ('midpoint', "The Master's Mark",
          "Under an old stone idol the priests find the Master Mason's mark, and when Dravot shows them the secret "
          "signs they take him for a god indeed. He opens a Lodge and makes himself Grand Master. He dreams of an "
          "empire, and of handing it to the Queen.",
          "the Master Mason's mark under a stone idol"),
         ('crisis', 'Keep Clear of Women',
          "Dravot wants a queen and a son. You remind him of the Contrack; Billy Fish says a god may not marry a "
          "mortal girl. He takes one anyway. At the wedding she bites his neck and draws blood: neither god nor "
          "devil, but a man.",
          "a girl's teeth marks bleeding on a king's neck"),
         ('climax', 'The Rope Bridge',
          "The army turns. Billy Fish stays to die with you. Dravot walks out onto the rope bridge in his crown and "
          "asks you to forgive him; you do. He shouts to them to cut, and falls, turning, a long way. They crucify "
          "you between two pines and, when you live, let you go.",
          'a gold crown on a man falling from a cut rope bridge'),
         ('resolution', 'And There the Matter Rests',
          "You crawl back to the newspaper office with Dravot's head in a black horsehair bag, the gold crown on it, "
          "and tell everything. Two days later you are in the road, singing a hymn. You die in the asylum, of the "
          "sun.",
          'a crowned head in a black horsehair bag')],
        [{'label': 'your partner', 'name': 'Daniel Dravot', 'wants': 'to be a king, then an emperor, then a god',
          'edge': 'magnificent, reckless, and convinced of his own divinity',
          'voice': '"I won\'t make a Nation, I\'ll make an Empire!"',
          'breaking_point': 'breaks the Contrack to take a queen'},
         {'label': 'the newspaperman', 'name': 'the narrator', 'wants': 'a quiet night and a story',
          'edge': 'disapproving and fascinated', 'voice': 'dry, decent, ironic'},
         {'label': 'the chief who stands by you', 'name': 'Billy Fish', 'wants': 'to serve his kings',
          'edge': 'loyal past reason', 'voice': 'grave and faithful to the end'},
         {'label': 'the priests', 'name': 'the priests', 'opposition': True, 'wants': 'a god who is truly a god',
          'edge': 'the power that made Dravot and can unmake him', 'voice': '"Neither God nor Devil but a man!"'}]),

    story(
        'ref_lady_with_the_dog',
        'What happens to a man who has never loved when the affair he meant as nothing turns out to be everything?',
        'The Most Complicated Part',
        "You start out wanting a light, brief affair to pass a seaside holiday; you end with the only real thing in "
        "your life hidden in a hotel room, and no idea how to live it.",
        {'title': 'Only Beginning',
         'summary': "Anna comes to Moscow every few months and you meet in her hotel; you are like husband and wife, "
                    "tender friends, and you both know the hardest part is only just beginning.",
         'standing': ['Anna Sergeyevna'], 'lost': [],
         'changed': 'you love for the first time, and your life is split into a public lie and a hidden truth'},
        [('setup', 'A New Arrival on the Front',
          "At Yalta, bored, you notice a fair young woman in a beret walking a white Pomeranian, always alone. You "
          "have had many women and call them the lower race, and you cannot do without them. Here is a fleeting "
          "affair, if you want one.",
          'a white Pomeranian on the seafront'),
         ('inciting_incident', 'Through the Dog',
          "At dinner you call the dog to you, wagging a finger, and it growls. The talk that follows is easy: the "
          "sea, the heat, the boredom. Her name is Anna Sergeyevna; she is married, from S., staying a month. In your "
          "room afterwards you think there is something pathetic about her.",
          'a finger wagged at a growling dog'),
         ('rising', 'The Watermelon',
          "After the first night she sits like a woman in an old painting, weeping that she is wicked, a low woman, "
          "that you will despise her now. You cut a slice of watermelon from the table and eat it slowly, and say "
          "nothing for half an hour.",
          'a slice of watermelon on a hotel table'),
         ('rising', 'Oreanda',
          "At dawn you sit with her on a bench above the sea at Oreanda and listen to it, and think how everything is "
          "beautiful except what we do when we forget our dignity. Then her husband writes; at the station she says "
          "it is right that you part forever.",
          'the sea below Oreanda at dawn'),
         ('midpoint', 'The Sturgeon',
          "Back in Moscow: frost, clubs, banquets. She does not fade: she is in your study, in the street, in every "
          "woman. One night at your club you tell a man about a fascinating woman you met in Yalta; he answers that "
          "the sturgeon was a bit too strong. You cannot stand any of it.",
          'a man at a club saying the sturgeon was a bit too strong'),
         ('crisis', 'The Grey Fence',
          "In December you tell your wife you are going to Petersburg and go to S. instead. Opposite her house runs "
          "a long grey fence studded with nails. You walk up and down it all afternoon, and nobody comes out but "
          "the white dog, with an old servant.",
          'a long grey fence studded with nails'),
         ('climax', 'The Geisha',
          "At the first night of The Geisha you see her come in, small and ordinary in a provincial crowd, and she "
          "fills your whole life. At the interval you find her on a narrow staircase; she is terrified, and she has "
          "thought of nothing but you. She promises to come to Moscow.",
          'a lorgnette in her hand on a gloomy staircase'),
         ('resolution', 'Only Beginning',
          "She comes to Moscow every two or three months and stays at the Slaviansky Bazaar. You have two lives now, "
          "the one everyone sees and the one that is true. Your hair is going grey, and you love for the first time. "
          "How to be free? The hardest part is only beginning.",
          'grey hairs in a hotel mirror')],
        [{'label': 'the lady with the dog', 'name': 'Anna Sergeyevna',
          'wants': 'to live, really live, instead of the life she married into',
          'edge': 'ashamed of what she wants and unable to stop wanting it',
          'voice': 'quick and frightened, calling herself low and wicked one moment, clinging the next',
          'breaking_point': 'tells you it is right that you part forever'},
         {'label': 'her husband', 'name': 'von Dideritz', 'opposition': True,
          'wants': 'respectability', 'edge': 'the flunkey she married, tall, stooping, bowing',
          'voice': 'a little bow at every word'},
         {'label': 'your wife', 'name': 'your wife', 'wants': 'a cultured house',
          'edge': 'thinks of herself as intellectual; you think her narrow', 'voice': 'calls you Dimitri'}]),
]

if __name__ == '__main__':
    for r in REFS:
        with open(os.path.join(HERE, f"{r['story_id']}_reference.json"), 'w', encoding='utf-8') as f:
            json.dump(r, f, indent=1, ensure_ascii=False)
        words = [len(n['summary'].split()) for n in r['nodes'].values()]
        print(f"{r['story_id']}: {len(r['nodes'])} nodes, summaries {min(words)}-{max(words)} words")
