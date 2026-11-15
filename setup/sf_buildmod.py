#!/usr/bin/env python3
"""
sf_buildmod.py - build the Speed Force game files from the player's own extracted dumps.

  python sf_buildmod.py <xbox dir> <psp dir> <out dir> [--sd]

<xbox dir>: the extracted Xbox disc (default.xbe, res/...)
<psp dir>:  the extracted PSP disc (PSP_GAME/USRDIR/...)
<out dir>:  receives default.xbe and res/ - the original Xbox files with the mod applied

Every modified file is made here by the mod tools (modtools/) from the original files:
nothing from the game is shipped. --sd builds the seven PSP-derived levels at the Xbox's
texture budget (as the Xbox mod); the default builds them at the PC's (2x textures).
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, 'modtools')
if not os.path.isdir(TOOLS):                      # repository layout
    TOOLS = os.path.join(os.path.dirname(HERE), 'modtools')
sys.path.insert(0, TOOLS)


def log(m):
    print(m, flush=True)


def run(*args):
    r = subprocess.run([sys.executable, '-I', os.path.join(TOOLS, args[0])] + list(args[1:]),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'{args[0]} failed:\n{r.stdout}\n{r.stderr}')


def find(d, name):
    """A file in d, matched without case (the PSP disc is upper case)."""
    low = name.lower()
    for n in os.listdir(d):
        if n.lower() == low:
            return os.path.join(d, n)
    raise FileNotFoundError(os.path.join(d, name))


def lmp_member(path, member):
    import lmp
    for n, b, _ in lmp.read_bytes(open(path, 'rb').read()):
        if n.lower() == member:
            return b
    raise KeyError(member)


def gob_member(gob, member):
    out, o = None, 0
    while o + 40 <= len(gob):
        name = gob[o:o + 32].split(b'\0')[0].decode('latin-1')
        if not name:
            break
        off, size = struct.unpack_from('<II', gob, o + 32)
        if name.lower() == member:
            return gob[off:off + size]
        o += 40
    raise KeyError(member)


def music_stream(xres, stream):
    """The Xbox recording of a music stream: the first Xbox level that holds it."""
    import level as L
    import lmp
    for n in sorted(os.listdir(xres)):
        if not n.lower().endswith('.gob'):
            continue
        lvl = n[:-4]
        gob = open(os.path.join(xres, n), 'rb').read()
        try:
            lm = gob_member(gob, lvl.lower() + '.lmp')
        except KeyError:
            continue
        for mn, b, _ in lmp.read_bytes(lm):
            if mn.lower() == 'ntsc_dialog.bin':
                for r in L.read_dialog(b):
                    if r['name'] == stream:
                        vat = open(os.path.join(xres, lvl + '.vat'), 'rb').read()
                        return vat[r['offset']:r['offset'] + r['size']]
    raise KeyError(stream)


LEVELS = [   # psp level, new name, music stream
    ('ebonus1', 'ebonus1', 'env_e03_arctic_a.vag'),
    ('ebonus2', 'ebonus2', 'env_e09_brain.vag'),
    ('ebonus3', 'ebonus3', 'env_e11_dark.vag'),
    ('ebonus4', 'ebonus4', 'env_e02_subwy_a.vag'),
    ('pspe1', 'e1l8', 'env_e01_star.vag'),
    ('pspe5', 'e5l5', 'env_e05_mars_a.vag'),
    ('pspe11', 'e11l2', 'env_e11_frtrs_a.vag'),
]


def build(xdir, pdir, out, sd=False):
    xres = os.path.join(xdir, 'res')
    usr = os.path.join(pdir, 'PSP_GAME', 'USRDIR')
    ores = os.path.join(out, 'res')
    os.makedirs(ores, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='sf_mod_')
    try:
        log('executable')
        run('patch_unlock.py', os.path.join(xdir, 'default.xbe'), os.path.join(out, 'default.xbe'),
            '--mode', 'standard')
        log('menus')
        run('patch_menus.py', 'stats', find(xres, 'stats.lmp'), os.path.join(ores, 'stats.lmp'))
        # patch_chapter applies the frontend_challenge patch itself
        run('patch_chapter.py', find(xres, 'frontend.lmp'), os.path.join(ores, 'frontend.lmp'))
        run('patch_charsel.py', find(xres, 'char_sel.lmp'), os.path.join(ores, 'char_sel.lmp'))
        log('game data')
        run('build_gamedata.py', find(xres, 'gamedata.lmp'), find(usr, 'GAMEDATA.LMP'),
            os.path.join(ores, 'gamedata.lmp'))
        run('build_gametext.py', find(xres, 'gametext.lmp'), find(usr, 'GAMETEXT.LMP'),
            os.path.join(ores, 'gametext.lmp'))
        log('characters')
        cape = os.path.join(tmp, 'cape8.vif')
        open(cape, 'wb').write(lmp_member(find(xres, 'zatanna.lmp'), 'cape8.vif'))
        run('build_character.py', find(usr, 'SUPERGRL.LMP'), os.path.join(ores, 'supergrl.lmp'), cape)
        run('build_character.py', find(usr, 'BCANARY.LMP'), os.path.join(ores, 'bcanary.lmp'))
        log('levels')
        import level_psp2xbox as C
        import rename_level
        import build_psp_story as S
        if sd:
            C.SCALES = (S.TEX_SCALE,)
        else:
            C.SCALES = (2.0, 1.5, 1.25, 1.0)
            C.LEVEL_BUDGET = 100.0
        xenv = os.path.join(tmp, 'xenv')
        os.makedirs(xenv)
        e1l6 = open(find(xres, 'e1l6.gob'), 'rb').read()
        for m in ('env.lmp', 'waterenv.lmp'):
            open(os.path.join(xenv, m), 'wb').write(gob_member(e1l6, m))
        pl = os.path.join(tmp, 'psp')
        os.makedirs(pl)
        for psp, new, stream in LEVELS:
            for e in ('.gob', '.tex', '.vat'):
                shutil.copy(find(usr, psp.upper() + e.upper()), os.path.join(pl, psp + e))
        work = os.path.join(tmp, 'work')
        os.makedirs(work)
        for psp, new, stream in LEVELS:
            log(f'  {new}')
            C.convert_level(pl, psp, music_stream(xres, stream), stream, xenv, work,
                            log=lambda m: None)
            gob = open(os.path.join(work, psp + '.gob'), 'rb').read()
            if psp != new:
                gob = rename_level.rename(gob, psp, new, work)
            open(os.path.join(ores, new + '.gob'), 'wb').write(gob)
            os.remove(os.path.join(work, psp + '.gob'))
            for e in ('.tex', '.vat'):
                shutil.move(os.path.join(work, psp + e), os.path.join(ores, new + e))
        S.XBOX = xres
        for xlvl in S.LINKS:
            open(os.path.join(ores, xlvl + '.gob'), 'wb').write(S.patch_links(xlvl))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log('mod files built')


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    build(a[0], a[1], a[2], sd='--sd' in sys.argv)


if __name__ == '__main__':
    main()
