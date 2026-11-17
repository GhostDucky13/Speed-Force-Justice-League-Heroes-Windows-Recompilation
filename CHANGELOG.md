# Changelog

## 3.0.2 (pre-release)
- Fixed: missing visual effects (reported on GitHub and Reddit), such as Superman's freeze
  breath (only its sound played) and the shadow under him. Effects the game draws
  as point sprites lost their texture coordinates: a speed-up in the graphics command decoder
  remembered the point-sprite switch as "not handled here" after its first use and skipped every
  later change to it, so each particle drew as one see-through texel. The switch is now always
  applied, which brings back every effect drawn this way.
- Setup: install.log now starts with the Speed Force version and the system it runs on, and an
  error is logged with its full details and, for a missing file, the file's name. (GitHub issue
  #1 came from the 2.0.0 setup, whose build tool bug was fixed in 2.0.1; this makes reports like
  it easier to diagnose.)
- From 2.1.1: Challenge Missions never save and never show the "pick a slot" screen (they used
  to overwrite the story save), and save backups: before the game overwrites or deletes a save
  file, the old file is copied to `saves\backup\` as `<file>.0001.bak`, `.0002.bak`, ... (see
  docs/SAVES.md). Online play leaves the backup folder out of the saves it sends.
- Rebuild to get the fixes: run the 3.0.2 setup (Windows) or the 3.0.2 AppImage (Linux) over your
  install; your saves and settings are kept. Both players need 3.0.2 to play online together.

## 3.0.1 (pre-release)
- Fixed: no voices in cutscenes and in-game dialogue. The game speaks its dialogue on the center
  speaker, and only the front left and right speakers reached the output. All six speaker feeds
  are now folded down to stereo, as the Xbox does with its audio set to stereo (center and
  surround at -3 dB). Surround-only sounds are back too.
- Online play, the first version for testing: not yet tried by many players, so it is a
  pre-release. Please report how it goes.
- New **Online** page in the launcher (Windows and Linux): play the two-player game with a
  friend on another PC. One hosts, the other joins with the address the host's window shows.
  Delay-based netplay: both PCs run the whole game deterministically and swap only their
  controllers; the version, the game files and the host's saves are matched when connecting,
  the input delay is set from the ping, and the host asks its router to open the port (UPnP).
- The game is now generated with `--back-edge-yield` and the D3D KickOff spin-wait site, which
  the deterministic mode needs. Rebuild (run the setup again) to get online play.
- The deterministic mode hands the APU its 25 frames per vblank in one go (faster).
- Windows and Linux play together: the game's sine, cosine, tangent, arctangent and logarithm
  (the Xbox's x87 instructions) are now computed by code built into the game
  (`toolkit/include/recomp_detmath.h`, from Go's math package) instead of each system's C
  library, whose last bit differs between Windows and Wine / Proton. Every PC now computes the
  same results.
- Intel and AMD play together: the Xbox's approximate reciprocal and reciprocal square root
  (SSE `rcpss` / `rsqrtss`) return different bits on Intel and AMD processors, which made the
  same particles and vertices differ between two PCs. They are now computed exactly, the same way
  on every processor.
- New guide: [docs/ONLINE.md](docs/ONLINE.md), with every combination of Windows and Linux, port
  forwarding, Tailscale / ZeroTier, firewalls and troubleshooting.
- Version 3: online play is a big enough change for a new major version (3.0.0 was not released).

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
