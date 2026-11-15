#!/usr/bin/env python3
"""
vif_psp.py - Decode PSP .vif models (Justice League Heroes) into a neutral mesh.

File layout:
  0x00 "1.30", 0x08 "PSP"
  0x68 u32 section offsets (one per LOD), terminated by the file size
       (rigid models: one section at 0x100)
  each section: u32 vtx_off, u32 cmdlist_off, u32 cmdlist_size (relative to section)
  cmdlist = raw PSP GE commands:
     VTYPE (0x12)  vertex format
     BONENUM (0x2A) + CALL (0x0A) -> matrix slot (arg/12) <- bone ((target & 0xFFFF) / 0x38)
     PRIM (0x04)   triangle strip (type 4) of N vertices; vertex pointer advances
     RET  (0x0B)

Output per strip: list of vertices
  dict(pos=(x,y,z) s16, nrm=(x,y,z) s8, uv=(u,v) u16 (/32768, relative to the actual texture size),
       bones=[bone ids], weights=[0..1])
"""
import struct
import sys


def _align(o, a):
    return (o + a - 1) // a * a


def vtype_layout(vt):
    tex = vt & 3            # 0 none, 1 u8, 2 u16, 3 float
    col = (vt >> 2) & 7
    nrm = (vt >> 5) & 3     # 0 none, 1 s8, 2 s16, 3 float
    pos = (vt >> 7) & 3
    wgt = (vt >> 9) & 3     # 0 none, 1 u8, 2 u16, 3 float
    nw = ((vt >> 14) & 7) + 1 if wgt else 0
    if col or (vt >> 11) & 7 or (vt >> 18) & 7:
        raise NotImplementedError(f"VTYPE {vt:06X}: colour/index/morph not handled")
    size_of = {0: 0, 1: 1, 2: 2, 3: 4}
    o, lay, maxa = 0, {}, 1
    if wgt:
        s = size_of[wgt]; o = _align(o, s); lay['w'] = (o, wgt, nw); o += s * nw; maxa = max(maxa, s)
    if tex:
        s = size_of[tex]; o = _align(o, s); lay['t'] = (o, tex); o += s * 2; maxa = max(maxa, s)
    if nrm:
        s = size_of[nrm]; o = _align(o, s); lay['n'] = (o, nrm); o += s * 3; maxa = max(maxa, s)
    if pos:
        s = size_of[pos]; o = _align(o, s); lay['p'] = (o, pos); o += s * 3; maxa = max(maxa, s)
    return lay, _align(o, maxa)


FMT = {1: 'b', 2: 'h', 3: 'f'}
UFMT = {1: 'B', 2: 'H', 3: 'f'}


def read_vertex(d, o, lay):
    v = {}
    if 'w' in lay:
        off, k, n = lay['w']
        raw = struct.unpack_from('<%d%s' % (n, UFMT[k]), d, o + off)
        scale = {1: 128.0, 2: 32768.0, 3: 1.0}[k]
        v['wraw'] = [r / scale for r in raw]
    if 't' in lay:
        off, k = lay['t']; v['uv'] = struct.unpack_from('<2' + UFMT[k], d, o + off)
    if 'n' in lay:
        off, k = lay['n']; v['nrm'] = struct.unpack_from('<3' + FMT[k], d, o + off)
    if 'p' in lay:
        off, k = lay['p']; v['pos'] = struct.unpack_from('<3' + FMT[k], d, o + off)
    return v


def sections(d):
    offs = []
    o = 0x68
    size = len(d)
    while o + 4 <= 0x100:
        v = struct.unpack_from('<I', d, o)[0]
        if v == size or v == 0 or v > size:
            break
        offs.append(v)
        o += 4
    return offs or [0x100]


def decode_section(d, sec):
    vo, dlo, dls = struct.unpack_from('<3I', d, sec)
    vptr = sec + vo
    dl = sec + dlo
    vt, lay, stride = None, None, 0
    slots = {}          # matrix slot -> bone id
    pending_slot = None
    strips = []
    for i in range(dls // 4):
        w = struct.unpack_from('<I', d, dl + 4 * i)[0]
        cmd, arg = w >> 24, w & 0xFFFFFF
        if cmd == 0x12:
            vt = arg; lay, stride = vtype_layout(vt)
        elif cmd == 0x2A:
            pending_slot = arg // 12
        elif cmd == 0x0A:
            if pending_slot is not None:
                slots[pending_slot] = (arg & 0xFFFF) // 0x38
                pending_slot = None
        elif cmd == 0x04:
            ptype, n = (arg >> 16) & 7, arg & 0xFFFF
            if ptype != 4:
                raise NotImplementedError(f"prim type {ptype}")
            verts = []
            for k in range(n):
                v = read_vertex(d, vptr + k * stride, lay)
                if 'wraw' in v:
                    v['bones'] = [slots.get(s, -1) for s in range(len(v['wraw']))]
                    v['weights'] = v.pop('wraw')
                    v['skinned'] = True
                else:
                    v['bones'], v['weights'] = [slots.get(0, 0)], [1.0]
                    v['skinned'] = False
                verts.append(v)
            vptr += n * stride
            strips.append(verts)
        elif cmd == 0x0B:
            break
    return strips


def decode(d):
    if d[8:11] != b'PSP':
        raise ValueError('not a PSP .vif')
    return [decode_section(d, s) for s in sections(d)]


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    for li, strips in enumerate(decode(d)):
        nv = sum(len(s) for s in strips)
        bones = sorted({b for s in strips for v in s for b in v['bones']})
        print(f"LOD{li}: {len(strips)} strips, {nv} strip vertices, {len(bones)} bones used: {bones}")
