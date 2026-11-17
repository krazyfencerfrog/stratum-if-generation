# Can Stratum write a story worth playing?

Follow-up to [Fable request 6](fable_request_6.txt) and its [response](fable_response_6.md), based on *The Housekeeper’s Reckoning*, the saved snowbound murder mystery.

I think the project is worth pursuing. I would change what the next run tries to prove. A frontier model invented a good use for the housekeeper’s expertise. She can look at a candle in a gentleman’s study and recognize that it came from below stairs. The engine can remember whether she took it and can make that matter hours later. The open question is whether the writer can make me *want* to spend those hours in this house. The saved run gives me moments of curiosity, but I wouldn’t play it a second time for the pleasure of anyone’s company.

## Why the story feels flat

At dinner, the housekeeper threatens to keep Millicent’s sherry glass until she gives up the hour of her visit. In the gallery, the housekeeper threatens to bring the valet’s candle box before the heir unless he gives up an hour. The details are specific and the threats make sense. Yet two very different relationships give the player much the same experience. Once I recognize the pattern, I know what everyone is for. [Dinner and gallery scenes in the generated outline](runs/kernel38_fable_2026-10-28/run/kernel38_fable_story.md#nodes)

The detail I’d follow is Fairbrother setting out two pairs of boots, one for a dead man. Is it habit? Does he need one more morning of being someone’s valet? What would he do if the new housekeeper quietly put the boots away? For a moment he has a life I can wonder about. There’s already material like this in the run. The story gives it little room to develop. [Stage A observations in the original review](fable_response_6.md#stage-a-arcs-and-minor-nodes)

The prompts help explain that result. Step 4a commissions the canonical telling and defers how it will be played. By the time the scene writer has people together in a room, it must render the actions selected upstream in exactly the prescribed number and order. The outline judge looks for losses, plants, payoffs, and reversals. Those checks can catch an empty outline. They can also all pass when the second conversation feels just like the first. The pipeline commits to writing fifteen rooms before anyone has played one dinner worth keeping. [Main-line prompt](../prompts/s4a_main_line.prompt) · [Scene prompt](../prompts/s7d_scene.prompt) · [Outline judge](../prompts/s4e_outline_judge.prompt)

## What the replay established

I followed two routes from the opening through the main drawing-room scene using actions offered by the engine. Each took 24 actions.

| Route | What I did | What the game remembered in the ending |
| --- | --- | --- |
| Took the stub | Pocketed it and left Fairbrother room to testify in his own words. | The Major was taken away. The ending credited the valet’s confession and described the candle-end in my apron. |
| Left the stub | Left it upstairs and asked Fairbrother to put more coal on the fire. | The same verdict, confession, and candle-end in my apron. At dinner I had even been offered the option to turn out the apron “stub and all.” |

Response 6 identifies the missing connection between evidence and verdict. One engineering detail changes the remedy. The generated package already has portable evidence and a `show` action. The compiler sets `reach: any` on onward actions and moment options, bypassing the ordinary object-reachability check. I could show Fairbrother the candle box without fetching it. A player can reasonably decide to accuse someone with weak evidence. Showing a particular box should require access to that box. The game can honor both rules. [Saved package](runs/kernel38_fable_2026-10-28/run/kernel38_fable_package_draft.json) · [Scene compiler](../generator/compile_scenes.py)

I changed the main drawing room in an in-memory copy to allow seven accusations. For this test, the room accepted the accusation against the Major if the housekeeper held the stub and Fairbrother had testified voluntarily. All 28 combinations of suspect, possession, and testimony produced the intended outcome through ordinary play, and the modified package passed validation. I chose that simple proof rule to test the runtime. A fair mystery still needs an inference that distinguishes the killer from an innocent visitor who used the same candle.

The original playtest reached all three authored endings. Thirteen of sixteen scenes hit the search cap, and the drawing room was explored from eight of 266 observed entry states. The result establishes that the endings can be reached. Whether a player arrives with a theory, cares what becomes of Fairbrother, or wants another turn requires a different test. [Saved playtest report](runs/kernel38_fable_2026-10-28/run/kernel38_fable_package.md#playtest-log)

## A dinner I would try

This is a sketch for the same kernel, written for this review.

> The Major proposes that everyone repeat exactly what they did last night. Somebody has to play the dead man. He gives you the part because, he says, the servants were coming and going anyway.
>
> You sit in the master’s chair. Fairbrother slips a cushion behind your back. He does it before either of you has time to be embarrassed.
>
> “Now ring for the sherry,” says the Major.
>
> Under the arm of the chair are two bellpulls. In a fortnight downstairs you have only ever heard one.

I want to try the other bell. I also want to hold out the empty glass and see who gets up without being rung for. The Major has lent the least powerful person in the house the master’s authority for as long as she can keep the reconstruction going. The cushion tells me something about Fairbrother I would never have thought to ask. There’s a reason to play this scene before I know whether either bell will help solve the murder.

## What I’d test next

1. **Give both models a direct-writing baseline.** Give the local 27B model and the frontier model the same kernel, a ten-minute length target, numbered choices, and room for an ending. Make a few independent attempts with each. Play them alongside a similar-length stretch of the current game with the source labels hidden. The local model’s shipboard AI in *The Red Line* already faces a legible choice between protecting the core and counting the people still in the atrium. That earns the local model a trial. Neither model has yet demonstrated reliable, unattended generation of a whole story readers enjoy. [Local example](../examples/kernel1_the_red_line.json)
2. **Choose among playable scenes before expanding one.** Try three different openings. Ask readers where they first wanted to do something of their own accord, which person they wanted another minute with, and whether they would keep playing on their own time. Let them put all three down. If readers prefer the direct drafts, trace what disappears as a favorite scene passes through planning and compilation. If they put down the direct drafts too, work on invention and selection before adding stages. Reader comparisons during development can later test whether an automated selector is good enough for offline generation.
3. **Carry the winning scene forward intact.** Preserve the actual exchange, playable actions, and character behavior. Write far enough beyond it to see a consequence. The next scene after the reconstruction might be the housekeeper and Fairbrother putting the room back in order. Give that scene a chance to earn its place before commissioning the rest of the house.
4. **Then connect the scenes that work.** Give consequential objects, discoveries, and testimony stable identities across outline, world, dialogue, and endings. Keep separate records of what happened, what the player learned, and what the household can be persuaded to believe. Reuse the fixed dinner and thaw wherever they serve the story. Leave the identity of the accused in the player’s hands. Repeat the experiment on the [canal-boat ghost kernel](../tests/kernels/kernel35.txt), where the interesting consequence might be whether the captain will cast off after seeing how you treated your brother-in-law.

I’d spend the next generation budget on the first two experiments. The small verdict test answered the immediate engineering question. The more consequential result would be a reader reaching the end of ten minutes and asking to play the next scene.
