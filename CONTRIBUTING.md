# Contributing

Thanks for helping. A few rules keep the project legal and reviewable:

1. **Never commit anything from the game**: no `default.xbe`, no `res/` files, no generated
   recompiled code (`game/src/recomp/gen`), no analysis output (`toolkit/tools/*/output`),
   no screenshots of copyrighted artwork beyond normal gameplay, no save files. `.gitignore`
   blocks the usual paths; check `git status` before committing.
2. Keep mod changes as tools in `setup/modtools/` that transform the original files, so the setup can
   rebuild them from each player's own dumps.
3. Describe what you tested: which episode, which settings (frame generation, upscaler, AA).
4. Code style: follow the surrounding code. C for the runtime, Python 3 (standard library +
   NumPy/Pillow) for tools.

Bug reports: use the issue template and attach `install.log` or the game's log, never game files.
