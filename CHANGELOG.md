# Changelog

## 2.0.0 Linux
- New **Linux AppImage** (`SpeedForce-2.0.0-x86_64.AppImage`): the same builder and launcher for
  Linux and Steam Deck. It builds the same game on your PC and runs it with Proton, your system
  Wine, or the Wine it carries (with DXVK and vkd3d-proton), in that order.
- Fixed: the game crashed at start on a PC with no sound output device (seen under Wine); it now
  runs without sound instead.
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
