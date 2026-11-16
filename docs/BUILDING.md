# Building

## The setup (Speed Force Builder)
Requirements: Windows, Python 3.13, LLVM-MinGW, Visual Studio 2022+ (C++ workload, only for the
upscaler bridge), internet access for the downloads.

    (download into payload_src\: python-embed.zip, pysite\ (pip install --target numpy pillow capstone),
     cmake.zip, ninja.zip, llvm-mingw.zip, SDL3\ (SDL3 3.4.20 mingw devel), dsp56300.tar.gz,
     librashader.zip - the URLs are in toolkit/cmake/*.cmake and in this file)
    setup\build_upscale.bat            # jlh_upscale.dll (SDKs unpacked in payload_src\sdk, see the script)
    launcher\build_launcher.bat        # SpeedForceLauncher.exe, SpeedForceBuilder.exe, sfpack.exe
    python setup\make_payload.py       # the build kit, in payload\
    launcher\sfpack.exe payload.sfar payload=_build launcher\SpeedForceLauncher.exe=SpeedForceLauncher.exe
    copy /b launcher\SpeedForceBuilder.exe + payload.sfar dist\SpeedForce-Setup-2.0.0.exe

The builder unpacks the build kit (LZMS, Windows' own Compression API) into `<install>\_build`,
runs `_build\python\python.exe -u _build\setup\sf_install.py --xbox <iso> --psp <iso> --app <install dir>
[--saves <folder>]` and follows its `@@<per mille>|<text>` progress lines, then adds the shortcuts
and the entry in Windows' installed apps. Scripted: `SpeedForce-Setup-2.0.0.exe /xbox <iso> /psp <iso>
[/dir <folder>] [/saves <folder>]` fills the fields in. `setup\sf_saves.py --in <folder> --out
<install dir>\saves` imports Xbox saves on its own.

## The Linux AppImage
Requirements: Linux x86_64 with FUSE (or use `--appimage-extract-and-run`), and the Windows build
kit's inputs (the same `jlh_upscale.dll`, SDL3, dsp56300 and librashader downloads as above).

    (download into linux_kit/: cpython-3.13.*-x86_64-unknown-linux-gnu-install_only.tar.gz
     (python-build-standalone), wheels/ (pip download --only-binary=:all: --platform
     manylinux_2_28_x86_64 --python-version 3.13 numpy pillow capstone),
     llvm-mingw-*-ucrt-ubuntu-*-x86_64.tar.xz, cmake-*-linux-x86_64.tar.gz, ninja-linux.zip,
     wine-*-amd64-wow64.tar.xz (Kron4ek), dxvk-*.tar.gz, vkd3d-proton-*.tar.gz)
    python3 linux/make_appdir.py --kit linux_kit --deps payload_src --out AppDir
    appimagetool --comp zstd AppDir dist/SpeedForce-2.0.0-x86_64.AppImage

The AppImage's builder copies the
kit into `<install>/_build` and runs `sf_install.py --tools <AppImage>/usr/share/speedforce/tools`;
on Linux `sf_install.py` cross-compiles with `x86_64-w64-mingw32-clang` (`CMAKE_SYSTEM_NAME=Windows`),
so the result is the same `SpeedForce.exe` as on Windows. The launcher then runs it with Proton
(`proton run`, prefix in `~/.local/share/speedforce/proton`), a system Wine, or the bundled Wine
(prefix in `~/.local/share/speedforce/wine`, DXVK/vkd3d DLLs copied into it). Scripted:
`SpeedForce-2.0.0-x86_64.AppImage --setup --xbox <iso> --psp <iso> [--dir <folder>] [--saves <folder>]`;
`--play` starts the game directly.

## Without the setup (developers)
With your own dumps:

    python setup\sf_extract.py xbox <xbox.iso> work\xbox
    python setup\sf_extract.py psp  <psp.iso>  work\psp
    python setup\sf_buildmod.py work\xbox work\psp work\mod      # the mod's files (about 15 minutes)

Then copy `work\mod\default.xbe` to `toolkit\game_files\default.xbe` and run the recompiler
from `toolkit\` (Python with capstone):

    python -m tools.xbe_parser game_files\default.xbe --json game_files\default_analysis.json
    python ..\game\seeds\add_cave.py game_files\default_analysis.json ..\work\cave_seeds.json
    python -m tools.disasm game_files\default.xbe --force --seed-functions ..\game\seeds\jlh_seeds.json
    python -m tools.func_id game_files\default.xbe
    python -m tools.abi_analysis game_files\default.xbe
    python ..\game\seeds\recomp_with_cave.py game_files\default.xbe --all --split 250 --gen-dir ..\game\src\recomp\gen

and build `game\` with CMake + Ninja + LLVM-MinGW (`-DXBOXRECOMP_ENHANCE=ON -DXBOX_INPUT_SDL_WIN=ON
-DSDL3_DIR=...`). Run the executable from a folder holding `default.xbe` and `res\` (the
extracted Xbox files with `work\mod` copied over them), or set `RECOMP_GAME_FILES`.

## Mod tools
`setup/modtools/` holds the tools that made the mod; `docs/mod/FINDINGS.md` documents the formats and
every patch. `sf_buildmod.py` shows the exact order they run in.
