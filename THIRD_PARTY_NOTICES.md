# Third-party notices

Speed Force uses or redistributes the following. Each keeps its own license; full texts are in
the linked projects (and, for the toolkit's dependencies, in `toolkit/LICENSES` and `toolkit/NOTICE`).

| Component | Use | License |
|---|---|---|
| [xboxrecomp](toolkit/README.md) (sp00nz) | Static recompilation toolkit and runtime (forked in `toolkit/`) | MIT |
| [SDL3](https://github.com/libsdl-org/SDL) | Controllers (SDL3.dll ships with the game) | zlib |
| [dsp56300](https://github.com/xemu-project/dsp56300) | Audio DSP JIT, linked into the game | MIT |
| [librashader](https://github.com/SnowflakePowered/librashader) | Optional presentation shaders (librashader.dll) | MPL-2.0 (or GPL-3.0) |
| [NVIDIA DLSS](https://github.com/NVIDIA/DLSS) | nvngx_dlss.dll, NGX static library in jlh_upscale.dll | NVIDIA RTX SDKs license (runtime redistributable with applications) |
| [AMD FidelityFX SDK](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK) | FSR (amd_fidelityfx_*_dx12.dll) | MIT |
| [Intel XeSS](https://github.com/intel/xess) | libxess.dll | Intel Simplified Software License (redistributable) |
| [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) | Compiler bundled in the setup | Apache-2.0 with LLVM exception; mingw-w64 runtime: ZPL / public domain and others |
| [CMake](https://cmake.org) | Build system bundled in the setup | BSD-3-Clause |
| [Ninja](https://ninja-build.org) | Build tool bundled in the setup | Apache-2.0 |
| [Python](https://www.python.org) (embeddable) | Runs the setup's tools | PSF License |
| [NumPy](https://numpy.org) | Mod tools | BSD-3-Clause |
| [Pillow](https://python-pillow.org) | Mod tools (texture scaling) | MIT-CMU (HPND) |
| [Capstone](https://www.capstone-engine.org) | Disassembler for the recompiler | BSD-3-Clause |
| [DejaVu fonts](https://dejavu-fonts.github.io) | Letters in the generated button icons | Bitstream Vera / DejaVu license |
| [Inter](https://rsms.me/inter/) | Lettering in the launcher artwork (launcher/make_art.py) | SIL Open Font License 1.1 |

All trademarks belong to their owners.
