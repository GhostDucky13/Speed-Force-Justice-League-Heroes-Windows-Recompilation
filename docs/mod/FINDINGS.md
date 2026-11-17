# Stage 1 findings — Xbox `default.xbe`

SHA-1 `264550fa8337b43f14a630120be854d2f32bb6a9` (2,117,632 bytes)

## Executable
| | |
|---|---|
| Title | Justice League Heroes, title ID `WR-001`, version 1 |
| Region | North America + Rest of World |
| Build | Retail (entry `0x0015894C`, base `0x00010000`) |
| XDK | **5849** for every library (XAPILIB, D3D8, XGRAPHC, DSOUND, XBOXKRNL, LIBCPMT, LIBCMT). 5849 is the final XDK and the best-supported version in xemu, Cxbx-Reloaded and xboxrecomp. |
| Middleware | Bink video (14 sections), Dolby audio encoder, XPP (USB input) |
| Kernel imports | 120 ordinals — the full list the runtime must implement is in `report/xbe_report.json` |
| Source tree | `\jla\src\game\core.cpp`, `game.cpp`, `lump.cpp` — internal project name **"jla"** |

## Code size
- `.text`: 1.42 MB of x86 code, **~4,470 directly called functions**.
- **~9,900 indirect calls** through C++ vtables. Static analysis will miss many of their targets, so emulator tracing (stage 3) is required.
- `.text` also contains statically linked C runtime and XAPI code, to be identified and replaced rather than translated.
- Separate sections hold the SDK code: D3D (83 entry points called), DSOUND (17), BINK (15), XPP (8). These get replaced wholesale.

## Supergirl and Black Canary are in the Xbox code
The PSP-exclusive characters are **not PSP-only in the code**. The Xbox executable has a full 15-character roster:

| ID | Internal | Display | Default |
|---|---|---|---|
| 0–6 | superman, manhunter, batman, wwoman, flash, glantern, zatanna | starting 7 | unlocked |
| 7, 8 | gl_kyle, gl_hal | Green Lantern variants | locked |
| 9–12 | greenarrow, aquaman, hawkgirl, huntress | | locked |
| **13** | **supergrl** | **Supergirl** | locked |
| **14** | **bcanary** | **BlackCanary** | locked |

Evidence:
- Parallel tables at `0x001E020C` (display names), `0x001E0248` (internal names), `0x001E0284` (reaction animations `SG_react`, `BC_react`), all 15 entries.
- Asset filenames `supergrl.lmp`, `bcanary.lmp` referenced from data tables at `0x001E2EF8`, `0x001E3730`.
- Character select (`0x0007F762`) matches a player's choice against all 15 names.
- Per-character save/state table at `0x001DF638`, 15 × 0x78 bytes. Byte +0 is the lock flag; the reset routine at `0x0001C57A` / `0x000713CD` sets IDs 0–6 unlocked and 7–14 locked.
- Save-menu code (`0x0014D93F`, `CHARS_LOCKED`) loops `id < 15`.

**Open question:** whether the Xbox disc actually contains `supergrl.lmp` and `bcanary.lmp`, and whether any Xbox unlock condition ever clears their lock flag. No direct write of 0 to their lock byte was found yet; unlocks probably run through script data on the disc.
- If the assets exist on the Xbox disc: enabling them is a small patch.
- If not: their models, animations and powers come from the PSP dump, as planned.

## Other notable findings
- The game exposes a `highdef` script variable (from byte `0x0046A3AF`) — the Xbox HDTV mode flag. Forcing it on is a first step for higher-resolution output.
- `level0`–`level20` are character experience levels, not stages. XP logic is at `0x00071310` and `0x0007D437`.
- A debug string notes that auto-map drawing must come after object drawing on Xbox — a render-order dependency to keep in the new renderer.

## Next steps
1. **Disc file listing** from the Xbox dump — confirms whether Supergirl/Black Canary assets exist.
2. Identify CRT/XAPI functions inside `.text` by XDK 5849 signatures.
3. Trace runs in xemu to collect vtable call targets.
4. Lift to C with xboxrecomp (needs network access enabled).

## Xbox `res` folder check (847 files)
- `supergrl.lmp` and `bcanary.lmp` (the character model/animation archives) are **not** on the Xbox disc.
- Their HUD and status-screen files **are** on the disc: `hud_sg.lmp`, `sta_sg.lmp`, `hud_bc.lmp`, `sta_bc.lmp`.
- Conclusion: the Xbox build shipped with the code and menu assets for both characters, but not their models. Models and animations come from the PSP dump, converted to the Xbox formats.
- File types on disc: .lmp (578), .tex (69), .gob (69), .vat (67), .bik video (61).

## PSP vs Xbox file comparison (PSP 900 files, Xbox 847)
PSP-only content to port:
- Characters: `supergrl.lmp`, `bcanary.lmp`
- **9 extra levels** (each a .gob/.tex/.vat set): bonus levels `ebonus1`–`ebonus4`, and PSP levels `pspe1`, `pspe5`, `pspe11`, `pspe2l5a`, `pspe2l5b`
- Cutscene `cut_lgle` (PSP .pmf video)
- PSP-specific menu/stat screens (`charsp`, `statsp`, `frontpsp`, `*_i.lmp` variants) — likely only partly needed
- `wbrkanim.lmp` (unknown, to check)

Xbox-only: levels/assets `bunker`, `city`, `findis`, `subsample`, `wt2`, `w_mars.lmp`, `vu.lmp`, plus Xbox UI (`xbtexs`, `xbx_legl`, `frontbik`, Bink menu videos). Keep all.

Level format is the same trio (.gob/.tex/.vat) on both platforms, so one converter covers all 9 PSP levels.

## Character archive formats (from supergrl, bcanary, wwoman PSP + wwoman Xbox)
**.lmp container — solved.** `tools/lmp.py` unpacks and rebuilds all four archives byte-identical.
Layout: u32 count, count × {name_off, data_off, size}, 12-byte zero terminator, names, data aligned to 0x80 (last file unpadded). Identical data blocks are shared.

**Contents** (Wonder Woman, 147 shared file names): **127 are byte-identical between PSP and Xbox.**

| Type | PSP | Xbox | Status |
|---|---|---|---|
| `.anm` animation | same format | same format | Most identical. ~10 Wonder Woman anims differ slightly in size — check before relying on PSP anims |
| `.vag` / `.wav` sound | Sony VAG ADPCM | Xbox ADPCM WAV (tag 0x69), 16 or 18 kHz | **Converter done** (`vag2xwav.py`). Decoders verified against all 40 Xbox WW sounds (loudness envelope corr 0.998, level within 1%); encoder SNR 25.7 dB median over 110 sounds |
| `.tex` texture | 4-bit, 16 colours, swizzled 16×8 tiles, palette first | 8-bit, 256-colour RGBA palette, linear | **Converter done** (`tex.py`). Pixel-identical; converted cape16/lasso match real Xbox file sizes exactly |
| `.vif` model | "1.30" + `PSP` tag, GE-native vertex data | "1.30" + `XBOX` tag, bone remap tables + D3D-style buffers | **Next: reverse-engineer both, write converter** |

Texture atlases differ in layout between versions, so each texture only fits its own model: Supergirl and Black Canary need their PSP model + PSP texture together.
PSP textures are lower quality (16 colours; WW 304×191 vs Xbox 365×191). Optional later: AI-upscale and re-quantise to 256 colours for Xbox-level detail.

Character payloads: Supergirl 136 anims, 36 sounds, body + cape model/texture; Black Canary 86 anims, 34 sounds, body model/texture.

## Models (.vif) — Zatanna, Wonder Woman, top hat, Supergirl, Black Canary
### PSP format — solved (`tools/vif_psp.py`)
- 0x68: u32 section offsets (terminated by file size). Each section: u32 vtx_off, cmdlist_off, cmdlist_size.
- **Sections are swappable parts, not LODs.** Zatanna: body, long hair, hair variant, top hat (all head pieces use bone 13 + neighbours).
- Command list = raw PSP GE commands: VTYPE (0x12), BONENUM (0x2A, arg/12 = matrix slot) + CALL (0x0A, (target & 0xFFFF)/0x38 = skeleton bone), PRIM (0x04, triangle strips), RET.
- Vertices: [u8 weights ×1–2] + u16 uv[2] + s8 normal[3] + s16 pos[3], 16 bytes (14 for rigid). Model space, Z-up, T-pose.
- UV is relative to the actual texture size. Xbox UV is relative to the power-of-two size, so PSP→Xbox is `u × width / pow2(width)` (verified on the top hat and by rendering).
- Verified by rendering: Supergirl, Black Canary, Zatanna come out as complete, correctly textured characters.

### Xbox format — mostly solved (`tools/vif_xbox.py`)
- Same file as the PSP layout with **0xA0 bytes inserted** after 0x5C: two 64-byte bone palettes + index-split table. Blocks after it are the PSP blocks shifted by 0xA0; the header's u16 block-offset table is each PSP value +10. Attachment-point block (780 bytes) is byte-identical to PSP.
- 0x50: vertex_block_off, index_off, vertex_count. Indices: u16 triangle strips. Vertices 32 bytes: s16 pos[3], s16 normal[3], s16 uv[2], f32 (regA, wA, regB, wB); skeleton bone = palette[reg/4].
- Bone numbering is shared with PSP: 93% of matching vertices agree on bones; the rest are face/shoulder vertices the higher-detail Xbox model skins to extra bones.
- Rigid models fully verified: all 78 top hat vertices reproduced from PSP data within rounding.
- Verified by rendering Xbox Zatanna: complete, correctly textured.
- **Open:** exact meaning of the 9-entry index-split table (which index range is which part, and which palette it uses). The game's model loader in the XBE is the authoritative source; ~140 candidate functions found, needs a focused pass.

### Visual comparison (same character, same renderer)
Zatanna PSP (corrected UVs: same costume as Xbox): 1,494 triangles, 320×192 texture with 16 colours. Xbox: 3,942 triangles, 382×184 texture with 256 colours.

### Converter plan for Supergirl / Black Canary
1. Decode PSP model (done) → neutral mesh with bones.
2. Build Xbox file: PSP header + inserted palettes/split table, PSP blocks shifted +0xA0, index strips + 32-byte vertices.
3. Split bones into ≤44-slot palettes (Supergirl uses 45 bones, Black Canary 46 → two batches, like Zatanna).
4. Convert UVs to actual-size, normals s8 → s16, textures via `tex.py`, sounds via `vag2xwav.py`.
5. Repack with `lmp.py` as `supergrl.lmp` / `bcanary.lmp` into the Xbox `res` folder.

## Stage 4 — Xbox model format completed, converters and unlock patch

### Xbox .vif, final details
- Header byte 0x4A = part count n (also in PSP). Header 0x30 is a PSP-only block offset; Xbox has 0 and the game code (0x55FD7) skips that path when it is 0.
- 0xF0: (2n+2) u32 index boundaries = palette-A pass [0, end of part 0 .. part n-1] then palette-B pass [start, end of part 0 .. part n-1]. Bit 30 marks alpha-blended ranges (matches the texture's 0x80 flag).
- Per-part 16-byte records: bounding box (1/16 units), anchor bone, **triangle count** (= triangles with 3 distinct indices; verified exactly).
- Palettes: max 44 slots (shader registers slot×4).
- Effect-sphere block (u16 table entry 3): Xbox = u32 n1, u32 n2, u32 0, then (n1+n2) × {s16 x,y,z,size,bone}; PSP = u32 n then the same records. Positions and bones identical on both platforms; size is platform-tuned (Xbox ≈ 0.55–0.75× PSP). Used by effect code (0x5635C) to spawn effects on the body.
- Block placement: after the per-part records, 16-aligned, in PSP order; index data 128-aligned.
- PSP texture UVs are relative to the actual texture size (earlier renders used the wrong scale; corrected).
- Winding: Xbox character strips mix both windings per segment, so characters are drawn without back-face culling.
- Capes: 8×8 cloth grid, row-major, stored twice (128 vertices), one-bone palette [0]. All PSP and Xbox cape8 grids share identical positions.

### Converter validation (PSP → Xbox, compared with the real Xbox files)
| Model | Header | Block table | Index offset | Data blocks identical |
|---|---|---|---|---|
| Zatanna body | identical | identical | identical | 79% (rest = bounds recomputed from each mesh) |
| Wonder Woman body | identical except alpha flag | identical | identical | 79% |
| Top hat, dove | identical | identical | identical | 100% |
| Lasso | identical | identical | identical | 100% |
| Tiara | identical | identical | identical | 96% |
Round trip: every vertex keeps its exact bone in all parts (0 mismatches) for Zatanna, Supergirl, Black Canary.
Full pipeline on PSP Wonder Woman / Zatanna produces the same file set as the real Xbox archives (185/185 for Zatanna).

### Built
- `out/supergrl.lmp` (176 files: 136 anims, 36 sounds, body + cape, 2 textures)
- `out/bcanary.lmp` (122 files: 86 anims, 34 sounds, body, texture)
Every file decodes with the Xbox-side readers.

### Unlock patch (`tools/patch_unlock.py`)
New-game routine 0x7139D sets lock = (id > 6). Patch: lock = (7 ≤ id ≤ 12) via two int3 alignment gaps (0x1602B1, 0x160761; unreachable, unreferenced). 63 bytes changed, .text digest recomputed (formula SHA-1(u32 size + data) verified on the original). `--mode all` unlocks everyone (1 byte).

### Still to verify in an emulator
- Whether the Xbox character-select layout (`char_sel.lmp`, `chartext.lmp`) shows slots 13/14. If not, those files need the PSP layout ported.
- Supergirl/Black Canary powers and stats (scripts) — the Xbox build has the code paths, but their data may live in files not yet examined.

## Stage 5 — character select shows only 13 (fixed, pending test)
User test: game runs, 13 filled slots (three Green Lanterns = IDs 0-12).
- Startup preload (0x1B6EB) loaded archives for IDs 0-12 only (`cmp esi,0xD` at 0x1B75D). Patched to 15; handle slots 0x2ADCD4/0x2ADCD8 were unused. Character creation (0x7CDBD) already has a Supergirl (ID 13) special case.
- Menus are uncompressed Flash 4 (`.swb` = SWF). `tools/swb.py` lists tags and disassembles actions.
- `char_sel.swb` (Xbox) already contains the PSP 15-portrait grid (p13/p14, rowCount 5 × colCount 3, GetRow*PSP), enabled only when `platform == 3`. The XBE sets `platform` = "1" (handler 0x14E0C7), so 3 = PSP. Other platform checks select button icons and are left alone.
- Xbox and PSP menu scripts are otherwise near-identical (PSP adds CMD_HIGHLIGHT_TEXT calls).
- `tools/patch_charsel.py`: flips the 4 player-1 layout checks (`not` → `toInteger`), and overwrites player 2's 13-portrait GetRow/GetRowAbove/GetRowBelow with the PSP grid code renamed to player-2 variables. Same size, every instruction verified against the source.
- chartext.gdt has ptChar0-14 on both; Xbox ptChar14 has 3 strings vs PSP 5 (description may be shorter).

## Stage 6 — slots shown but locked (black silhouettes, not selectable)
- Menu lock state comes from CMD_GET_CHARS_LOCKED (handler 0x14D91D): locked if lock byte [0x1DF638 + id*0x78] == 1, or the hero is already picked.
- The 15 × 0x78 table is saved with the profile (0x7143B copies 0x708 bytes out) and restored on load (0x71472 copies it back). A profile from the unpatched game stores 13/14 as locked, overriding the new-game patch.
- Fix in `patch_unlock.py`: after the load copy, clear lock bytes 0x1DFC50 (ID 13) and 0x1DFCC8 (ID 14). Uses padding gaps 0x160801 and 0x161472.

## Stage 7 — menus, shield shop, PSP levels
### Formats
- `.gdt` data tables fully decoded (`tools/gdt.py`, byte-identical rebuild of all 14 tables in gamedata.lmp + gametext.lmp). Cells are a 2-bit-typed stream; `~~U:` tables hold UTF-16 strings (type 3, 2-byte aligned, 0xFF filler).
### Main menu
- PSP's real main menu is `frontpsp.swb`; its `frontend.swb` is the console one. Item for item the menus match (New Game, Continued Play, Load, Challenge Missions, Options, Credits). PSP only adds memory-stick prompts and reworded Continued Play text. Pause menus are equivalent.
- Challenge Missions (item 3) and Continued Play (item 1) are skipped while `gameWon` = 0. `gameWon` comes from 0x68105, which scans save slots for a completed-game save.
- `patch_menus.py frontend`: one byte (`i == 3` → `i == 9` at 0x532) makes Challenge Missions always selectable. **Only ship it together with the ebonus levels**: CMD_GET_CHALLENGE_MISSIONS (0x14D82A) lists the last 4 rows of `~~Levels`, which on Xbox are Episode 11.
### Shield shop (stats.swb)
- Shop items 1-23 map to unlocks in the XBE (0x7CC2F jump table): item 22 → Supergirl, item 23 → Black Canary (hero unlock 0x71521, start level 5). Purchases saved in a 23-byte table at 0x437358.
- Xbox stats.swb already has all 23 prices (items 22/23 = 95 shields). The XBE sends numBuyItems = 23. On non-PSP the menu hides the last two (maxscroll = numBuyItems − 2, `nonpsp` cover, row 22 blanked).
- `patch_menus.py stats`: 4 platform checks → PSP branch.
### Level table (~~Levels): Xbox 60 rows, PSP 68
| PSP row | Name | Placement | Verdict |
|---|---|---|---|
| pspe2l5a, pspe2l5b | The Hive 1 / 2 | replaces e2l5 | memory split of Xbox e2l5 (PSP disc still has unused E2L5) → **skip** |
| pspe1 | Star Labs, The Labs 2 ("S.T.A.R. Labs Sub Level") | between e1l6 and e1l7; PSP e1l6 exit text changed to "To Research Labs Sub Level" | new story level or split of e1l6 → **compare geometry** |
| pspe5 | Mars Caves 1a ("Mars Lower Caves") | between e5l2 and e5l3 | same check |
| pspe11 | Fortress Perimeter (new objective e11part4 "Protect the perimeter") | between e11l3 and e11l4 | same check |
| ebonus1-4 | Challenge missions (Vent System, Brainiac Security, Darkened City Street, Swarm) | end of table | Xbox already has all their text and the challenge code → **port** |
- Columns include `charSel` (e.g. `c1,2` = select screen) and `charExclude` (hero codes) — the hooks for the any-character mod.
- Levels are looked up by name, not index.

## Stage 8 — difficulties, level container
- Difficulty screen (frontend.swb, /Difficulty): nItems = gameWon ? 5 : 3, and d3/d4 (Elite, Superhero) greyed while gameWon == 0. `patch_menus.py frontend_diff`: nItems 3 → 5 (0x50E8C) and both grey checks compare to 9 (0x50D2F, 0x50D87). The /DifficultyPSP copy is PSP-only and left alone.
- `patch_menus.py frontend` = difficulties + Challenge Missions (ship with the ebonus levels).
- Level files: `.gob` = container of 32-byte-named entries {name, u32 offset, u32 size}: `<level>.lmp` (dialog .bin ×2, `<level>.world`, `level.amx`, `objects.ob`), `env.lmp`, `waterenv.lmp`. `.vat` and `.tex` are separate per-level files.
- `level.amx` is a Pawn AMX script (magic 0xF1E0). Strings are 1 cell (4 bytes) per char. It names the next level for `simpleNewWorld`: e1l6→"e1l7", e1l7→"e2l1", e5l2→"e5l3", e5l3→"e5l4", e11l3→"e11l4", e11l4→"e11l5".
- Plan to insert PSP stages without moving script data: give them unused same-length names (pspe1→e1l8, pspe5→e5l5, pspe11→e11l2) and change the one next-level string in the Xbox level before each.
- The uploaded `.tex` files were corrupted in transit (UTF-8 replacement characters); `.gob`/`.vat` arrived intact. Re-upload inside a ZIP.

## Stage 9 — level formats, split question settled
### Audio (.vat) — solved (`tools/level.py`)
- `*_dialog.bin` in the level .lmp lists the streams in the .vat: 80-byte records {name[60], u32 size, u32 offset, u32 0, u32 0x90000}, ended by an empty record whose offset = total size.
- Xbox .vat: streams back to back (2048-aligned), stereo Xbox ADPCM, 72-byte blocks (L header, R header, 8 × {4 bytes L, 4 bytes R}). Xbox levels have 2 streams: music (env_…) + ambience (amb_<level>).
- PSP .vat: one ATRAC3plus music stream only.
- Every PSP level uses an existing music track by name: pspe1 env_e01_star (Xbox e1l6), pspe5 env_e05_mars_a (Xbox e5l2), pspe11 env_e11_frtrs_a (Xbox e11l4), ebonus1 env_e03_arctic_a, ebonus2 env_e09_brain, ebonus3 env_e11_dark, ebonus4 env_e02_subwy_a (the last four live in other Xbox levels). → Ported levels get the original Xbox-quality streams copied verbatim; no transcoding. `tools/collect_for_levels.py` (run by the user) extracts the four missing ones.
### Split vs new — new
- World header fields 2-5/10-13/15-18 are level bounds. pspe1, pspe5 and pspe11 extend well outside the Xbox level each would have been split from (pspe5 x −220..−78 vs e5l2 −190..171, y −215 vs −90; pspe1 y up to 200 vs e1l6 116; pspe11 x 5..195 vs e11l4 −195..80). Together with the earlier 3–5 % object overlap, their own objectives and exit text: they are areas the Xbox version does not have. **All seven (pspe1, pspe5, pspe11, ebonus1-4) get ported**; pspe2l5a/b stay skipped.
### .world (same header on both platforms)
- h[0] = object count, h[9] = offset of 60-byte object records (same size on both): +0 mesh ptr, +4 u32, +8 bbox max xyz, +0x14 bbox min xyz, +0x20, +0x24 flags, +0x28 cell coords, +0x34 u16 texture-group id.
- PSP mesh (record +0 points into the geometry block): {u32 0x10 vertex offset, u32 GE-list offset, u32 0x30, 0}, vertices of 14 bytes (u16 u,v; s8 nx,ny,nz,pad; s16 x,y,z; VTYPE 0x122), then a GE list (VTYPE, PRIM tri-strip n, RET).
- Xbox mesh: record +0 points to a 0x80-byte descriptor {u32 vert ptr, u32 nverts, u32 index ptr, u32 nindices, runtime zeros}; u16 indexed triangle strips, 16-byte vertices (s16 u,v; s16 x,y,z; s16 nx,ny,nz).
- Position units match between platforms (both s16, same magnitude). UV scale still to calibrate → PSP E1L7 requested (the one level on both platforms).
### Level .tex
- {u32 id, off, size} per texture group; ids are world-cell ids (≈ 5000 + x + 100·y; header h22/h23 = min/max), i.e. textures are streamed per cell, not global. Each group: u32 image count, 64-byte records {u16 a, u16 b, u32 0x10c, u32 data off}, 256-colour palette at +0x500, then pixel data. Pixel encoding not decoded yet.
- No global texture ids, so Xbox substitution would have to be by image content (later); fallback is upscaling the PSP images.

## Stage 10 — calibration with PSP E1L7 (user's collect ZIP)
- Collected: PSP E1L7.GOB/.TEX/.VAT; Xbox tracks env_e11_dark (e11l1), env_e02_subwy_a (e2l5), env_e03_arctic_a (e3l2), env_e09_brain (e9l1) → input/collect/. All music for the 7 ported levels is now available in Xbox quality.
- e1l7 on both platforms: identical world header bounds/cell grid/texture ids; 306 (Xbox) vs 313 (PSP) objects, same bboxes and cell ids in the same order.
- Vertex positions: s16 local coords, scale 1/4 world unit, identical on both. PSP has its own triangulation (non-indexed tri strips, more verts); Xbox uses indexed strips → conversion = dedupe PSP strip verts + emit indices.
- PSP UV is a planar projection of position (exact linear fit). The first 4 bytes of the Xbox vertex are NOT a planar UV (u8.8-ish texel coords into a tile atlas, values 0x18..0x50 << 8); Xbox field order: (4 bytes tex coords, s16 x,y,z, s16 nx,ny,nz).
- Level .tex = baked surface textures (Snowblind-style unique per-surface textures, lighting baked in), grouped per world cell. Image records (64 B): u16 w, u16 h, u16 flags 0x10c (bit 0x100 = tiled), u32 descriptor (low 17 bits = offset, high bits = page). PSP images are ~half the Xbox size in each axis (13→7, 148×140→76×70) → "Xbox standard" = 2× resolution.
- Tiled descriptor: u32 base (colour-pair table: 4-byte entries {a, b, b, 0}), then runs {s8 c0, s8 r0, s8 c1, s8 r1} + (c1−c0+1)(r1−r0+1) u32 tile pointers (16×16 tiles: 148×140 → 10×9), terminated 0xFF. Tiles are a compressed bitstream (variable size, ~46-92 bytes) — codec still to find in the XBE (texture-page cache at 0x442f78, 1 KB pages, swizzle table built at 0x72de1, per-image setup 0x72d24, load loop 0x7348a).

## Stage 11 — level texture codec solved (`tools/leveltex.py`)
- Reimplemented the XBE tile decoder (0x73684). Tiled images: 16×16 tiles of 8-bit palette indices, Huffman-coded (MSB-first over little-endian u16 words, canonical tables: u32 n, n u16 symbols, first[18], limit[18], 8-bit fast lookup). Symbols: <0x100 literal; 0x100-0x104 copy neighbour at −1, −16, −17, −15, −2; ≥0x105 context table ctx[prev][sym−0x105] (256×8 bytes). Codebook base = palette (256 × RGBA, alpha 0 = opaque) + ctx + Huffman tables, shared per group.
- Raw images (flag 0x4000) are also supported by the game: palette + w·h pixels, no Huffman → easiest write path for converted levels.
- Game boosts palette saturation ×1.3 at upload (0x73909).
- Verified on Xbox and PSP E1L7: same artwork; PSP at half resolution and sometimes packed differently in the atlas.

## Stage 12 — world mesh format complete, converter plan
- Xbox mesh descriptor (record +0 → 0x80 bytes): {u32 vp, u32 nverts, u32 ip, u32 nindices, runtime zeros}. vp → u32 byte size + vertices of 16 bytes {s16 x,y,z, s16 nx,ny,nz, s16 u,v}; ip → u16 indices, one triangle strip with degenerate joins. Loader 0x78fe6: copies both into D3D buffers, negates nverts as a "done" flag (shared descriptors OK). Record +4 = 1 on Xbox.
- UV: Xbox u = texel / pow2(image w) · 32768; PSP u = texel / image w · 32768. Record +0x20 = image record offset in the cell's .tex group (0x40 + 64·k), +0x34 = group id.
- Object types (record flags & 0xC880): 0 = plain mesh. Swarm (ebonus4) and ebonus2 are all plain; others have a few 0x80/0x4000/0x8000 objects (to do).
- World relocation function 0x78de1 lists every header pointer: h1, h6 (grid, cells relative to h30), h8 (0x24-byte recs, +0xc ptr), h9 objects, h14, h19, h21 (count = word at +0x52), h25 (filled from the .tex table at load), h27 (embedded texture), h32.
- Plan: keep the PSP .world, append Xbox descriptors + geometry at the end, repoint records → nothing else moves.
- env.lmp / waterenv.lmp are identical generic maps in every level (PSP 64², Xbox 128²) → use the Xbox files.
- h27 = embedded .tex (PSP fmt 0x00/flags 0xA0/hdr 0x80 swizzled 8-bit → Xbox fmt 0x04/0xC0/hdr 0x40 linear; fits in place), followed by more data (Xbox: 0x40 zeros, then {-15,-15,30,30,…} + s16 grid; PSP layout differs) — still to identify.

## Stage 13 — challenge missions converted (update 6, untested in game)
- `tools/level_psp2xbox.py`: PSP world kept, meshes → Xbox descriptors/VB/IB appended, embedded tex converted and appended (h27 repointed); special objects (0x80/0x4000/0x8000 = platform-independent settings blocks) left as-is.
- `tools/leveltex.py` encoder: Huffman tiles (literal + left/up copy symbols), one codebook per palette; lossless round trip on all 372 ebonus4 images.
- Textures: per-channel Lanczos 2× (max 512), mapped to the image's own palette colours; groups capped at 0x160000 bytes (largest real Xbox group 0x166a49) — 5 ebonus1 groups fell back to 1.5×.
- Script natives and objects.ob assets all exist on Xbox; gametext already has all ebonus strings; levels.gdt gets the 4 PSP rows appended (out/gamedata.lmp).
- Winding is not consistent in real Xbox level strips either → culling off for world geometry.
- Delivered jlh_update6_challenges.zip (4 levels + gamedata.lmp + frontend.lmp with challenges + difficulties).

## Stage 14 — Xbox main menu had no Challenge Missions item (fixed)
- Correction: the Xbox main menu is New Game, Continued Play, Load, Options, Extras, Credits (6 items, names gs50/51/52/54/62/55 set by the XBE FRONTEND handler 0x14eb12). Challenge Missions (gs53) is item 3 only on the PSP; the earlier `i == 3 → 9` edit did nothing useful on Xbox.
- The missions screen (frame 'missions'), CMD_GET_CHALLENGE_MISSIONS and the players screen's bChallenge → CMD_START_CHALLENGE path all exist on Xbox, plus an unused menu6 slot below Credits.
- `patch_menus.py frontend_challenge`: nItems = 7, menu6 text = gs53 (CMD_UISTRING), item 6 → bChallenge = 1, gotoFrame 203. Plus the difficulty unlock. Replaces the old 'frontend' variant.
- 6b: menu6 had no name (CMD_UISTRING from the root timeline didn't reach menu6) → XBE patch build_menu7 (FRONTEND loop to 7, index 6 = "gs53" via caves 0x1616E1/0x161811/0x162CA1). Selecting it crashed (cause not yet known; asked user for timing + whether gamedata.lmp was installed).
- 6c: XBE menu7 patch removed (froze at title). menu6 text set in Flash to '~~U:uistrings,gs53' (diagnostic: same key form as mission names).
- 6d: '~~U:' key strings in text fields crash Xbox (user test). menu6 and the four mission names now plain ASCII; CMD_GET_CHALLENGE_MISSIONS kept for mission indices.
- 6e: likely real cause of 6a-6d crashes: patches padded with End (0x00) bytes skipped by a jump; the Xbox Flash player stops at End. Now padded with dummy pushes. (Also: the 6b XBE menu7 patch may have been fine; it shipped with the same padding.)
- 6f: ROOT CAUSE of the name/navigation/bChallenge bugs: the Xbox Flash player reads only the FIRST value of a multi-value Push (original menus never use them: 0 of 6000+). So `nItems=7`, `bChallenge=1` and the text pushes silently failed (nItems undefined → wrap to missing menu7 → setTarget falls back to root → play runs into frame 19 'main_psp_diff'; bChallenge unset → players screen starts a normal new game). All patches now use one value per Push, pad with one-value pushes, and set text via CMD_UISTRING (setTarget + trace), like the Difficulty screen. Rules for future SWF patches: single-value pushes, no End-byte padding, text only through XBE commands.

## Stage 15 — starting a challenge (in progress)
- Players screen (button113 0xc200): numPlayers = feVar (0 = one player, 1 = two); Xbox + two players → nextFrame (controller check); bChallenge == 1 → trace "CMD_START_CHALLENGE,<numPlayers>,<map>" (map = mission%d = ~~Levels row index 60-63, set by CMD_GET_CHALLENGE_MISSIONS).
- **The Xbox XBE has no START_CHALLENGE command** (string absent) → the trace is ignored ("select does nothing").
- Command dispatch (0x14f2fc): CMD_<name> by first letter: <'H' 0x14baa1, 'H'-'N' 0x14c675, 'O'-'U' 0x14fe61, ≥'V' 0x14c9bb (args: name, str, int).
- START_GAME,a,b (0x15047c): players 0x2c2f90 = a+1, difficulty 0x1de564 = b+1, new-game init 0x7139d(0), then 0x14903d(-1) (start request: flag 0x46a3b0 = 1, arg 0x1e8fec).
- WARP2LEVEL,n (debug, 0x14ca1d): 0x14903d(n). Main loop 0x149720: start request → mode 0x1e9061: 0/1 → 0x1495cf (ignores arg), 2 → 0x148eec.
- Level-by-name switch: 0x45587 loop over level table (0x1e0010 entries, stride 0xb8) → 0x148e2d(0x7ed93(index), x) sets current level 0x1e8fe0 and mode 2. 0x1e8fe0 = current level row.
- Plan: implement START_CHALLENGE in the XBE = START_GAME init with the given players + set current level row (0x1e8fe0) / use the level-by-name path, so the new game begins at the ebonus row instead of e1l1.
- 6g: players screen challenge branch now sends CMD_WARP2LEVEL,<map> (0x454d5 copies ~~levels row name into next-level buffer 0x2c44d0). START_GAME deliberately not sent (0x7139d new-game init would reset the loaded profile). Untested.
- 6h: BUG: build_dialog wrote 76-byte records (Xbox = 80). Fixed; ebonus gobs repaired. Sent test A (Xbox e1l7 as ebonus4) / B (converted PSP e1l7 as ebonus4).
- 6j: ROOT CAUSE of black screen: loader 0x79231 compacts the world after making D3D buffers: memmove(min_geom, min_geom + Σ(vbsize + 2·ni), …) and subtracts that size from header pointers above it. Descriptors interleaved with geometry were destroyed. Converter now writes all descriptors first, then one packed geometry block (per mesh: u16 indices | u32 vbsize | vertices), like the Xbox files. All 4 ebonus gobs rebuilt.
- 6m: Swarm crash = too much texture data: each half of the upscaled groups loads, all together crash (5.4 MB .tex; working sets ≤ 4.5 MB). Encoder now uses all 5 neighbour-copy symbols; convert_tex enforces LEVEL_BUDGET = 2.5 × PSP .tex size (Xbox/PSP e1l7 = 2.45) by stepping the largest groups down 2 → 1.5 → 1.25 → 1. Results: ebonus1 2.49x (42/79 groups at 2x), ebonus2 2.47x, ebonus3 2.48x, ebonus4 2.46x (13/16 at 2x).

## Stage 16 — hero maxing + Chapter Select (update 7, untested)
- Hero record (0x1DF638 + id·0x78): +0 lock, +1 costumes, +2 pending costume, +3 level (max 20, ~~GeneralPerLevel expPoints/statPoints), +4 unspent points, +8/+0xC/+0x10 XP floats, +0x14 nine 11-byte slots {u8 rank (max 5, USE_CREDIT 0x7211e), 5 × (u8 boost type, u8 boost level)} = powers then stats. 0x71310(hero, level) sets level/XP/points; 0x70c94(hero, v) sets all 9 slot ranks.
- levels.gdt charXPLevel = comma list "code:level" (codes sm mm bm ww fl gl za gk gh ga am hg hu sg bc), applied at level change (0x1fe79 → 0x7208f); only e4l1 uses it (ww:4).
- Challenges were level 1 because the PSP requires a finished game (heroes come from that save); the warp loads none.
- patch_unlock.build_maxheroes: WARP2LEVEL handler call 0x14903d → W(0x76DD3) → loop over 15 heroes: unlock, 0x70c94(h,5), 0x71310(h,20) (caves 0x1604A4, 0x15D0D3, 0x161811, 0x163F23, 0x1616E1), then 0x14903d.
- tools/swfedit.py: SWF rebuilder (DoAction + DefineButton2 condaction resize, branch fix-ups, byte-identical identity rebuild).
- tools/patch_chapter.py: Missions screen = 4 pages (challenges, episodes 1-4/5-8/9-11 by first-level name), episode → chapterRow + New Game flow (mode SAVE, gotoFrame 36); difficulty start adds CMD_WARP2LEVEL,<row>. Episode first rows: 0 7 13 18 24 28 30 39 44 52 56.

## Stage 17 — character select per episode (update 8, untested)
- levels.gdt: fixed episodes use Player1/Player2 (model names); free ones use teamID (float, team index) + charSel "c<teams>,<heroes per team>" on the first level (+ charCut cutscene) + charExclude (hero codes greyed out).
- Fliers = models with fly_* animations in modeldata.gdt: superman, supergirl, wwoman, mmhunter, hawkgirl, glantern/gl_hal/gl_kyle, zatanna. Ground: bm fl ga am hu bc.
- tools/build_gamedata.py: ebonus rows + Episodes 1-5, 7, 10 → team 0, charSel c1,2 on e1l1a e2l1 e3l1 e4l1 e5l1 e7l1 e10l1 e10l2 e10l5; charExclude ground heroes on e2l1, e7l1, e10l5.
- Vent crash (ebonus1): follows the DESTINATION (swap test), happens on pressing "enter vent", independent of texture scale. Start vents: t01 (-1261,826) → t02 (-3306,625: fans bigfana, camera Line 'cambar', Stop-Fan minigame), t03 (-457,779) → t04 (3300,773: blockers). Waiting for which one crashed originally.

## Stage 18 — vent crash fixed, costumes (update 9)
- Vent System (ebonus1): the crash on entering a start vent was texture memory. Teleporting loads the destination area's textures on top of what is loaded; at the 2.5x budget that overflowed. All textures at 0.5x of the upscaled size (T1 test) works: out/levels/ebonus1.{gob,tex} replaced with that build (user confirmed).
- Costumes: hero record +1 = low nibble worn costume, bits 5/6 = alternate costumes 1/2 owned (0x7c636; costume 0 always). CMD_GET_TEAMS sends costumes<id> = number owned (0x7cbdb) for heroes 0-6, "1" for 7-14 (no alternate models). Character select: X cycles costumes when costumes<id> > 1, skipping unowned (CMD_IS_COSTUME_AVAIL). Models per hero (0x7c6e3 switch): sm supr_blk/supr_e2, mm mm_cone/mm_suit, bm batmn_tk/batm_blu, ww wwtoga/wwblack, fl flash_jg/flash_ww, gl glantrn2/glantrn3, za z_clasic/zat_ic.
- patch_unlock.build_maxheroes: unlock cave E now jumps to new cave F (0x161AE1, 15-byte int3 run after `ret 0x14`): or byte [eax+0x1DF639],0x60; jmp C. Every WARP2LEVEL start (chapter select, challenges) owns all costumes.
- Update 9 was superseded before install (user wanted changes) -> update 10.

## Stage 19 — story pairs in New Game, hidden costumes, Continued Play (update 10, untested)
- New code space: XBE headers end at 0xDF0, file is zero to 0x1000 (.text raw starts there) and the header page is mapped at 0x10000. SizeOfHeaders 0xDF0 -> 0x1000; code at 0x10E00 (135 bytes used).
- Story flag = bit 4 of Superman's record +1 byte. New Game (0x713DB `mov [eax-1],0x10`, also the boot reset) sets bit 4 for all heroes; nothing reads it (costume 0 short-circuits in 0x7c636, buying ORs only bits 5-7). Saved with the profile.
- GRANT (0x10E00): all heroes +1 = (worn) | 0x60, Superman/WW | 0x80, bit 4 cleared. Called from W2 (WARP2LEVEL: maxheroes A, GRANT, jmp 0x14903D) and LH (after save load 0x71472 when 0x46BC52 = 1, set only by CMD_LOAD_REPLAY = Continued Play; CMD_LOAD_GAME clears it).
- SEL (0x46EEC call): level start reads the greyed-out list from "charExclNew" while the story flag is set, else "charExclude". gamedata: new column charExclNew = original charExclude, but all heroes except the original Player1/Player2 on the selection rows of the converted fixed episodes (+ e11l3 now converted too).
- Costume 3: Superman supr_kdr (native switch), WW armour wwo_armd/hud_ww_a/sta_ww_a = the Episode 11 path 0x7C6B2. WWA (jmp at 0x7C692): WW worn costume 3 -> armour path, else original Episode 11 / wwo_armd check. Character-select portraits already have frame 4 for Superman (sprite 246) and WW (212). char_sel.swb X handlers: nextCostume limit '3' -> '4' at 758793, 759060 (P1), 825444, 825711 (P2).
- Stage 19b: patch_unlock --mode standard (new default): no unlock changes (original new-game locks, no lock clearing on load; SG/BC via shop items 22/23), all other logic kept. Single out/default.xbe.

## Stage 20 — greyed-out list overflow, PSP story levels (update 11, untested)
- charExclude is parsed (0x1B0B3) into 4 dword slots 0x2ADCF4..0x2AD00 and tested by 0x1B49F (also used by the archive preload 0x1B704 and char add 0x1B823). Lists > 4 heroes overflowed into the cutscene-name buffers at 0x2AD04 and were ignored after the 4th. patch_unlock.build_exclmask: slot 0 becomes a 15-bit mask (init 0; `bts [slot0],hero`, pointer no longer advances; test = `bt [0x2ADCF4],hero; setc al`).
- 0x1E0010 is the PLAYER count (stride 0xB8 array 0x44A820 is per player), not the level count (Stage 15 note was wrong). Level rows are read via the table DB (vtable +0x4C count, +0x5C name): no fixed level array. PSP engine uses 68 rows.
- PSP story levels are new geometry (bbox match vs Xbox neighbours 1-12 %; same level PSP/Xbox e1l7 = 87 %). Converted at 0.5x textures (build_psp_story.py): pspe1 -> e1l8, pspe5 -> e5l5, pspe11 -> e11l2. Music = first stream of Xbox e1l6 / e5l2 / e11l4 .vat.
- Links: e1l6 "e1l7"->"e1l8"; e11l3 "e11l4"->"e11l2" (cs37 kept); e5l2 movieStartAndTransition("cs19","e5l3") -> native renamed simpleNewWorld (reads only params[1], 0x12551) + "cs19"->"e5l5"; e5l5 keeps cs19 -> e5l3 (PSP order).
- levels.gdt: rows e1l8/e5l5/e11l2 inserted before ebonus1 (challenges stay the last 4; chapter rows < 60 unchanged). gametext: uistrings e1l8/e5l5/e11l2, scriptstrings pspe1title/pspe1intro/pspe1end/pspe5introtitle/pspe5/pspe11, missionstrings e11part4 (build_gametext.py).
- tools/verify_level.py: structural checker (gob, 80-byte dialog, descriptor-below-geometry packed layout, vbsize, index range, tex decode of every image, texture refs). Passes Xbox e1l6/e1l7, ebonus1-4 and the 3 new levels.

## Stage 21 — first-level select, challenge restart, shop (update 12, untested)
- The greyed-out list / team setup (0x46DF1 -> 0x459AF -> 0x1B090) runs only when the next-level buffer 0x2C44D0 holds a name. New Game (START_GAME 0x1504B6) and the post-load start (0x149AF4) request -1, which leaves it empty: the first level's character select kept the previous list (story pairs in New Game Episode 1 failed). New Game now requests 0 (0x45550 copies row 0 = e1l1a, same as Chapter Select Episode 1); CPS: after a Continued Play load request 0, after Load Game -1 (0x46BC52).
- 0x2C44D9 = current level name ("charsel" during the select pseudo-level); 0x2C44D0 = next level; 0x2C3025 = allow reloading the same level.
- Restart Episode (CMD_RESTART_EPISODE: 0x46BC51 -> 0x148FB3 -> 0x67FCE) restores the episode-start snapshot 0x3F9130 (taken by 0x683D1 only for names matching "e%dl%d") and goes to "e%dl1" (+"a" for 1). Challenges never take one -> blank hero table + "e0l1" -> crash. RST: current level "ebon..." -> same resets (0x3A06C(8), 0x6CA36, 0x69054), next = current, 0x2C3025 = 1.
- Shop: 0x7CC2F(item 1..23, v) sets bought flag 0x437357+item and applies: costumes 0x7CBFB(hero, c) (incl. Superman costume 3), hero unlocks 0x71521(hero 7..14, level 5; only if locked). BUYALL buys every unbought item; called by W2 (before maxing) and LH (Continued Play).
- gamedata: Episode 5 e5l1 charExclude = ground heroes.

## Stage 22 — story pairs without select, Continued Play -> Chapter Select (update 13, untested)
- User: story-pair select in New Game still not greyed correctly -> dropped: in story mode the level table's charSel (0x46E27 select setup, 0x7F76F team source) and teamID (0x7F831) are read from story copies charSelNew / teamIDNew (stubs SELCS / PUSHCS / SELTID in the header page, same story flag as SEL). Team source order at level start (0x7F762): charSel -> team 0, else teamID, else the "player1"/"player2" columns (only read there). Player1/Player2 are kept in every row now.
- Continued Play crashed on every save (cause not found; it went through LOAD_REPLAY + the LH/CPS hooks). Replaced: frontend gameWon starts at 1 (it gates only item 1, Challenge Missions and the top difficulties); item 1 text = uistrings "chsel" (new row, 5 languages); item 1 select -> bChallenge=1, chStart=1, gotoFrame 203; missions init chPage = chStart; Challenge Missions sets chStart=0.
- Stage 23 (update 14): page flips: challenge page 0 wraps onto itself, episode pages 1-3 wrap among themselves (sentinel 9 in the up/down handlers).

## Stage 24 - Challenge Missions overwrote story saves (2.1.1)
- Level changes (0x148E2D(row, x, autosave)) store the autosave request in 0x46A3A8 (0x148E74 `mov [0x46A3A8],eax`). At the next level start 0x148EEC calls 0x68ABA(current slot 0x46BC5C != -1) and the pause menu init sends CMD_AUTOSAVE_STATUS (0x14BCBF reads 0x46A3A8 -> autosaveStatus); > 0 opens pause.swb's /auto_save screen, which asks for a slot when none is set (CMD_CHANGE_SAVE_SLOT / CMD_SLOT_TO_SAVE).
- Challenges start with CMD_WARP2LEVEL and keep whatever slot is current: a loaded story save was autosaved over, and with no slot the player was asked for one.
- NOAS (header 0x10F32, called from 0x148E74): if the current (0x2C44D9) or next (0x2C44D0) level name starts with "ebon", store 0 instead. Seed 0x00010F32 added to jlh_seeds.json.
- Runtime (toolkit kernel_file.c): before an overwrite/write open or delete of a save file, the file is copied to <user-data root>\backup\<path>.<NNNN>.bak (one copy per file per 10 s).
