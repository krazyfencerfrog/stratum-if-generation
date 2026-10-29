# kernel38_fable: the compiled package

## Stage C
- C: scene S_N04: the stair head (stair_head) was out of reach; joined it to the dining room (dining_room)
- C: scene S_T2N04: the study (study) was out of reach; joined it to the drawing room (drawing_room)
- C: scene S_T3N02: the library (library) was out of reach; joined it to the stair head (stair_head)
- C: scene S_T3N05: the housekeeper's room (housekeeper_s_room) was out of reach; joined it to the drawing room (drawing_room)

## Engine validator
- no errors
- note flag 'done_N04b' is set but nothing reads it
- note flag 'done_N05b' is set but nothing reads it
- note flag 'done_N06b' is set but nothing reads it
- note flag 'done_N07' is set but nothing reads it
- note flag 'done_N07b' is set but nothing reads it
- note flag 'done_T2N01c' is set but nothing reads it
- note flag 'done_T3N02c' is set but nothing reads it
- note flag 'done_T3N03c' is set but nothing reads it
- note flag 'done_T3N03d' is set but nothing reads it
- note flag 'done_T3N03e' is set but nothing reads it
- note flag 'done_T3N03f' is set but nothing reads it
- note story verb 'walk' is used by one interaction only (S_N01.a2): it may point at the solution
- note story verb 'shut' is used by one interaction only (S_N02.N02b.3): it may point at the solution
- note story verb 'empty' is used by one interaction only (S_N02.N02c.1): it may point at the solution
- note story verb 'knock' is used by one interaction only (S_N03.N03c.3): it may point at the solution
- note story verb 'lead' is used by one interaction only (S_N05.N05a.2): it may point at the solution
- note story verb 'keep' is used by one interaction only (S_N05.N05a.3): it may point at the solution
- note story verb 'hold' is used by one interaction only (S_N06.N06c.1): it may point at the solution
- note story verb 'lock' is used by one interaction only (S_N07.a4): it may point at the solution
- note story verb 'rake' is used by one interaction only (S_T2N01.T2N01b.3): it may point at the solution
- note story verb 'unfold' is used by one interaction only (S_T2N01.a2): it may point at the solution
- note story verb 'drink' is used by one interaction only (S_T2N02.T2N02b.3): it may point at the solution
- note story verb 'follow' is used by one interaction only (S_T2N02.a1): it may point at the solution
- note story verb 'search' is used by one interaction only (S_T2N03.T2N03b.3): it may point at the solution
- note story verb 'check' is used by one interaction only (S_T3N01.T3N01b.3): it may point at the solution
- note story verb 'leave' is used by one interaction only (S_T3N03.T3N03a.2): it may point at the solution
- note story verb 'slip' is used by one interaction only (S_T3N03.T3N03c.3): it may point at the solution
- note story verb 'put' is used by one interaction only (S_T3N03.T3N03d.n): it may point at the solution

## Playtest Reachability
- States explored: 289105
- Scenes: 16/16 (100%)
- Endings: 3/3 (100%)
- Stuck states: 0

## Playtest Log
```
The Housekeeper's Reckoning: explored scene by scene, 289105 states over 16 of 16 scenes
  S_N01         10457 states from 1 entry state(s); leads to S_N02, S_T3N01
  S_N02         20000 states from 8 entry state(s) (stopped at the limit); leads to S_N03
  S_T3N01       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T3N02
  S_N03         20000 states from 8 entry state(s) (stopped at the limit); leads to S_N04, S_T2N01
  S_T3N02       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T3N03
  S_N04         20000 states from 8 entry state(s) (stopped at the limit); leads to S_N05
  S_T2N01       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T2N02
  S_T3N03       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T3N04
  S_N05         20000 states from 8 entry state(s) (stopped at the limit); leads to S_N06
  S_T2N02       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T2N03
  S_T3N04       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T3N05
  S_N06         20000 states from 8 entry state(s) (stopped at the limit); leads to S_N07
  S_T2N03       20000 states from 8 entry state(s) (stopped at the limit); leads to S_T2N04
  S_T3N05        7664 states from 8 entry state(s); leads to E_T3N05
  S_N07         10984 states from 8 entry state(s); leads to E_N07
  S_T2N04       20000 states from 8 entry state(s) (stopped at the limit); leads to E_T2N04
  ending E_T3N05 (The Keyhole Filled): 2 resolution combination(s), shortest in 20 actions
  ending E_N07 (The Carriage Takes the Major): 4 resolution combination(s), shortest in 25 actions
  ending E_T2N04 (The Wrong Passenger): 3 resolution combination(s), shortest in 25 actions
play styles:
  random                 200 runs: none; mean None actions; 200 unfinished
      shift S_N03 -> S_T2N02: 0%
  seek                   50 runs: E_N07 46, E_T2N04 4; mean 39.5 actions
      shift S_N03 -> S_T2N02: 0%
  seek:branch            50 runs: E_T3N05 50; mean 35.4 actions
  up                     50 runs: E_T2N04 47, E_T3N05 3; mean 44.2 actions
      shift S_N03 -> S_T2N02: 100%
  down                   50 runs: E_N07 49, E_T3N05 1; mean 63.8 actions
      shift S_N03 -> S_T2N02: 0%
  carrington_regard:up   50 runs: E_T2N04 47, E_T3N05 3; mean 49.9 actions
      shift S_N03 -> S_T2N02: 100%
  carrington_regard:down 50 runs: E_N07 44, E_T3N05 4, E_T2N04 2; mean 65.7 actions
      shift S_N03 -> S_T2N02: 0%
  fairbrother_faith:up   50 runs: E_N07 42, E_T2N04 4, E_T3N05 4; mean 72.3 actions
      shift S_N03 -> S_T2N02: 2%
  fairbrother_faith:down 50 runs: E_N07 48, E_T3N05 2; mean 69.5 actions
      shift S_N03 -> S_T2N02: 0%
  gresham_confidence:up  50 runs: E_N07 47, E_T2N04 3; mean 67.3 actions
      shift S_N03 -> S_T2N02: 0%
  gresham_confidence:down 50 runs: E_N07 43, E_T2N04 5, E_T3N05 2; mean 69.7 actions
      shift S_N03 -> S_T2N02: 2%
  ormsby_ease:up         50 runs: E_N07 41, E_T2N04 5, E_T3N05 4; mean 70.5 actions
      shift S_N03 -> S_T2N02: 2%
  ormsby_ease:down       50 runs: E_N07 44, E_T3N05 4, E_T2N04 2; mean 70.7 actions
      shift S_N03 -> S_T2N02: 0%
  netherby_nerve:up      50 runs: E_N07 46, E_T2N04 2, E_T3N05 2; mean 70.1 actions
      shift S_N03 -> S_T2N02: 0%
  netherby_nerve:down    50 runs: E_N07 45, E_T3N05 4, E_T2N04 1; mean 70.4 actions
      shift S_N03 -> S_T2N02: 2%
findings:
  note  scene S_N02 is entered in 12 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N03 is entered in 210 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N04 is entered in 464 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N05 is entered in 342 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N06 is entered in 266 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N07 is entered in 531 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T2N01 is entered in 860 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T2N02 is entered in 207 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T2N03 is entered in 238 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T2N04 is entered in 455 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T3N01 is entered in 12 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T3N02 is entered in 51 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T3N03 is entered in 182 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T3N04 is entered in 72 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_T3N05 is entered in 61 distinct states; explored from 8 of them, spread over their arc states
  note  scene S_N02: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T3N01: exploration stopped at 20000 states; its findings cover only those
  note  scene S_N03: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T3N02: exploration stopped at 20000 states; its findings cover only those
  note  scene S_N04: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T2N01: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T3N03: exploration stopped at 20000 states; its findings cover only those
  note  scene S_N05: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T2N02: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T3N04: exploration stopped at 20000 states; its findings cover only those
  note  scene S_N06: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T2N03: exploration stopped at 20000 states; its findings cover only those
  note  scene S_T2N04: exploration stopped at 20000 states; its findings cover only those
  note  nudge S_N02.n2 never fires
  note  nudge S_N03.n2 never fires
  note  scene S_N03: the exit to S_T2N02 (pattern('carrington_regard','up',3,0.75)) is never taken
  note  nudge S_T3N02.n2 never fires
  note  nudge S_N04.n2 never fires
  note  nudge S_T2N01.n2 never fires
  note  event S_T3N03.e2 never fires
  note  nudge S_T3N03.n2 never fires
  note  nudge S_N05.n2 never fires
  note  nudge S_N06.n2 never fires
  note  nudge S_T2N03.n2 never fires
  note  ending E_T3N05: the variant pattern('carrington_regard','up',2,0.6) of C01 is never chosen
  note  ending E_T3N05: the variant pattern('gresham_confidence','up',2,0.6) of C05 is never chosen
  note  ending E_T3N05: the variant pattern('ormsby_ease','up',2,0.6) of C07 is never chosen
  note  ending E_T3N05: the variant pattern('netherby_nerve','up',2,0.6) of C08 is never chosen
  note  ending E_N07: the variant pattern('carrington_regard','up',2,0.6) of C01 is never chosen
  note  ending E_N07: the variant pattern('fairbrother_faith','up',2,0.6) of C02 is never chosen
  note  ending E_T2N04: the variant pattern('carrington_regard','up',2,0.6) of C01 is never chosen
  note  ending E_T2N04: the variant pattern('fairbrother_faith','up',2,0.6) of C02 is never chosen
  note  ending E_T2N04: the variant pattern('netherby_nerve','up',2,0.6) of C08 is never chosen
  note  opportunity talk:C04:mrs_ormsby is offered in only 0% of curious plays: most players never get the choice (gate the way forward behind it, move it onto the path, or mark it optional)
  note  opportunity talk:C07:keyhole_at_midnight is offered in only 0% of curious plays: most players never get the choice (gate the way forward behind it, move it onto the path, or mark it optional)
  note  200 of 200 random plays did not finish in the step limit (wandering is allowed; a high share may mean the way forward is hard to find)

Walkthrough to E_T3N05, C01: true; C02: true; C05: true; C07: true; C08: true:
   1. Talk › Gideon Ashcombe › say 'Anything to be brought up, Doctor?'
   2. Walk › the study door › refuse the Major: walk the four walls
   3. Go › through the service door
   4. Carry › the tureen
   5. Talk › Lucius Carrington › say 'That's for the magistrate, sir.'
   6. Go › the service door
   7. Go › to the library
   8. Talk › Reginald Fairbrother › say 'Go on down, Mr Fairbrother. Later.'
   9. Talk › Cordelia Ormsby › say 'Mind the landing, madam. It's dark.'
  10. Talk › Cornelius Ellingham › say 'Put your name under mine, sir.'
  11. Talk › Lavinia Netherby › say 'Steady the sieve. Breathe.'
  12. Talk › Reginald Fairbrother › say 'Is the candle enough?'
  13. Put › the sherry glass › leave it under the account book
  14. Talk › Gideon Ashcombe › say 'You will want dry boots, Doctor.'
  15. Go › the main stair › down to the drawing room, to give account
  16. Talk › Nathaniel Yardley › say 'Hold him, Mr Yardley. Mind his arm.'
  17. Go › the stair head
  18. Go › to the drawing room
  19. Go › out through the double doors
  20. Go › the front door

Walkthrough to E_N07, C01: true; C02: true; C05: true; C07: true; C08: true:
   1. Talk › Gideon Ashcombe › say 'Anything to be brought up, Doctor?'
   2. Go › the back stair
   3. Talk › Lucius Carrington › say 'Shall I bring in the next course?'
   4. Talk › Millicent Gresham › say 'Not now, miss.'
   5. Talk › Lucius Carrington › say 'Shall I make up the fire first?'
   6. Go › the service door
   7. Go › along the gallery
   8. Talk › Cordelia Ormsby › say 'You'll take cold, madam. Go in.'
   9. Talk › Reginald Fairbrother › say 'Your candle wants trimming.'
  10. Talk › Cordelia Ormsby › say 'What did you hear at eleven, madam?'
  11. Show › Reginald Fairbrother › to the tallow box
  12. Talk › Lavinia Netherby › say 'Set it down a moment. Breathe.'
  13. Talk › Millicent Gresham › say 'Milk first, miss.'
  14. Talk › Lucius Carrington › say 'I am ready to give my account.'
  15. Go › out to the stair foot
  16. Talk › Lucius Carrington › say 'Finish your list first, Major.'
  17. Talk › Cornelius Ellingham › say 'Count the rest first, sir.'
  18. Go › the baize door
  19. Talk › Millicent Gresham › say 'The glass can wait. The candles first'
  20. Talk › Gideon Ashcombe › say 'Ask me after you have signed, Doctor'
  21. Talk › Reginald Fairbrother › say 'Fairbrother, more coal on the fire'
  22. Talk › Lucius Carrington › say 'Major Carrington.'
  23. Go › along the gallery
  24. Go › through the arch to the study door
  25. Lock › the study door

Walkthrough to E_T2N04, C01: true; C02: true; C05: true; C07: true; C08: true:
   1. Talk › Gideon Ashcombe › say 'Anything to be brought up, Doctor?'
   2. Go › the back stair
   3. Talk › Lucius Carrington › say 'Shall I bring in the next course?'
   4. Talk › Millicent Gresham › say 'Not now, miss.'
   5. Talk › Lucius Carrington › say 'Shall I make up the fire first?'
   6. Go › the service door
   7. Go › along the gallery
   8. Talk › Cordelia Ormsby › say 'You'll take cold, madam. Go in.'
   9. Talk › Reginald Fairbrother › say 'Your candle wants trimming.'
  10. Talk › Cordelia Ormsby › say 'What did you hear at eleven, madam?'
  11. Go › the widow's door › see the widow in; leave him unasked
  12. Talk › Lavinia Netherby › say 'Mind the stair-rods with those pails.'
  13. Talk › Cordelia Ormsby › say 'The carriage is ordered, madam.'
  14. Talk › Lucius Carrington › say 'I'll come down and give my account.'
  15. Go › back across the yard
  16. Go › back in by the yard door
  17. Talk › Gideon Ashcombe › say 'Let me make him decent first.'
  18. Talk › Lavinia Netherby › say 'Hot water for the doctor, Netherby.'
  19. Go › up to the drawing room
  20. Go › out through the double doors
  21. Talk › Reginald Fairbrother › say 'The hall lamp wants trimming.'
  22. Talk › Millicent Gresham › say 'The carriage is not round yet.'
  23. Talk › Lucius Carrington › say 'Shall I see to the carriage first?'
  24. Go › the front door › see Miss Gresham to the carriage
  25. Go › the study › up to lock the study for the night
```
