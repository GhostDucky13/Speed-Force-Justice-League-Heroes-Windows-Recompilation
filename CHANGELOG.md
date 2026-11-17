# Changelog

## 2.1.0
- New **Online** page in the launcher (Windows and Linux): play the two-player game with a
  friend on another PC. One hosts, the other joins with the address the host's window shows.
  Delay-based netplay: both PCs run the whole game deterministically and swap only their
  controllers; the version, the game files and the host's saves are matched when connecting,
  the input delay is set from the ping, and Windows hosts open their router's port by UPnP.
- The game is now generated with `--back-edge-yield` and the D3D KickOff spin-wait site, which
  the deterministic mode needs. Rebuild (run the setup again) to get online play.
- The deterministic mode hands the APU its 25 frames per vblank in one go (faster).

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
