#!/usr/bin/env python3
"""
sf_install.py - what the Speed Force setup runs after copying its files.

  python sf_install.py --xbox <Xbox dump .iso> --psp <PSP dump .iso> --app <install dir>
                       [--saves <folder>] [--tools <dir>] [--allow-unknown-dumps] [--keep-build]

On Windows the setup puts everything in <install dir>\\_build. On Linux (the AppImage) the
compilers stay in the AppImage (--tools: llvm/, cmake/, ninja/) and the same Windows
SpeedForce.exe is cross-compiled with LLVM-MinGW.

Everything happens on the player's own PC, from the player's own dumps:
  1. check the dumps        5. translate the patched Xbox program to C (xboxrecomp)
  2. extract both discs     6. compile it with the bundled LLVM-MinGW, CMake and Ninja
  3. rebuild the mod        7. install the game beside the executable
  4. place the game files   8. clean up
The setup carries no game code or data.
"""
import argparse
import platform
import hashlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)                # <app>\_build
sys.path.insert(0, HERE)

KNOWN = {   # SHA-1 of the dumps this release was made and tested with
    'xbox': {'76ec8ba8466ecc32b5129c2513707c8e59f687e8': 'Justice League Heroes (Xbox, USA)'},
    'psp': {'87055c512472e8fd160361a84c2fb5444bba422d': 'Justice League Heroes (PSP, USA)'},
}
STEPS = 8
LOG = None
# Where each step starts on the setup's progress bar (per mille); the setup reads the
# "@@<per mille>|<text>" lines this script prints.
STEP_AT = {1: 0, 2: 30, 3: 60, 4: 560, 5: 570, 6: 760, 7: 960, 8: 985}
# The mod build's own milestones inside step 3 (fraction of the step, from timed runs).
MOD_AT = {'characters': 0.01, 'levels': 0.02, 'ebonus2': 0.23, 'ebonus3': 0.32, 'ebonus4': 0.40,
          'e1l8': 0.47, 'e5l5': 0.60, 'e11l2': 0.80}
MOD_TEXT = {'characters': 'Supergirl and Black Canary', 'levels': 'Challenge mission 1 of 4',
            'ebonus2': 'Challenge mission 2 of 4', 'ebonus3': 'Challenge mission 3 of 4',
            'ebonus4': 'Challenge mission 4 of 4', 'e1l8': 'S.T.A.R. Labs Sub Level',
            'e5l5': 'Mars Lower Caves', 'e11l2': 'Fortress Perimeter'}


def say(m):
    line = time.strftime('%H:%M:%S ') + m
    print(line, flush=True)
    if LOG:
        LOG.write(line + '\n')
        LOG.flush()


def progress(permille, text=''):
    print(f'@@{int(permille)}|{text}', flush=True)


def step(n, m):
    say(f'[{n}/{STEPS}] {m}')
    progress(STEP_AT[n], f'Step {n} of {STEPS}: {m}')


def mod_log(m):
    say('  ' + m)
    key = m.strip()
    if key in MOD_AT:
        span = STEP_AT[4] - STEP_AT[3]
        progress(STEP_AT[3] + span * MOD_AT[key], MOD_TEXT[key])


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while True:
            b = f.read(16 << 20)
            if not b:
                return h.hexdigest()
            h.update(b)


def run(cmd, cwd=None, env=None):
    say('  > ' + ' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd))
    # Windows looks a bare program name up on THIS process's PATH, not on env['PATH'] (where the
    # build tools are), so find it on env's PATH first.
    if env and not os.path.isabs(cmd[0]):
        exe = shutil.which(cmd[0], path=env.get('PATH'))
        if not exe:
            raise RuntimeError(f'{cmd[0]} was not found in the build tools ({env.get("PATH", "")[:300]})')
        cmd = [exe] + list(cmd[1:])
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors='replace')
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if LOG:
            LOG.write('    ' + line + '\n')
        if line.startswith('[') and '/' in line[:12]:          # Ninja: "[n/total] ..."
            try:
                a, b = line[1:line.index(']')].split('/')
                span = STEP_AT[7] - STEP_AT[6]
                progress(STEP_AT[6] + span * int(a) / max(1, int(b)), f'{a} of {b} files')
            except ValueError:
                pass
        tail = (tail + [line])[-40:]
    if p.wait():
        raise RuntimeError(f'{os.path.basename(str(cmd[0]))} failed (exit {p.returncode}):\n'
                           + '\n'.join(tail))


def pymod(module, args, cwd):
    """Run a toolkit module with the bundled Python (whose path is fixed by its ._pth)."""
    code = ('import sys, runpy; sys.path.insert(0, %r); sys.argv = [%r] + %r; '
            'runpy.run_module(%r, run_name="__main__")' % (cwd, module, list(args), module))
    run([sys.executable, '-c', code], cwd=cwd)


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument('--xbox', required=True)
    ap.add_argument('--psp', required=True)
    ap.add_argument('--app', required=True)
    ap.add_argument('--allow-unknown-dumps', action='store_true')
    ap.add_argument('--keep-build', action='store_true')
    ap.add_argument('--saves', help='a folder (or file) of Xbox saves to bring over')
    ap.add_argument('--tools', help='where llvm/, cmake/ and ninja/ are (default: next to setup/)')
    a = ap.parse_args()
    app = os.path.abspath(a.app)
    os.makedirs(app, exist_ok=True)
    LOG = open(os.path.join(app, 'install.log'), 'w', encoding='utf-8')
    t0 = time.time()
    say(f"Speed Force {os.environ.get('SF_VERSION', '(unknown version)')} setup on {platform.platform()}, "
        f"Python {sys.version.split()[0]}")
    try:
        install(a, app)
    except Exception as e:
        import traceback
        LOG.write(traceback.format_exc())
        LOG.flush()
        if isinstance(e, OSError) and getattr(e, 'filename', None):
            say(f'ERROR: {e.strerror or e}: {e.filename}')
        else:
            say('ERROR: ' + str(e))
        say('The full log is in ' + os.path.join(app, 'install.log'))
        return 1
    say(f'Done in {int(time.time() - t0) // 60} min.')
    progress(1000, 'Done')
    return 0


def install(a, app):
    work = os.path.join(BUILD, 'work')
    tk = os.path.join(BUILD, 'toolkit')
    game = os.path.join(BUILD, 'game')
    import sf_extract
    import sf_buildmod

    step(1, 'Checking your dumps (this reads both discs once)')
    for kind, path in (('xbox', a.xbox), ('psp', a.psp)):
        if not os.path.isfile(path):
            raise RuntimeError(f'{kind} dump not found: {path}')
        h = sha1(path)
        if h in KNOWN[kind]:
            say(f'  {kind}: {KNOWN[kind][h]} (verified)')
        elif a.allow_unknown_dumps:
            say(f'  {kind}: unknown dump {h} - continuing as asked')
        else:
            raise RuntimeError(
                f'The {kind.upper()} dump is not one this release knows (SHA-1 {h}).\n'
                'Speed Force needs the USA releases. Check that the dump is complete and '
                'unmodified, or run the setup again and allow unknown dumps.')

    step(2, 'Extracting both discs')
    for kind in ('xbox', 'psp'):
        d = os.path.join(work, kind)
        shutil.rmtree(d, ignore_errors=True)
    sf_extract.extract_xbox(a.xbox, os.path.join(work, 'xbox'), progress=lambda m: None)
    sf_extract.extract_psp(a.psp, os.path.join(work, 'psp'), progress=lambda m: None)

    step(3, 'Rebuilding the mod from your dumps (about 15-20 minutes)')
    mod = os.path.join(work, 'mod')
    shutil.rmtree(mod, ignore_errors=True)
    sf_buildmod.log = mod_log
    sf_buildmod.build(os.path.join(work, 'xbox'), os.path.join(work, 'psp'), mod)

    step(4, 'Placing the game files')
    res = os.path.join(app, 'res')
    shutil.rmtree(res, ignore_errors=True)
    shutil.move(os.path.join(work, 'xbox', 'res'), res)
    for n in os.listdir(os.path.join(mod, 'res')):
        shutil.copy2(os.path.join(mod, 'res', n), os.path.join(res, n))
    shutil.copy2(os.path.join(mod, 'default.xbe'), os.path.join(app, 'default.xbe'))

    step(5, 'Translating the game program to C (xboxrecomp)')
    gf = os.path.join(tk, 'game_files')
    os.makedirs(gf, exist_ok=True)
    shutil.copy2(os.path.join(mod, 'default.xbe'), os.path.join(gf, 'default.xbe'))
    xbe = os.path.join('game_files', 'default.xbe')
    seeds = os.path.join(game, 'seeds', 'jlh_seeds.json')
    gen = os.path.join(game, 'src', 'recomp', 'gen')
    shutil.rmtree(gen, ignore_errors=True)
    pymod('tools.xbe_parser', [xbe, '--json', os.path.join('game_files', 'default_analysis.json')], tk)
    run([sys.executable, os.path.join(game, 'seeds', 'add_cave.py'),
         os.path.join(gf, 'default_analysis.json'), os.path.join(work, 'cave_seeds.json')], cwd=tk)
    pymod('tools.disasm', [xbe, '--force', '--seed-functions', seeds], tk)
    pymod('tools.func_id', [xbe], tk)
    pymod('tools.abi_analysis', [xbe], tk)
    # the mod's code in the XBE header is added to the lifter's section layout
    # --back-edge-yield and the KickOff spin-wait site: the deterministic mode online play runs in
    run([sys.executable, os.path.join(game, 'seeds', 'recomp_with_cave.py'), xbe, '--all', '--split', '250',
         '--back-edge-yield', '--spin-waits', os.path.join(game, 'seeds', 'spin_waits.json'),
         '--gen-dir', gen], cwd=tk)

    step(6, 'Compiling (about 5-15 minutes, depending on the CPU)')
    tools = os.path.abspath(a.tools) if a.tools else BUILD
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([os.path.join(tools, 'llvm', 'bin'), os.path.join(tools, 'cmake', 'bin'),
                                   os.path.join(tools, 'ninja'), env.get('PATH', '')])
    bdir = os.path.join(work, 'build')
    deps = os.path.join(BUILD, 'deps')
    llvm = os.path.join(tools, 'llvm', 'bin')
    ninja = shutil.which('ninja', path=os.path.join(tools, 'ninja'))
    t = 'x86_64-w64-mingw32-'

    def tool(*names):       # the first of names in the build tools, as a full path for CMake
        for n in names:
            f = shutil.which(n, path=llvm)
            if f:
                return f.replace('\\', '/')       # CMake reads backslashes as escapes
        raise RuntimeError(f'{names[0]} is missing from the build tools ({llvm})')

    compilers = ['-DCMAKE_C_COMPILER=' + tool(t + 'clang', 'clang'),
                 '-DCMAKE_CXX_COMPILER=' + tool(t + 'clang++', 'clang++'),
                 '-DCMAKE_RC_COMPILER=' + tool(t + 'windres', 'windres', 'llvm-windres')]
    if os.name != 'nt':     # cross-compile the same Windows program
        compilers += ['-DCMAKE_SYSTEM_NAME=Windows', '-DCMAKE_SYSTEM_PROCESSOR=AMD64',
                      '-DCMAKE_AR=' + tool('llvm-ar'), '-DCMAKE_RANLIB=' + tool('llvm-ranlib')]
    if ninja:
        compilers.append('-DCMAKE_MAKE_PROGRAM=' + ninja.replace('\\', '/'))
    run(['cmake', '-S', game, '-B', bdir, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release'] + compilers + [
         '-DXBOXRECOMP_DIR=' + tk, '-DXBOXRECOMP_ENHANCE=ON', '-DXBOX_INPUT_SDL_WIN=ON',
         '-DSDL3_DIR=' + os.path.join(deps, 'SDL3', 'cmake'),
         '-DXBOXRECOMP_DSP56300_ARCHIVE=' + os.path.join(deps, 'dsp56300.tar.gz'),
         '-DXBOXRECOMP_LIBRASHADER_ARCHIVE=' + os.path.join(deps, 'librashader.zip')], env=env)
    run(['cmake', '--build', bdir, '--parallel'], env=env)

    step(7, 'Installing')
    shutil.copy2(os.path.join(bdir, 'jlh_recomp.exe'), os.path.join(app, 'SpeedForce.exe'))
    for n in os.listdir(bdir):
        p = os.path.join(bdir, n)
        if n.lower().endswith('.dll'):
            shutil.copy2(p, os.path.join(app, n))
    if os.path.isdir(os.path.join(bdir, 'shaders')):
        shutil.copytree(os.path.join(bdir, 'shaders'), os.path.join(app, 'shaders'), dirs_exist_ok=True)
    shutil.copy2(os.path.join(deps, 'SDL3', 'x86_64-w64-mingw32', 'bin', 'SDL3.dll'), app)
    rt = os.path.join(BUILD, 'runtime')
    for n in os.listdir(rt):
        shutil.copy2(os.path.join(rt, n), os.path.join(app, n))

    os.makedirs(os.path.join(app, 'saves'), exist_ok=True)
    if a.saves:
        say('  importing your saves')
        try:
            run([sys.executable, os.path.join(BUILD, 'setup', 'sf_saves.py'), '--in', a.saves,
                 '--out', os.path.join(app, 'saves')])
        except RuntimeError as e:          # a save that can't be used must not fail the install
            say('  some saves could not be imported (see saves\\import.log): ' + str(e).splitlines()[0])

    step(8, 'Cleaning up')
    if not a.keep_build:
        # the build tools and sources are no longer needed (the running Python stays until
        # the uninstaller removes it)
        shutil.rmtree(work, ignore_errors=True)
        for d in (('llvm', 'cmake', 'ninja') if not a.tools else ()) + ('toolkit', 'game', 'deps', 'jlh-upscale', 'runtime'):
            shutil.rmtree(os.path.join(BUILD, d), ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
