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

## Backups

Every time the game is about to overwrite or delete a save file, Speed Force first copies the
file as it was into the `backup` folder inside `saves`, with the same folders below it and a
number that goes up by one each time:

```
saves\UDATA\57520001\<save>\slot.bin                       the save
saves\backup\UDATA\57520001\<save>\slot.bin.0001.bak       the save before the 1st overwrite
saves\backup\UDATA\57520001\<save>\slot.bin.0002.bak       ... before the 2nd
```

Saves are small, so all of them are kept (a thousand backups are still only a few MB). To get
an older save back, close the game, copy the `.bak` file you want over the save file and remove
the `.<number>.bak` ending from its name. Delete the `backup` folder whenever you like; it is
only for you. (Developers: `RECOMP_SAVE_BACKUP=0` turns it off.)
