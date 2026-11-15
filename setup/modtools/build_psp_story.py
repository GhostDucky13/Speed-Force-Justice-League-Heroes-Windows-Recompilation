#!/usr/bin/env python3
"""
build_psp_story.py - the three PSP-only story levels, converted and linked into the Xbox story.

  PSP pspe1  "S.T.A.R. Labs Sub Level"  -> e1l8   Xbox e1l6 -> e1l8 -> e1l7
  PSP pspe5  "Mars Lower Caves"         -> e5l5   Xbox e5l2 -> e5l5 -> (cs19) e5l3
  PSP pspe11 "Fortress Perimeter"       -> e11l2  Xbox e11l3 -> (cs37) e11l2 -> e11l4

Checked first (FINDINGS stage 20): all three are new geometry (bounding-box match with their
Xbox neighbours 1-12 %, same level PSP/Xbox = 87 %), every object class / script native exists
on Xbox, each PSP level streams only its music, whose Xbox recording is the first stream of a
neighbouring Xbox level's .vat.

Textures at 0.5x (the scale that fixed the Vent System crash).

Script links (level.amx strings are one char per 4-byte cell; patched in place, same length):
  e1l6 : "e1l7" -> "e1l8"
  e11l3: "e11l4" -> "e11l2"   (cutscene cs37 still plays before the new level, as on the PSP)
  e5l2 : movieStartAndTransition("cs19", "e5l3") -> simpleNewWorld("e5l5"): the native's name
         is renamed in the AMX native table and its first argument becomes "e5l5". The PSP level
         plays cs19 itself before e5l3, so the cutscene is shown once, after the new level.
New levels keep their own links (pspe1 -> e1l7, pspe5 -> cs19 + e5l3, pspe11 -> e11l4).

  python build_psp_story.py   (paths are the project's input/ and out/ folders)
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level as L  # noqa: E402
import level_psp2xbox as C  # noqa: E402
import lmp  # noqa: E402
import rename_level  # noqa: E402

ROOT = os.path.dirname(HERE)
PSP = os.path.join(ROOT, 'input', 'levels', 'p')
XBOX = os.path.join(ROOT, 'input', 'levels', 'x')
OUT = os.path.join(ROOT, 'out', 'levels')
WORK = os.path.join(ROOT, 'work', 'conv_story')

LEVELS = [   # psp name, new name, xbox level holding the music, music stream
    ('pspe1', 'e1l8', 'e1l6', 'env_e01_star.vag'),
    ('pspe5', 'e5l5', 'e5l2', 'env_e05_mars_a.vag'),
    ('pspe11', 'e11l2', 'e11l4', 'env_e11_frtrs_a.vag'),
]
LINKS = {    # xbox level: [(old string, new string)]  + native renames
    'e1l6': [('e1l7', 'e1l8')],
    'e11l3': [('e11l4', 'e11l2')],
    'e5l2': [('cs19', 'e5l5')],
}
NATIVE_RENAMES = {'e5l2': [('movieStartAndTransition', 'simpleNewWorld')]}
TEX_SCALE = 0.5


def cells(s):
    return b''.join(struct.pack('<I', ord(ch)) for ch in s) + b'\0\0\0\0'


def level_lmp(gob, name):
    for n, b in L.read_gob(gob):
        if n.lower() == name + '.lmp':
            return b
    raise KeyError(name)


def amx_of(gob, name):
    for n, b, _ in lmp.read_bytes(level_lmp(gob, name)):
        if n.lower() == 'level.amx':
            return b
    raise KeyError('level.amx')


def music(xlvl, stream):
    gob = open(os.path.join(XBOX, xlvl + '.gob'), 'rb').read()
    for n, b, _ in lmp.read_bytes(level_lmp(gob, xlvl)):
        if n.lower() == 'ntsc_dialog.bin':
            for r in L.read_dialog(b):
                if r['name'] == stream:
                    vat = open(os.path.join(XBOX, xlvl + '.vat'), 'rb').read()
                    return vat[r['offset']:r['offset'] + r['size']]
    raise KeyError(stream)


def patch_links(xlvl):
    """Patch level.amx of an Xbox level in place inside its .gob (sizes unchanged)."""
    gob = bytearray(open(os.path.join(XBOX, xlvl + '.gob'), 'rb').read())
    amx = amx_of(bytes(gob), xlvl)
    base = gob.find(amx)
    assert base > 0 and gob.find(amx, base + 1) < 0, 'level.amx not found exactly once'
    new = bytearray(amx)
    for old, rep in LINKS.get(xlvl, []):
        assert len(old) == len(rep)
        o, r = cells(old), cells(rep)
        assert new.count(o) == 1, (xlvl, old, new.count(o))
        i = new.find(o)
        new[i:i + len(r)] = r
    for old, rep in NATIVE_RENAMES.get(xlvl, []):
        o = old.encode() + b'\0'
        assert new.count(o) == 1 and len(rep) <= len(old)
        i = new.find(o)
        new[i:i + len(o)] = rep.encode() + b'\0' * (len(o) - len(rep))
    gob[base:base + len(amx)] = new
    return bytes(gob)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    C.SCALES = (TEX_SCALE,)
    logf = open(os.path.join(WORK, 'convert.log'), 'w')

    def log(m):
        print(m)
        logf.write(m + '\n')
    for psp, new, xmus, stream in LEVELS:
        mus = music(xmus, stream)
        C.convert_level(PSP, psp, mus, stream, os.path.join(ROOT, 'work', 'lv', 'x_e1l6'), WORK, log=log)
        gob = open(os.path.join(WORK, psp + '.gob'), 'rb').read()
        open(os.path.join(OUT, new + '.gob'), 'wb').write(rename_level.rename(gob, psp, new, WORK))
        for ext in ('.tex', '.vat'):
            os.replace(os.path.join(WORK, psp + ext), os.path.join(OUT, new + ext))
        os.remove(os.path.join(WORK, psp + '.gob'))
        log(f'{psp} -> {new}')
    for xlvl in LINKS:
        open(os.path.join(OUT, xlvl + '.gob'), 'wb').write(patch_links(xlvl))
        log(f'{xlvl}.gob: links patched')


if __name__ == '__main__':
    main()
