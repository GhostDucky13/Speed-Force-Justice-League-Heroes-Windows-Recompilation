#!/usr/bin/env python3
"""rename_level.py - repack a level gob under another level name (test helper).
   python rename_level.py in.gob old new out.gob"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import level as L, lmp, level_psp2xbox as C  # noqa: E402


def rename(gob, old, new, tmpdir):
    out = []
    for n, b in L.read_gob(gob):
        if n.lower() == old + '.lmp':
            ents = [((new + '.world') if e.lower() == old + '.world' else e, d) for e, d, _ in lmp.read_bytes(b)]
            tmp = os.path.join(tmpdir, '_rn.lmp'); lmp.build(ents, tmp); b = open(tmp, 'rb').read(); os.remove(tmp)
            n = new + '.lmp'
        out.append((n, b))
    return C.build_gob(out)


if __name__ == '__main__':
    src, old, new, dst = sys.argv[1:5]
    open(dst, 'wb').write(rename(open(src, 'rb').read(), old, new, os.path.dirname(os.path.abspath(dst))))
