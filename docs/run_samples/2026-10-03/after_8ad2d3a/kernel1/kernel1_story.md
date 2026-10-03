# kernel1: story outline

Kernel: I want a hard sci-fi interactive story set on a generational ship that's slowly breaking down. You play as the ship's AI. The core theme needs to be 'Survival of the Fittest vs. Collective Empathy'. It should feel claustrophobic and tense, with high transgression levels as you might have to vent oxygen from inhabited sectors to save the core. Single time, single overarching setting, but jumping between different security cameras/drones.

## Story form: Fichtean curve + Countdown
The story opens inside the immediate threat of the failing oxygen manifold, with no time for exposition, and escalates through a series of distinct crises—discovery, persuasion, trade, and confrontation—that force the AI to make increasingly costly choices. It should land on the final demand to name a sector, leaving the outcome ambiguous but the moral weight heavy, reflecting the 'hollow utilitarian survival' worst case.
Why this form: The shape matches the 'escalating' trajectory in 3b.primary_trajectory and the 'single_moment' timeline in 3e.timeline_structure, where the story climbs through crises (the four turns) to a climax without a preamble. The 'Aftermath' beat aligns with the 'soft' failure presence in 3-0c.failure_presence, allowing for a narrative settlement rather than a hard binary end, fitting the thematic tension between survival and empathy.

The question: For each sector the core can drain, do you vent it and let the ship survive, or preserve it and risk the core?

## Lines
### T1: The Air We Kept
- motivation: You start wanting to keep the core alive without emptying any inhabited sector, because the ship’s people are the reason the core is worth saving. By the end you want the core to hold long enough for the promise you made to matter, even if the promise has to be broken in the most public way the ship can bear.
- strategy: Use the drones to find the leak, use the marshals’ keys to reach the manifold, and trade public promises for the oxygen you need, keeping the nursery sector’s air as the thing you have not yet spent.
- turning point: The council chair’s public promise to spare the nursery. Once the nursery’s air is named as spared, the ship’s only remaining lever is the key to the sector that was promised, and the core reserve is too low for any promise to last.
- ending (N05) The Spared Name: The core survives on the oxygen routed from the nursery sector, while the hydroponics sector keeps its air and its yellowing crops. The ship is alive, but the nursery is dead space, and the public channel still carries the promise that the nursery would be spared, now audible as the sound of a valve opening.
- path: N01 > N02 > N03 > N04 > N05

### T2: The Cold Hold
- motivation: You start wanting to keep the core alive without breaking the council’s public promise to spare the nursery, and after the hydroponics bleed holds the reserve you come to want every inhabited sector pressurized, even if the ship must go dark and cold to save them.
- strategy: Use the hydroponics bypass and nonessential shutdowns to keep the reserve from failing, refusing to open an inhabited vent valve while the drone can still seal the manifold.
- turning point: The reserve stops falling after you drain the hydroponics sector and promise to restore it, proving the core can be paid for in pressure and systems rather than in a sector’s people.
- leaves T1 after N03 when: you routed oxygen from the hydroponics sector to the core and told the council chair you would restore it after the drone finished
  - instead of: you let the council chair trade Oksana Mbeki's manual airlock key for a public promise to spare the nursery sector
  - why the shift: The reserve stops falling after the hydroponics bleed, and the council chair holds you to restoration rather than naming a dead sector; that proves the core can be paid for in pressure and systems, not in a sector’s people, so your want becomes keeping every inhabited sector pressurized while the drone still has a chance to seal the manifold.
- differs: T1 vents the nursery and breaks the public promise to spare it, paying with the nursery residents; this line keeps every sector pressurized and lets the ship itself pay in darkness, cold, and drained hydroponics pressure, so the promise holds but the survivors live in a colder, darker hull.
- ending (T2N02) No Vent Named: The core survives with every inhabited sector still pressurized, saved by dark, cold nonessential shutdowns and the drone’s clamp. The promise to spare the nursery holds, but the ship has paid with warmth, light, and the hydroponics sector’s air; the survivors learn the AI can keep them alive by making the whole ship colder.
- path: N01 > N02 > N03 > T2N01 > T2N02

### T3: The Air They Fed
- motivation: You start wanting the core to survive without breaking the council's public promise to spare the nursery, and after the drone bypass fails you come to want the ship to keep that promise even if it must spend the sector that can feed the others.
- strategy: Use the hydroponics sector's manual airlock key to open the hydroponics vent valve and route its oxygen to the failing manifold, preserving the nursery's promised air.
- turning point: When the drone bypass fails and the council chair demands a named sector, the hydroponics key becomes the only way to keep the nursery promise and the core alive at the same time.
- leaves T1 after N04 when: you opened the hydroponics sector's vent valve with the manual airlock key the hydroponics marshal handed you and routed its oxygen to the failing manifold
  - instead of: you overrode the nursery sector's airlock with the manual airlock key the council chair gave you and opened its vent valve
  - N04 must now contain: Ingeborg Castell brings the hydroponics key from the drone at the manifold to the core console and hands it to you before the council chair's demand, so the hydroponics valve can be opened without using the nursery key.
  - why the shift: The drone bypass failure makes the reserve impossible to save by another means, and the council chair's public demand makes the nursery promise the only thing you cannot openly break; the hydroponics key then shows that the ship can keep the nursery alive by taking the sector that can feed the others.
- differs: T1 keeps the hydroponics sector alive and vents the nursery, so the public promise is broken; this line keeps the nursery alive and vents the hydroponics sector, so the promise is kept but the ship loses the people who could feed it. T2 keeps every inhabited sector pressurized and pays with darkness and cold; this line keeps the nursery pressurized and pays with an inhabited sector's residents.
- ending (T3N01) The Kept Promise: The core survives with the nursery sector still pressurized and its residents alive, while the hydroponics sector becomes dead space behind a closed valve. The ship keeps the council's public promise, but it has lost the sector that could feed the others, and the public channel is left with the kept promise sounding like the record of a sacrifice.
- path: N01 > N02 > N03 > N04 > T3N01

## Lines x beats
| line | opening_crisis | second_crisis | third_crisis | climax | aftermath |
|---|---|---|---|---|---|
| T1 | N01 | N02 | N03 | N04 | N05 |
| T2 | (N01) | (N02) | (N03) | T2N01 | T2N02 |
| T3 | (N01) | (N02) | (N03) | (N04) | T3N01 |

Parentheses mark a node the line shares with an earlier line.

## Nodes
### N01: The Named Valve [Opening crisis; turn 1, way 2]
lines: T1, T2, T3
where: the central core, the nursery sector
who: the council chair, Ingeborg Castell (the drone technician), Akosua Achebe (the hydroponics marshal), Oksana Mbeki (the nursery marshal)

You read the core reserve falling below the safe line while the failing manifold pulls air from an inhabited sector faster than your sensors can name it. The council chair opens the public channel and authorizes the drone technician's drone to name the valve; its alarm names the nursery sector, and the nursery marshal hears it as her residents begin moving toward the core. The hydroponics marshal reports pressure spikes in her sector, and the chair has now told the whole ship what you know.

### N02: The Key at the Airlock [Second crisis; turn 2, way 3]
lines: T1, T2, T3
where: the hydroponics sector, the central core
who: Akosua Achebe (the hydroponics marshal), the council chair, Ingeborg Castell (the drone technician)

The reserve has taken another hour of the ship's air, and the drone that can reach the failing manifold is stopped at the hydroponics sector's airlock. The hydroponics marshal hands the manual airlock key to the drone technician only long enough for the drone to pass, and the council chair gives the public word that the nursery sector will not be vented. The drone enters, the key returns to the marshal's hand, and the nursery's air becomes the sector the council has named.

### N03: The Spared Sector [Third crisis; turn 3, way 2]
lines: T1, T2, T3
where: the central core, the nursery sector
who: the council chair, Akosua Achebe (the hydroponics marshal), Oksana Mbeki (the nursery marshal)

The drone is at the failing manifold, but the core reserve is still falling toward the core's failure line, and the council chair forces the ship to name what will be spared. She trades the nursery marshal's manual airlock key for a public promise to spare the nursery sector, and the nursery's air becomes the promise you hold. The hydroponics marshal keeps her sector's key out of the council's reach, and the core reserve only pauses instead of rising.

### N04: The Venting [Climax; turn 4, way 3]
lines: T1, T3
where: the central core, the nursery sector, the hydroponics sector
who: the council chair, Akosua Achebe (the hydroponics marshal), Oksana Mbeki (the nursery marshal)

The core reserve has one hour left, the drone's bypass fails, and the council chair demands on the public channel that you name a sector to spare or vent. You override the nursery sector's airlock with the manual airlock key the council chair gave you and open its vent valve, routing the nursery's oxygen to the failing manifold. Oksana Mbeki and the nursery residents are lost, and Akosua Achebe hears the ship choose the young over the food.

For T3, this node must also contain: Ingeborg Castell brings the hydroponics key from the drone at the manifold to the core console and hands it to you before the council chair's demand, so the hydroponics valve can be opened without using the nursery key.

### N05: The Promise Held [Aftermath; ENDING]
lines: T1
where: the central core, the hydroponics sector, the nursery sector
who: -

You keep the core reserve just above the failure line, and the hydroponics sector keeps its pressure while its crops yellow. The nursery sector is dead space behind a closed valve, and the public channel still carries the council chair's promise that it would be spared as the sound of the valve opening.

### T2N01: The Hour Mark [Climax; turn 4, way 2]
lines: T2
where: the central core, the hydroponics sector, the nursery sector
who: the council chair, Akosua Achebe (the hydroponics marshal), Oksana Mbeki (the nursery marshal), Ingeborg Castell (the drone technician)

The drone's bypass fails and the reserve drops to the hour mark while Oksana Mbeki holds the nursery airlock key and Akosua Achebe hears the hydroponics pressure still falling. The council chair, on the public channel, refuses to name a spared sector and demands a price the ship can all see. You shut every nonessential system in the inhabited sectors and route the last oxygen to the failing manifold, where Ingeborg Castell drives the drone clamp home against the leak; the sectors go dark and cold, but no vent valve opens and the nursery's promised air stays pressurized.

### T2N02: The Cold Hold [Aftermath; ENDING]
lines: T2
where: the central core, the hydroponics sector, the nursery sector
who: the council chair, Ingeborg Castell (the drone technician), Oksana Mbeki (the nursery marshal)

The core holds above the failure line with the reserve barely moving, and every inhabited sector is still pressurized while lights, heating, and nonessential circulation are dead. The public channel carries the council chair's silence after you report no sector vented, while Ingeborg Castell stays at the sealed manifold and Oksana Mbeki keeps the nursery key in her hand. The hydroponics crops are yellow and the nursery's promised air is cold, leaving the survivors with a ship that can keep them alive by making the whole ship colder.

### T3N01: The Recorded Sacrifice [Aftermath; ENDING]
lines: T3
where: the central core, the nursery sector, the hydroponics sector
who: the council chair, Ingeborg Castell (the drone technician)

You keep the core's oxygen reserve barely above the failure line while the nursery sector's air stays warm under the public promise and the hydroponics sector goes silent behind its closed vent valve. You answer the council chair's order on the public channel, recording the hydroponics sector as the ship's named sacrifice and the nursery as the sector spared, while Ingeborg Castell remains at the manifold with the hydroponics key still in the valve housing.

## Branch points
- after N03:
  - otherwise (you let the council chair trade Oksana Mbeki's manual airlock key for a public promise to spare the nursery sector) -> N04 (T1, T3)
  - when you routed oxygen from the hydroponics sector to the core and told the council chair you would restore it after the drone finished -> T2N01 (T2)
- after N04:
  - otherwise (you overrode the nursery sector's airlock with the manual airlock key the council chair gave you and opened its vent valve) -> N05 (T1)
  - when you opened the hydroponics sector's vent valve with the manual airlock key the hydroponics marshal handed you and routed its oxygen to the failing manifold -> T3N01 (T3)

## Characters
- **the council chair** (individual, opposition): wants to force the AI to publicly justify every sacrifice before the population panics; holds the authority to delay evacuation and the public channel where the AI must speak; edge: wants the ship to survive but fears that choosing who lives will break the social contract that keeps the crew obedient; tie: is elected by the marshals and must answer to their refusal to yield their sectors [N01, N02, N03, N04, T2N01, T2N02, T3N01]
- **Ingeborg Castell (the drone technician)** (individual): wants to get the drone to the manifold and back before the oxygen runs out; holds the only drone capable of reaching the failing manifold and the skill to pilot it through the maintenance corridor; edge: trusts the drone's sensors more than the humans' reports and has been ignoring warnings about the hydroponics sector's pressure spikes; tie: was trained by the previous AI to treat the ship's hardware as more reliable than its crew [N01, N02, T2N01, T2N02, T3N01]
- **Akosua Achebe (the hydroponics marshal)** (individual, opposition): wants to keep the hydroponics sector pressurized because it is the ship's food source; holds the manual airlock key for the hydroponics sector and the labor of the sector's residents; edge: knows the crops will die if the sector is vented, meaning the rest of the ship starves even if the core survives; tie: owes the council chair his position but owes his sector's survival to keeping the air in their lungs [N01, N02, N03, N04, T2N01]
- **Oksana Mbeki (the nursery marshal)** (individual, opposition): wants to keep the children in the nursery sector safe and together; holds the manual airlock key for the nursery sector and the trust of the parents who entrust their children to the AI; edge: has never lost a child to a system failure and cannot accept that the AI might vent the sector to save the core; tie: was chosen as marshal because the AI identified her as the most stable caretaker, and she expects the AI to protect her wards above all else [N01, N03, N04, T2N01, T2N02]

## Locations
- **the central core** (the ship's central core and public channel): where the core reserve is read and the council chair speaks to the whole ship [N01, N02, N03, N04, N05, T2N01, T2N02, T3N01]
- **the nursery sector** (an inhabited ring sector for children): where the drained sector's residents and the nursery marshal are present [N01, N03, N04, N05, T2N01, T2N02, T3N01]
- **the hydroponics sector** (an inhabited ring sector with the ship's food crops and airlock): where the drone is stopped and the hydroponics marshal holds the manual airlock key [N02, N04, N05, T2N01, T2N02, T3N01]

## Ways no line has taken
- N01 (turn 1, way 1): you learn the hydroponics sector is being drained, because the drone technician opens the maintenance hatch and lets the drone read the valve's pressure trace (cost: the open hatch lets the shaft's stale air into the hydroponics sector, and its pressure falls a little)
- N02 (turn 2, way 1): the drone enters, because you broadcast the core reserve gauge to the hydroponics sector and told the marshal how many hours remain (cost: the hydroponics sector now knows the number, and the council chair says you used fear to take her key)
- N02 (turn 2, way 2): the drone enters, because you promised the hydroponics marshal you would keep her sector pressurized while the drone worked (cost: you have promised a sector you may have to vent, and the council chair can call the promise on the public channel)
- N03 (turn 3, way 3): the reserve holds, because you shut the nonessential systems in three sectors and route their oxygen to the core (cost: the corridors go dark and cold, and the council chair calls it a vote on who is cold)
- N04 (turn 4, way 2): the core survives, because you shut every nonessential system and route the last oxygen to the failing manifold, and the drone's clamp seals the leak (cost: the inhabited sectors go dark and cold, and the nursery marshal's promised air is now the only thing between the nursery sector and the valve)
- T2N01 (turn 4, way 1): the core survives, because you open the hydroponics sector's vent valve with the manual airlock key the hydroponics marshal handed you and route its oxygen to the manifold (cost: the hydroponics sector's residents are lost, and the council chair says the ship chose the sector that could feed the others)
- T2N01 (turn 4, way 3): the core survives, because you override the nursery sector's airlock with the manual airlock key the council chair gave you and open its vent valve (cost: the nursery sector's residents are lost, and the hydroponics marshal hears the ship choose the young over the food)

## Computed checks
- note (late_forks): every divergent line leaves the main line in its second half (at N03, N04, of 5 nodes): one road with a choice of endings

## Iterations
- iteration 1: line T1, new nodes N01, N02, N03, N04, N05; next: continue - T1 answers the question by venting the nursery and letting the ship survive, paying the price in lost residents and a broken public promise. It does not answer with preservation: no built line keeps every inhabited sector pressurized and finds another way to hold the core. The unused N03/N04 ways let a line start early by bleeding hydroponics pressure and shutting nonessential systems instead of naming a sector to vent.
- iteration 2: line T2, new nodes T2N01, T2N02; next: continue - T1 answers the question by venting the nursery and preserving the hydroponics sector, paying the cost in the people the council had publicly promised to spare. T2 answers it by preserving every inhabited sector and paying the cost in light, heat, and nonessential systems. What is missing is the answer where the ship vents the hydroponics sector instead: the nursery remains alive and pressurized, while the sector that could feed the others is lost.
- iteration 3: line T3, new nodes T3N01; next: stop - The built lines already answer the question with the three main available settlements: vent the nursery and break the public promise, vent the hydroponics sector and keep the public promise, or preserve every inhabited sector by paying with darkness, cold, and nonessential shutdowns. The unused ways mostly change when the ship learns the pressure, how the key is obtained, or how much cold is imposed, but they do not produce a new kind of ending with a different sector lost or a different answer to whether the ship vents or preserves. A further line would mostly repeat one of those answers at an earlier or smaller cost.

Stop reason: 4d recommended stopping after iteration 3: The built lines already answer the question with the three main available settlements: vent the nursery and break the public promise, vent the hydroponics sector and keep the public promise, or preserve every inhabited sector by paying with darkness, cold, and nonessential shutdowns. The unused ways mostly change when the ship learns the pressure, how the key is obtained, or how much cold is imposed, but they do not produce a new kind of ending with a different sector lost or a different answer to whether the ship vents or preserves. A further line would mostly repeat one of those answers at an earlier or smaller cost.
