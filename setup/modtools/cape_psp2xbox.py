#!/usr/bin/env python3
"""
cape_psp2xbox.py - Build an Xbox cape8.vif for a PSP-only character.

Capes are cloth-simulated 8x8 grids. The Xbox file stores the 64 grid vertices
row by row, then a second copy (128 vertices), with a fixed strip index list and a
one-bone palette. All PSP and Xbox cape8 files share the same grid positions, so
this tool takes an existing Xbox cape8.vif as the structural template and replaces
only the texture coordinates with the PSP character's own (converted to Xbox UV space).

Usage:
  python cape_psp2xbox.py psp_cape8.vif psp_cape8.tex template_xbox_cape8.vif out.vif
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vif_psp  # noqa: E402
import vif_xbox  # noqa: E402


def p2(n):
    return 1 << (n - 1).bit_length()


def convert(psp, tex_w, tex_h, template):
    strips = vif_psp.decode(psp)[0]
    uv_by_pos = {}
    for s in strips:
        for v in s:
            uv_by_pos.setdefault(v['pos'], v['uv'])
    out = bytearray(template)
    voff, ioff, nv = vif_xbox.header(template)
    base = voff + 4
    us, vs = tex_w / p2(tex_w), tex_h / p2(tex_h)
    missing = 0
    for i in range(nv):
        o = base + 32 * i
        pos = struct.unpack_from('<3h', out, o)
        uv = uv_by_pos.get(pos)
        if uv is None:
            missing += 1
            continue
        struct.pack_into('<2h', out, o + 12, min(32767, round(uv[0] * us)), min(32767, round(uv[1] * vs)))
    if missing:
        raise ValueError(f'{missing} template vertices have no matching PSP cape vertex')
    return bytes(out)


def main():
    psp_vif, psp_tex, tmpl, dst = sys.argv[1:5]
    w, h = struct.unpack_from('<HH', open(psp_tex, 'rb').read(), 0)
    open(dst, 'wb').write(convert(open(psp_vif, 'rb').read(), w, h, open(tmpl, 'rb').read()))
    print(f'cape -> {dst}')


if __name__ == '__main__':
    main()
