# Speed Force: features

Speed Force is *Justice League Heroes* (Xbox, 2006) running as a native Windows program, with
the content that was only on the PSP version, a set of gameplay changes, and modern PC
graphics and controls. This page explains what each part does.

---

## 1. The recompilation: a native PC program, not an emulator

**How it works.** The Xbox game's program (`default.xbe`) is x86 code written for the Xbox's
Pentium III. Speed Force's setup runs the [xboxrecomp](toolkit/) static recompiler over it on
your PC:

1. The XBE is parsed and every function in it is found (disassembly, function identification,
   calling-convention analysis), guided by a seed list that marks functions the analysis can't
   find on its own (`game/seeds/jlh_seeds.json`), including the mod's added code.
2. Each function is translated to C, keeping the original behaviour instruction for instruction.
3. The C code is compiled with LLVM (clang) into `SpeedForce.exe`, together with the runtime
   that replaces the Xbox itself.

The result is a normal 64-bit Windows program. Because the translated code comes from **your**
dump during setup, none of the game's code is ever distributed.

**The runtime replaces the Xbox hardware and system software:**

| Xbox part | Speed Force replacement |
|---|---|
| Xbox kernel (files, threads, timers, memory) | Native Windows implementation of the kernel calls the game uses |
| NV2A graphics chip (push buffer, shaders, combiners) | A Direct3D 11 renderer that reads the game's own GPU command stream and translates its vertex programs and register combiners to HLSL shaders |
| MCPX audio (DSP56300 effects processor, voices) | XAudio2 output, with the original DSP effect programs run by a DSP56300 interpreter, so reverb and effects sound as they did |
| Controller ports (USB/OHCI) | SDL3 gamepads and the keyboard, presented to the game as Xbox controllers in ports 1 and 2 |
| Hard disk save partition | The `saves` folder inside the install folder |

**Speed and stability.**
- The game runs at its original 60 updates per second with paced frame delivery, so game speed,
  physics and timings are exactly as designed, whatever your monitor's refresh rate.
- File reads are completed asynchronously like the real hardware, so level loads do not stutter.
- Translated shaders are cached on disk after the first time they are seen.

---

## 2. Graphics

### Resolution
- **Widescreen 16:9 (Hor+)**: you see more to the sides, nothing is stretched or cut off.
- **Resolution scale 1x to 4x**: the game is drawn at 720p x the scale (up to 5120x2880) and
  scaled to your screen, which also acts as supersampling.
- **Output resolution**: native screen size, 1080p, 1440p or 4K.
- **16x anisotropic filtering** for sharp textures at grazing angles.
- Window or fullscreen (F11 switches at any time).

### Speed Force frame generation
Speed Force is the project's own frame generation. It creates new frames **between** the
game's real frames, so motion on a 120, 144 or 240 Hz monitor is as smooth as the monitor
allows, while the game itself keeps running at 60.

- **Optical flow from the finished picture.** Motion is measured on the final image, at three
  levels of detail, with sub-pixel accuracy, so everything that moves is tracked: characters,
  effects, the camera, even parts of the HUD. The game's own motion information is used as a
  hint.
- **Two-way warping with occlusion handling.** Each generated frame is built from both the
  previous and the next real frame. Where something appears or disappears (behind a door, under
  a character), the picture switches cleanly to the frame that shows it instead of smearing.
- **Confidence weighting.** Every pixel's motion has a match score. Uncertain areas fall back
  to the nearest real frame, which avoids the wobbling and ghosting typical of frame generation.
- **Identical objects tracked one by one.** Crates, tractors and other repeated objects are
  matched individually, so they don't flicker.
- **Sharp resampling** (Catmull-Rom), so generated frames are as crisp as real ones.
- Settings: Off (the original 60), 120, 144, 240, or match the monitor. Measured at 237-239 fps
  shown at 240 Hz.

### Upscaling and anti-aliasing
- **NVIDIA DLSS, AMD FSR and Intel XeSS.** With a resolution scale below the screen size they
  upscale; at the same size they work as high-quality anti-aliasing.
- **FXAA**, **FXAA (high)** and **TAA** (temporal anti-aliasing with sub-pixel jitter and
  history clamping).
- An optional on-screen counter shows the frames on screen, the game's own rate and the frame
  time.

---

## 3. Controls

- **Any modern controller** through SDL3: Xbox, PlayStation (DualShock 4, DualSense), Nintendo
  (Switch Pro, Joy-Con, GameCube adapters) and more, plugged in or wireless, at any time.
- **Matching button icons**: the on-screen prompts change to the controller you are using
  (Xbox, PlayStation, Nintendo or GameCube style), or can be fixed in the settings.
- **Keyboard play**: WASD move, IJKL camera, Z / X / C / V = A / B / X / Y, Enter = Start.
- **Full remapping** of every controller button and keyboard key.
- **Two players on one PC**, each with their own controller, as on the Xbox: pick Two Players
  for a new game or Chapter Select, or add (and remove) player 2 from the pause menu at any
  time. In the character selector both players choose their own hero and costume.
- **Online play** (2.1): the same two-player game with a friend on another PC, through the
  launcher's Online page. Delay-based netplay: each PC runs the whole game in the toolkit's
  deterministic mode, sends its player's controller every frame, and both feed the two
  controllers to ports 1 and 2. A memory checksum is compared every 5 seconds to catch a desync.
  The host's saves are sent to the joiner; the game checks that both have the same version and
  game files; the input delay comes from the ping; Windows hosts open the router port by UPnP.

---

## 4. Audio
- Native XAudio2 audio with the original DSP effects (reverb, filters) recreated exactly.
- Master volume, and the game's own music, effects and speech levels.

---

## 5. Settings: in game (F10) and in the launcher
- **F10** opens the settings menu over the game at any time: graphics, frame generation,
  upscaler, anti-aliasing, display, audio and controls. Changes apply immediately and are saved.
- The **Speed Force launcher** shows the main settings before you start, then **Play**.

---

## 6. The mod: content and gameplay changes

### PSP content added to the console version
- **Supergirl and Black Canary are unlocked**, converted from the PSP version as full playable
  heroes with their own powers.
- **Four Challenge Missions** from the PSP version (including Vent System), on a new main-menu
  item.
- **Three PSP-only story levels** placed in the story: S.T.A.R. Labs Sub Level (Episode 1),
  Mars Lower Caves (Episode 5) and Fortress Perimeter (Episode 11).
- The PSP-derived levels are rebuilt with 2x textures for the PC.

### Challenge Missions and Chapter Select
- **Challenge Missions are unlocked**, and every hero in them is **fully maxed out**: they are
  meant for after you have beaten the game.
- **Chapter Select is unlocked the same way**: start any episode, at any difficulty, with fully
  maxed heroes (every shop item counts as bought).

### Character selector
- When you play from **Chapter Select**, a **character selector is shown at the start of each
  mission**, so you pick your own heroes instead of the story's fixed pair.
- Episodes that need flying (for example, the levels in space) **only offer heroes who can
  fly**.
- The selector **keeps appearing for every level after that**, like a New Game Plus: you can
  change your team at every mission for the rest of the run.
- New Game keeps the original story pairs.

### Costumes
- A **Costume button** in the character selector for Chapter Select and Challenge Missions.
- Every hero's alternate costumes are available, **including Wonder Woman's costume from the
  last mission** (and Superman's third costume).

### Other changes
- All difficulties are available from the start.
- Restart Episode works in Challenge Missions.

---

## 7. Installer, launcher and saves
- **The Speed Force Builder** (the setup, one program): install folder, your Xbox and PSP disc
  images (checked on the spot, with the free space), optional Xbox saves and a desktop shortcut;
  then the build, with each step, its time, the time left and the full log a click away.
- **The launcher**: Play, the main settings (changed with a click, saved at once), your five save
  slots and Xbox save import, the update check, and Uninstall.
- **The game on its own**: `SpeedForce.exe` runs without the launcher just as well.
- **Saves live inside the install folder** (`saves\`), next to the game, so they are easy to back
  up. Uninstalling keeps them.
- **Bring your Xbox saves**: saves from a real console (the `UDATA\57520001` folder) are copied
  and re-signed for the PC version, into free slots. See [docs/SAVES.md](docs/SAVES.md).
- **Completed saves are playable again**: the original game refuses to load a "Completed Game"
  save. In Speed Force, picking one in Load Saved Game starts **Episode 1 the Chapter Select
  way**: choose the slot, players and difficulty, and play with every hero maxed and the
  character selector. This works for completed saves from the Xbox and from the PC.
- **Update checker**: the launcher looks up the latest release on GitHub when it opens and
  offers it when it is newer (only the release is asked for; nothing is sent).
- Uninstall from the launcher or from Windows Settings > Apps; your saves and settings can stay.
