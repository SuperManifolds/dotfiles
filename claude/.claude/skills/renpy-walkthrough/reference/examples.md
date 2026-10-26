# Worked examples (from real games)

Kept out of `rubric.md` so blind spot-check agents never see hints for these games.


- CoD 2 tour loop (`script.rpy:3930`): note "Visit all three places (any order) before
  leaving."; three good items (one "Opens Emma's Ch 12 route" because a later `if` reads
  its flag); exit item bad "Ends the tour early".
- Studio Hearts quiz (`AidaMessages.rpy:481-636`): five menus, each with one
  `AidaFriendsScore += 1` item → "Correct answer"; note on the first: "All five answers
  right unlocks a gallery picture."
- Studio Hearts vibrator profile (`MilaMessages.rpy:349-381`): score = intensity × pattern
  × duration; band `14.9 <= s < 16.8` gives the best reaction; High × Earthquake × 15 min
  = 16.2 (avoid combos that hit 16.8 only through float rounding).
- Hearts on Parole: nearly every menu is `<Name>_point += 1`; `budget Rachel_point` shows
  6 gains and the `>= 4` gate, so the hints say "Rachel +1 (4 of 6 needed)".
- CoD 1: `cvar = MultiPersistent(...)` exports; only the values CoD 2 reads in conditions
  became "Carries into CoD 2" hints.
