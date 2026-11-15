#!/usr/bin/env python3
"""world.py - parse Justice League Heroes .world files (PSP and Xbox). Work in progress."""
import struct

REC = 60


def header(d):
    return struct.unpack_from('<64i', d, 0)


def objects(d):
    h = header(d)
    out = []
    for i in range(h[0]):
        o = h[9] + i * REC
        r = dict(idx=i, ptr=struct.unpack_from('<I', d, o)[0], n=struct.unpack_from('<I', d, o + 4)[0],
                 bmax=struct.unpack_from('<3f', d, o + 8), bmin=struct.unpack_from('<3f', d, o + 20),
                 f20=struct.unpack_from('<I', d, o + 32)[0], flags=struct.unpack_from('<I', d, o + 36)[0],
                 cell=struct.unpack_from('<4h', d, o + 40), f30=struct.unpack_from('<I', d, o + 48)[0],
                 tex=struct.unpack_from('<H', d, o + 52)[0], f36=struct.unpack_from('<H', d, o + 54)[0],
                 f38=struct.unpack_from('<I', d, o + 56)[0], raw=d[o:o + REC])
        out.append(r)
    return out


def xbox_mesh(d, ptr):
    vp, nv, ip, ni = struct.unpack_from('<4I', d, ptr)
    verts = [struct.unpack_from('<8h', d, vp + 16 * i) for i in range(nv)]
    idx = list(struct.unpack_from(f'<{ni}H', d, ip))
    return verts, idx


def psp_mesh(d, ptr):
    """Returns (verts, strips). verts: (u, v, nx, ny, nz, x, y, z); strips: list of index lists."""
    voff, goff = struct.unpack_from('<II', d, ptr)
    vtype, verts, strips, pos = None, [], [], ptr + voff
    o = ptr + goff
    while True:
        w = struct.unpack_from('<I', d, o)[0]; o += 4
        cmd, arg = w >> 24, w & 0xFFFFFF
        if cmd == 0x12:
            vtype = arg
        elif cmd == 0x04:
            prim, cnt = (arg >> 16) & 7, arg & 0xFFFF
            base = len(verts)
            for i in range(cnt):
                u, v, nx, ny, nz, _, x, y, z = struct.unpack_from('<HHbbbbhhh', d, pos)
                verts.append((u, v, nx, ny, nz, x, y, z)); pos += 14
            strips.append((prim, list(range(base, base + cnt))))
        elif cmd == 0x0B or cmd == 0x0C:
            break
        elif cmd == 0x10:      # BASE
            pass
        elif cmd == 0x01:      # VADDR
            pos = ptr + voff + arg  # guess
        elif o - ptr > 0x100000:
            break
    return verts, strips, vtype
