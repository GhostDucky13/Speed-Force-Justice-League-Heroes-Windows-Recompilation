# Planned mod (later): pick any unlocked hero at the start of each episode

Goal: when an episode starts, offer the character select screen (all unlocked heroes,
including Supergirl and Black Canary) instead of the fixed story pair, but only where
the level design doesn't depend on specific powers.

## Episode list (from a GameFAQs PS2 walkthrough; check against the Xbox level files e1l1a ... e11l5)
| Ep | Location | Story heroes | Choice in original | Restriction | Any-hero mod? |
|---|---|---|---|---|---|
| 1 | Metropolis (Brainiac robot) | Batman + Superman | fixed | none known | yes |
| 2 | Skyline / park / subway (Queen Bee) | Martian Manhunter + Zatanna | fixed | **flight needed to reach Queen Bee's throne** | only fliers |
| 3 | Communications facility (The Key) | Green Lantern + Flash | fixed | none known | yes |
| 4 | Missile base (Killer Frost) | Wonder Woman + Zatanna | fixed | none known | yes |
| 5 | Mars (White Martian leader) | Superman + Martian Manhunter | fixed | story/Mars; check for flight sections | probably yes, verify |
| 6 | Gorilla City (Grodd, earthquake machine) | your choice | free | — | already free |
| 7 | **Space** (White Martian fleet) | Superman + Wonder Woman | fixed | **space level, flight required** | only fliers (or keep fixed) |
| 8 | Watchtower (Doomsday clone) | your choice | free | — | already free |
| 9 | Brainiac's lair | your choice | free | — | already free |
| 10 | Escape the dimension (3 parts) | 10.1 Batman + Zatanna, 10.2 Wonder Woman + Flash, 10.3 Martian Manhunter + Green Lantern | fixed per part | 10.3 uses flight | 10.1/10.2 yes; 10.3 fliers only |
| 11 | New Apokolips (Darkseid) | 11.1 free; 11.3 four teams of two | mostly free | — | already free |

Fliers (to verify in game): Superman, Supergirl, Wonder Woman, Martian Manhunter, all three
Green Lanterns, Hawkgirl. Ground: Batman, Flash, Zatanna(?), Green Arrow, Huntress, Aquaman, Black Canary.

## How it could work (engine side, found so far)
- The character select screen (`char_sel.swb`) is already driven by commands to the game
  (CMD_GET_CHARS_LOCKED etc.); the free-choice episodes already show it.
- Need to find where each episode decides "fixed pair" vs "show select screen": likely in
  the level/episode table in gamedata.lmp (`~~Levels`) or the level scripts.
- For flight-restricted episodes: filter the select screen with a "can fly" flag per hero
  (the Xbox character table at 0x1DF638 or gamedata likely has a movement-type field).
- Story cutscenes are pre-rendered and show the original pair; that is unavoidable.
