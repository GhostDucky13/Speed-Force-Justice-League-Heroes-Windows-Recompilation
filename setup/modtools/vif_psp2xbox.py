#!/usr/bin/env python3
"""
vif_psp2xbox.py - Convert a PSP .vif model (Justice League Heroes) to the Xbox .vif format.

Usage:
  python vif_psp2xbox.py in_psp.vif texture.tex out_xbox.vif
      texture.tex = the texture this model uses (PSP or Xbox .tex); its size is
      needed because PSP UVs are relative to the actual size and Xbox UVs to the
      power-of-two size.

Xbox layout written (see FINDINGS.md):
  0x00-0x4F  PSP header (tag changed to XBOX, 0x10 = 0xF0); 0x4A = part count
  0x50       u32 vertex_block_off, u32 index_off, u32 vertex_count
  0x5C/0x9C  bone palettes A/B (64 bytes each, slot -> skeleton bone, 0xFF unused, max 44 slots)
  0xDC       PSP u16 block table (PSP 0x5A..0x65), offsets shifted by the block move / 16
  0xF0       index boundaries: [A start, A end of part 0..n-1] [B start, B end of part 0..n-1]
  then       per-part 16-byte records (PSP copy; last s16 = triangle count)
  then       PSP data blocks, 16-aligned, moved by the same shift
  index_off  (128-aligned) u16 triangle-strip indices
  vertex_block_off: u32 size, then 32-byte vertices:
     s16 pos[3], s16 normal[3], s16 uv[2], f32 regA, wA, regB, wB
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vif_psp  # noqa: E402

MAX_SLOTS = 44


def p2(n):
    return 1 << (n - 1).bit_length()


def tex_size(path):
    d = open(path, 'rb').read()
    return struct.unpack_from('<HH', d, 0)


def align(o, a):
    return (o + a - 1) // a * a


def strip_bones(strip):
    return {b for v in strip for b, w in zip(v['bones'], v['weights']) if w > 0}


def build_palettes(sections):
    """Palette A = most used bones (<=44); strips not fully covered go to palette B."""
    from collections import Counter
    use = Counter()
    for strips in sections:
        for s in strips:
            for v in s:
                for b, w in zip(v['bones'], v['weights']):
                    if w > 0:
                        use[b] += 1
    bones = [b for b, _ in use.most_common()]
    if len(bones) <= MAX_SLOTS:
        A = sorted(bones)
    else:
        # keep strips together: grow A strip by strip in order of bone popularity
        A = set()
        for b in bones:
            if len(A) < MAX_SLOTS:
                A.add(b)
        A = sorted(A)
    Aset = set(A)
    Bset = set()
    for strips in sections:
        for s in strips:
            sb = strip_bones(s)
            if not sb <= Aset:
                Bset |= sb
    B = sorted(Bset)
    if len(B) > MAX_SLOTS:
        raise ValueError(f"palette B needs {len(B)} bones (> {MAX_SLOTS})")
    return A, B


def join_strips(strips_idx):
    """Concatenate index strips with degenerate joins, every strip starting on an even index."""
    seq = []
    for s in strips_idx:
        if not s:
            continue
        if seq:
            seq.append(seq[-1])
            seq.append(s[0])
            if len(seq) % 2 == 1:
                seq.append(s[0])
        seq.extend(s)
    return seq


def tri_count(seq):
    return sum(1 for k in range(len(seq) - 2) if len({seq[k], seq[k + 1], seq[k + 2]}) == 3)


SPHERE_SIZE_SCALE = 0.6   # Xbox effect-sphere sizes are ~0.55-0.75x the PSP values


def convert_spheres(blk):
    """PSP: u32 n, n x (s16 x,y,z,size,bone). Xbox: u32 n1, u32 n2, u32 0, then records."""
    n = struct.unpack_from('<I', blk, 0)[0]
    recs = bytearray()
    for i in range(n):
        x, y, z, size, bone = struct.unpack_from('<5h', blk, 4 + 10 * i)
        if size > 0:
            size = max(4, int(round(size * SPHERE_SIZE_SCALE / 4)) * 4)
        recs += struct.pack('<5h', x, y, z, size, bone)
    return struct.pack('<3I', n, 0, 0) + recs


def relayout_blocks(psp, sec0, blk_x):
    """Copy the PSP data blocks referenced by the u16 table at 0x5A into Xbox order/offsets.
    Drops the PSP-only block at header 0x30 and converts the effect-sphere block (entry 3).
    Returns (bytes starting at blk_x, new u16 table[6])."""
    u16 = list(struct.unpack_from('<6H', psp, 0x5A))
    psp_only = struct.unpack_from('<H', psp, 0x30)[0] * 16
    starts = sorted({u * 16 for u in u16[:5] if u} | ({psp_only} if psp_only else set()))
    ends = starts[1:] + [sec0]
    content = {}
    for s, e in zip(starts, ends):
        blk = psp[s:e]
        if s == psp_only:
            continue
        if u16[3] and s == u16[3] * 16:
            n = struct.unpack_from('<I', blk, 0)[0]
            blk = convert_spheres(blk[:4 + 10 * n])
        content[s] = blk.rstrip(b'\0') if s == max(k for k in starts if k != psp_only) else blk
    out = bytearray()
    newpos = {}
    for s in sorted(content):
        pad = (-len(out)) % 16
        out += b'\0' * pad
        newpos[s] = blk_x + len(out)
        out += content[s]
    new16 = [newpos[u * 16] // 16 if u else 0 for u in u16[:5]] + [u16[5]]
    return bytes(out), new16


def convert(psp, tex_w, tex_h):
    if psp[8:11] != b'PSP':
        raise ValueError('input is not a PSP .vif')
    sections = vif_psp.decode(psp)
    ns = len(sections)
    if psp[0x4A] != ns:
        raise ValueError(f'part count mismatch: header {psp[0x4A]} vs {ns} sections')
    skinned = any(v.get('skinned') for strips in sections for s in strips for v in s)

    if skinned:
        A, B = build_palettes(sections)
    else:
        A, B = [], []
    slotA = {b: i for i, b in enumerate(A)}
    slotB = {b: i for i, b in enumerate(B)}
    uscale, vscale = tex_w / p2(tex_w), tex_h / p2(tex_h)

    verts, vindex = [], {}

    def vid(v, pal):
        nx, ny, nz = v['nrm']
        ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
        nrm = tuple(max(-32767, min(32767, round(c / ln * 32767))) for c in (nx, ny, nz))
        uv = (min(32767, round(v['uv'][0] * uscale)), min(32767, round(v['uv'][1] * vscale)))
        if skinned:
            slots = pal
            bw = [(slots[b], w) for b, w in zip(v['bones'], v['weights']) if w > 0]
            bw.sort(key=lambda t: -t[1])
            bw = (bw + [(0, 0.0)])[:2]
            tot = sum(w for _, w in bw) or 1.0
            rec = (float(bw[0][0] * 4), bw[0][1] / tot, float(bw[1][0] * 4), bw[1][1] / tot)
        else:
            rec = (0.0, 1.0, 0.0, 0.0)
        key = (v['pos'], nrm, uv, rec)
        if key not in vindex:
            vindex[key] = len(verts)
            verts.append(key)
        return vindex[key]

    # pass A then pass B, one index range per part each
    ranges_A, ranges_B = [], []
    for strips in sections:
        a_strips, b_strips = [], []
        for s in strips:
            if not skinned or strip_bones(s) <= set(A):
                a_strips.append([vid(v, slotA) for v in s])
            else:
                b_strips.append([vid(v, slotB) for v in s])
        ranges_A.append(join_strips(a_strips))
        ranges_B.append(join_strips(b_strips))

    indices, table = [], [0]
    for r in ranges_A:
        indices += r
        table.append(len(indices))
    table.append(len(indices))
    for r in ranges_B:
        indices += r
        table.append(len(indices))
    assert len(table) == 2 * ns + 2
    if len(verts) > 0xFFFF:
        raise ValueError('too many vertices for 16-bit indices')

    # ---- header -------------------------------------------------------
    r_p = 0x68 + 4 * (ns + 1)              # PSP per-part records
    r_x = 0xF0 + 4 * (2 * ns + 2)          # Xbox per-part records
    blk_x = align(r_x + 16 * ns, 16)
    sec0 = vif_psp.sections(psp)[0]
    blocks_x, u16 = relayout_blocks(psp, sec0, blk_x)
    ioff = align(blk_x + len(blocks_x), 0x80)

    out = bytearray(ioff)
    out[0:0x50] = psp[0:0x50]
    out[8:12] = b'XBOX'
    struct.pack_into('<I', out, 0x10, 0xF0)
    out[0x30:0x34] = b'\0' * 4      # PSP-only block offset; Xbox code skips it when 0
    pal = bytearray(b'\xFF' * 128)
    for i, b in enumerate(A):
        pal[i] = b
    for i, b in enumerate(B):
        pal[64 + i] = b
    out[0x5C:0xDC] = pal
    struct.pack_into('<6H', out, 0xDC, *u16)
    out[0xE8:0xEA] = psp[0x66:0x68]
    struct.pack_into('<%dI' % len(table), out, 0xF0, *table)
    for i in range(ns):
        rec = bytearray(psp[r_p + 16 * i:r_p + 16 * i + 16])
        count = tri_count(ranges_A[i]) + tri_count(ranges_B[i])
        struct.pack_into('<h', rec, 14, min(count, 32767))
        out[r_x + 16 * i:r_x + 16 * i + 16] = rec
    out[blk_x:blk_x + len(blocks_x)] = blocks_x

    # ---- geometry ------------------------------------------------------
    voff = ioff + 2 * len(indices)
    struct.pack_into('<III', out, 0x50, voff, ioff, len(verts))
    out += struct.pack('<%dH' % len(indices), *indices)
    vb = bytearray()
    for pos, nrm, uv, rec in verts:
        vb += struct.pack('<3h3h2h4f', *pos, *nrm, *uv, *rec)
    out += struct.pack('<I', len(vb)) + vb
    info = dict(parts=ns, verts=len(verts), indices=len(indices), paletteA=len(A), paletteB=len(B),
                skinned=skinned, triangles=sum(tri_count(r) for r in ranges_A + ranges_B))
    return bytes(out), info


def main():
    src, texp, dst = sys.argv[1:4]
    w, h = tex_size(texp)
    data, info = convert(open(src, 'rb').read(), w, h)
    open(dst, 'wb').write(data)
    print(f"{os.path.basename(src)} -> {dst}: {info}")


if __name__ == '__main__':
    main()
