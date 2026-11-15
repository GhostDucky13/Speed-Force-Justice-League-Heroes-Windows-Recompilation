# Bringing your Xbox saves to Speed Force

Speed Force keeps its saves in the `saves` folder inside the install folder. You can bring saves
from a real Xbox over, either in the Speed Force Builder (Options) or later with
**Import Xbox saves** on the launcher's Saves page. Pick the folder that holds them; the
importer looks through all of its subfolders.

The game has five save slots. Imported saves go into free slots only, so a save you already
have on the PC is never overwritten. What happened is written to `saves\import.log`.

## Xbox

Copy the game's save folder from your console, for example over FTP from a modded Xbox, or
with a save manager. It is `E:\UDATA\57520001` (57520001 is the game's title ID), with one
folder per save, each holding a `slot.bin`.

- Each save continues where it was saved, as on the Xbox.
- A **completed save** shows as "Completed Game". The original game refuses to load it; in
  Speed Force, picking it starts **Episode 1 the Chapter Select way** (choose the slot, the
  players and the difficulty), with every hero maxed and the character selector.

Xbox saves are signed with a key that belongs to the console. The importer signs them again for
the PC version; the save data itself is not changed otherwise.

Only Xbox saves are supported.
