#!/usr/bin/env python3
"""
vif_xbox.py - Decode Xbox .vif models (Justice League Heroes).

Layout (verified on Zatanna, Wonder Woman, top hat; see FINDINGS.md):
  0x00 "1.30", 0x08 "XBOX", 0x10 u32 0xF0, 0x4A u8 part count (n)
  0x50 u32 vertex_block_off, u32 index_off, u32 vertex_count
  0x5C / 0x9C  bone palettes A / B (slot -> skeleton bone, 0xFF unused)
  0xF0 (2n+2) u32 index boundaries: A pass [0, end part0 .. end part n-1],
       B pass [start, end part0 .. end part n-1]; bit 30 = alpha-blended range
  index_off: u16 triangle-strip indices
  vertex_block_off: u32 size, then 32-byte vertices
      s16 pos[3], s16 normal[3], s16 uv[2] (relative to pow2 texture size),
      f32 regA, wA, regB, wB   (bone = palette[reg / 4])

decode() returns [part][strip][vertex] like vif_psp.decode().
"""
import struct
import sys


def header(d):
    return struct.unpack_from('<III', d, 0x50)


def parts_table(d):
    n = d[0x4A]
    tab = [t & 0x3FFFFFFF for t in struct.unpack_from('<%dI' % (2 * n + 2), d, 0xF0)]
    A = [(tab[i], tab[i + 1]) for i in range(n)]
    B = [(tab[n + 1 + i], tab[n + 2 + i]) for i in range(n)]
    return n, A, B


def decode(d):
    if d[8:12] != b'XBOX':
        raise ValueError('not an Xbox .vif')
    voff, ioff, nv = header(d)
    idx = struct.unpack_from('<%dH' % ((voff - ioff) // 2), d, ioff)
    base = voff + 4
    pal = [list(d[0x5C:0x9C]), list(d[0x9C:0xDC])]
    rigid = all(b == 0xFF for b in pal[0])
    V = []
    for i in range(nv):
        o = base + 32 * i
        pos = struct.unpack_from('<3h', d, o)
        nrm = struct.unpack_from('<3h', d, o + 6)
        u, v = struct.unpack_from('<2h', d, o + 12)
        ra, wa, rb, wb = struct.unpack_from('<4f', d, o + 16)
        V.append((pos, nrm, (u & 0xFFFF, v & 0xFFFF), (int(ra) // 4, int(rb) // 4), (wa, wb)))
    n, A, B = parts_table(d)
    out = []
    for p in range(n):
        strips = []
        for which, (a, b) in ((0, A[p]), (1, B[p])):
            if b <= a:
                continue
            s = []
            for i in idx[a:b]:
                pos, nrm, uv, regs, w = V[i]
                bones = [0, 0] if rigid else [pal[which][regs[0]], pal[which][regs[1]]]
                s.append(dict(pos=pos, nrm=nrm, uv=uv, bones=bones, weights=list(w), palette=which))
            strips.append(s)
        out.append(strips)
    return out


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    voff, ioff, nv = header(d)
    n, A, B = parts_table(d)
    print(f"{nv} vertices, {(voff - ioff) // 2} indices, {n} parts")
    for p in range(n):
        print(f"  part {p}: A {A[p]}  B {B[p]}")
