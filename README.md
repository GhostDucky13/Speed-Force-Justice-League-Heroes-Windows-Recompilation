# Speed Force

**An unofficial native Windows version of *Justice League Heroes* (2006), built on your PC from your own Xbox and PSP discs.**

Speed Force statically recompiles the original Xbox game into a native x64 Windows program,
adds the content that was only on the PSP version, and adds modern PC features: high
resolutions, 240 Hz frame generation, DLSS / FSR / XeSS, anti-aliasing, modern controllers and
more. See [FEATURES.md](FEATURES.md) for a detailed explanation of everything.

### Highlights

- **A real native PC game**: the Xbox program is translated to C and compiled for Windows
  (no emulator), with a Direct3D 11 renderer, XAudio2 audio and SDL3 controllers.
- **Speed Force frame generation** up to 240 Hz, **DLSS / FSR / XeSS**, FXAA / TAA, up to 4x
  resolution scale, widescreen.
- **Challenge Missions are unlocked**, with fully maxed-out heroes: they are meant for after you
  beat the game. **Chapter Select** is unlocked the same way.
- **A character selector at the start of each mission** when you play from Chapter Select, with
  only flying heroes offered for the flying levels (for example in space). It keeps appearing
  for every level after that, like a New Game Plus.
- **Supergirl and Black Canary unlocked**, brought over from the PSP version, plus the PSP's
  Challenge Missions and three PSP-only story levels.
- **A Costume button** in the character selector for Chapter Select and Challenge Missions, with
  **Wonder Woman's last-mission costume** available too.
- Two players on one PC, each with their own controller.
- Bring your **Xbox saves** over; completed saves start Episode 1 the Chapter Select way.

> **No game code or data is included in this repository or in the setup.**
> You need your own dumps of both discs. The setup rebuilds everything on your PC from them.

## What you need

- Windows 10 or 11, 64-bit
- A DirectX 11 graphics card (DLSS needs an NVIDIA RTX card; FSR and XeSS run on any modern GPU)
- About 14 GB free disk space while the game is built (12 GB, plus 2 GB to be safe); about 5 GB afterwards
- Your own dumps (disc images) of:
  - **Justice League Heroes** for the original **Xbox** (USA)
  - **Justice League Heroes** for the **PSP** (USA)

How to make the dumps from discs you own: [docs/DUMPING.md](docs/DUMPING.md).

## Installing

1. Download `SpeedForce-Setup-2.0.0.exe` from [Releases](../../releases) and run it. It's one
   program, the **Speed Force Builder**: no administrator rights are needed.
2. **Game files:** choose where to install (by default `%LOCALAPPDATA%\Programs\Speed Force`) and
   your Xbox and PSP disc images. Each one is checked on the spot, and so is the free space.
3. **Options:** optionally, a folder of saves copied from an Xbox (see [docs/SAVES.md](docs/SAVES.md)),
   and a desktop shortcut.
4. **Build:** the builder unpacks its tools, checks your dumps, extracts them, rebuilds the mod,
   translates the game program to C and compiles it, all on your PC, with every step, its time
   and the time left on screen (about 20-40 minutes; **Show details** shows the full log, which is
   also saved as `install.log`). When it's done, press **Play**.

Two programs are installed:

- **Speed Force** (`SpeedForceLauncher.exe`, in the Start menu and on the desktop): Play, the main
  settings, your save slots and Xbox save import, the update check, and Uninstall.
- **Speed Force (game only)** (`SpeedForce.exe`): the game itself. It runs on its own too; press
  **F10** in game for every setting.

Your saves are in the `saves` folder inside the install folder, and your settings in
`config\config.toml`. Uninstall from the launcher's About page or from Windows Settings > Apps;
you can keep your saves and settings.

The launcher checks this repository's [Releases](../../releases) when it opens and offers a
newer version when there is one (it only asks GitHub for the latest release; nothing about you
or your PC is sent).

Supported dumps (SHA-1 of the whole image):

| Disc | SHA-1 |
|---|---|
| Xbox (USA) | `76ec8ba8466ecc32b5129c2513707c8e59f687e8` |
| PSP (USA) | `87055c512472e8fd160361a84c2fb5444bba422d` |

Other dumps are refused by default, because the mod tools patch exact byte offsets.

## Controls

Xbox, PlayStation (DualSense / DualShock), Nintendo (Switch Pro, Joy-Con, GameCube adapters)
and most other controllers work, with matching button icons in game. Keyboard: WASD move,
IJKL camera, Z / X / C / V = A / B / X / Y, Enter = Start, F10 = settings, F11 = fullscreen.
Every button can be remapped in F10 > Controls.

## Building from source

See [docs/BUILDING.md](docs/BUILDING.md). In short: the builder (`launcher/sfbuilder.c`) carries
a build kit and runs `setup/sf_install.py`, which does the same steps a developer would: extract,
`setup/sf_buildmod.py`, the xboxrecomp pipeline, CMake + Ninja + LLVM-MinGW. The builder and the
launcher are plain Win32 C with a small shared UI (`launcher/sfui.h`).

## Repository layout

| Folder | What it is |
|---|---|
| `toolkit/` | Fork of the xboxrecomp static recompilation toolkit (runtime, D3D11 renderer, audio, input, the F10 menu, Speed Force frame generation) |
| `game/` | The Justice League Heroes port: entry point, settings, lifter seeds. The translated game code is generated during setup, never committed |
| `jlh-upscale/` | DLSS / FSR / XeSS bridge (`jlh_upscale.dll`) |
| `setup/modtools/` | The mod's tools: XBE patcher, menu and data editors, PSP to Xbox character and level converters |
| `setup/` | Disc extractor, mod builder, save importer and the build steps the builder runs |
| `launcher/` | The Speed Force Builder (the setup) and launcher, their UI and the build-kit packer |
| `assets/` | Button icon pack (generated, original artwork) |
| `docs/` | Dumping, building, and the mod's technical notes |

## Known issues

- Episode 5, Mars (e5l1): laser fire can be invisible, too many meteors appear, and some debris
  textures vanish.

## Acknowledgements

Speed Force stands on the work of many people. Thank you to:

- **sp00nz** and the contributors of [xboxrecomp](toolkit/README.md), the static recompilation
  toolkit and Xbox runtime that this whole port is built on.
- **Snowblind Studios**, for making *Justice League Heroes*, and everyone who worked on the
  Xbox and PSP versions.
- The [xemu](https://github.com/xemu-project) team for [dsp56300](https://github.com/xemu-project/dsp56300),
  which brings the original DSP audio effects back, and for years of documenting the Xbox.
- The [SDL](https://github.com/libsdl-org/SDL) team, for making every controller just work.
- **Martin Storsjö** for [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw), and the LLVM,
  [CMake](https://cmake.org) and [Ninja](https://ninja-build.org) projects, which compile the
  game on your PC.
- The [Capstone](https://www.capstone-engine.org) engine, the disassembler behind the recompiler.
- [Python](https://www.python.org), [NumPy](https://numpy.org) and [Pillow](https://python-pillow.org),
  which run the setup and the mod tools.
- **NVIDIA** ([DLSS](https://github.com/NVIDIA/DLSS)), **AMD**
  ([FidelityFX](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK)) and **Intel**
  ([XeSS](https://github.com/intel/xess)) for their upscalers.
- **SnowflakePowered** for [librashader](https://github.com/SnowflakePowered/librashader).
- The [DejaVu fonts](https://dejavu-fonts.github.io) project, and **Rasmus Andersson** for the [Inter](https://rsms.me/inter/) typeface.
- Everyone in the Xbox and PSP preservation and modding communities whose research made the
  formats in this game understandable.

If your work is used here and you're missing from this list, please open an issue.

## Legal

Speed Force is a fan project. It is not affiliated with, endorsed or sponsored by Warner Bros.
Games, DC, Snowblind Studios or Eidos. *Justice League Heroes* and all related names and
trademarks belong to their owners. Read [LEGAL.txt](LEGAL.txt).

The project's own code is under the [MIT License](LICENSE). Third-party components keep their
own licenses: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
