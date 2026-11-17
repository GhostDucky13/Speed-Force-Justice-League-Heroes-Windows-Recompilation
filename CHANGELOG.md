# Changelog

## 2.1.1
- Fixed: Challenge Missions overwrote story saves (reported on Reddit). A challenge level asked
  the game to autosave, which wrote into the story save that was loaded, or showed the "pick a
  slot" screen when none was. Challenge Missions now never save and never show that screen.
- New: save backups. Before the game overwrites or deletes a save file, the old file is copied to
  `saves\backup\` (same folder layout) as `<file>.0001.bak`, `.0002.bak`, ... To restore one, copy
  it back into place and remove the `.<number>.bak` ending. See docs/SAVES.md.
- Rebuild to get the fixes: run the 2.1.1 setup (Windows) or the 2.1.1 AppImage (Linux) over your
  install; your saves and settings are kept.

## 2.1.0
- Fixed: no voices in cutscenes and in-game dialogue. The game speaks its dialogue on the center
  speaker, and only the front left and right speakers reached the output. All six speaker feeds
  are now folded down to stereo, as the Xbox does with its audio set to stereo (center and
  surround at -3 dB). Surround-only sounds are back too.
- Rebuild to get the fix: run the 2.1.0 setup (Windows) or the 2.1.0 AppImage (Linux) over your
  install; your saves and settings are kept.

## 2.0.1
- Fixed: the build stopped at the Compile step with "[WinError 2] The system cannot find the file
  specified" on PCs that don't have CMake installed separately. The builder now starts its own
  CMake, Ninja and clang by their full paths.
- Fixed: the game no longer crashes at start on a PC with no sound output device; it runs without
  sound instead.
- Linux AppImage: light theme by default, dark when the desktop is set to dark (or chosen under
  "Theme" in the launcher); update information for AppImageUpdate (`.zsync` next to the
  AppImage); a clear message on Linux versions too old to build (glibc older than 2.34).
- The update check uses the repository's new address.

## 2.0.0 Linux
- New **Linux AppImage** (`SpeedForce-2.0.0-x86_64.AppImage`): the same builder and launcher for
  Linux and Steam Deck. It builds the same game on your PC and runs it with Proton, your system
  Wine, or the Wine it carries (with DXVK and vkd3d-proton), in that order.
- The build steps (`setup/sf_install.py`) also run on Linux, cross-compiling with LLVM-MinGW.

## 2.0.0
- New **Speed Force Builder**: one program that checks your dumps and free space on the spot,
  then builds and installs the game with every step, its time and the time left on screen.
- New **launcher**: Play, settings, save slots with Xbox save import, update check from GitHub
  releases, and uninstall.
- `SpeedForce.exe` runs on its own too ("Speed Force (game only)" in the Start menu).
- Completed Xbox saves start Episode 1 the Chapter Select way.
- Two players: the second controller port is plugged in, so a second pad joins.

## 1.0.0
First release: native Windows build of Justice League Heroes from the player's own Xbox and PSP
dumps, with the PSP content, Speed Force frame generation (up to 240 Hz), DLSS / FSR / XeSS,
FXAA / TAA, resolution scale up to 4x, modern controllers with remapping, and the F10 settings menu.
Speed Force launcher (setup screen with progress, settings, Play), per-user install with the saves
and settings in the install folder, Xbox save import, completed saves start Episode 1 the Chapter
Select way, two-player support with a second controller. See FEATURES.md.
