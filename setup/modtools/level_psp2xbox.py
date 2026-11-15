#!/usr/bin/env python3
"""
level_psp2xbox.py - Convert a PSP Justice League Heroes level to the Xbox format.

  python level_psp2xbox.py <psp dir with LEVEL.GOB/.TEX> <level> <xbox music .xadpcm> <music name> <xbox env dir> <out dir>

Produces <out>/<level>.gob, <level>.tex, <level>.vat for the Xbox res folder.

What it does (see FINDINGS.md stages 9-12):
  .world : PSP world kept (same format on both platforms) except
           - meshes: PSP GE triangle strips -> Xbox indexed strips (16-byte vertices,
             UV rescaled from "relative to image size" to "relative to pow2 size"),
             appended at the end of the file, object records repointed;
           - embedded texture (header +0x6c): PSP 4/8-bit swizzled -> Xbox 8-bit linear, appended.
  .tex   : every image decoded, upscaled 2x (max 512) per channel (Lanczos), mapped back to
           its original 256-colour palette, re-encoded with the game's tile/Huffman codec.
  audio  : the level's music stream replaced by the original Xbox stream of the same track.
  env    : env.lmp / waterenv.lmp taken from an Xbox level (they are identical everywhere).
"""
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leveltex as T  # noqa: E402
import level as L  # noqa: E402
import lmp  # noqa: E402
import world as W  # noqa: E402

MAX_DIM = 512


def pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return max(p, 1)


# ------------------------------------------------------------------ textures
GROUP_LIMIT = 0x160000          # largest texture group in the real Xbox levels is 0x166a49
SCALES = (2.0, 1.5, 1.25, 1.0)


def upscale_image(w, h, pal, px, scale=2.0):
    s = min(scale, MAX_DIM / w, MAX_DIM / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    if (nw, nh) == (w, h):
        return w, h, px
    p = np.array(pal, dtype=np.float32)                      # 256 x 4
    idx = np.frombuffer(px, dtype=np.uint8).reshape(h, w)
    rgba = p[idx]                                            # h x w x 4
    chans = []
    for c in range(4):
        im = Image.fromarray(rgba[:, :, c].astype(np.uint8), 'L').resize((nw, nh), Image.LANCZOS)
        chans.append(np.asarray(im, dtype=np.float32))
    up = np.stack(chans, -1).reshape(-1, 4)
    used = np.unique(idx)                                    # map only to colours this image uses
    cand = p[used].astype(np.float64)
    # Speed Force: each distinct colour once, distances as |x|^2 - 2x.c + |c|^2 in float64.
    # All values are whole numbers, so every distance is exact and the nearest colour (first
    # one on a tie) is the same as the per-pixel search this replaces - only faster.
    q = up.astype(np.uint8).astype(np.uint32)
    key = (q[:, 0] << 24) | (q[:, 1] << 16) | (q[:, 2] << 8) | q[:, 3]
    uk, inv = np.unique(key, return_inverse=True)
    uq = np.stack([(uk >> 24) & 255, (uk >> 16) & 255, (uk >> 8) & 255, uk & 255], -1).astype(np.float64)
    best = np.empty(len(uq), dtype=np.uint8)
    cc = (cand * cand).sum(1)
    for i in range(0, len(uq), 65536):
        blk = uq[i:i + 65536]
        dist = (blk * blk).sum(1)[:, None] - 2.0 * blk @ cand.T + cc[None, :]
        best[i:i + 65536] = used[dist.argmin(1)]
    out = best[inv.reshape(-1)]
    return nw, nh, out.tobytes()


LEVEL_BUDGET = 2.5    # converted .tex may be at most this many times the PSP .tex (Xbox e1l7 / PSP e1l7 = 2.45)


def convert_tex(psp_tex, upscale=True, log=None, only=None, skip=(), budget=None):
    """Returns (xbox .tex bytes, {(gid, rec_off): (pw, ph, nw, nh)}).
    Each group starts at the highest scale that keeps it under GROUP_LIMIT; then, while the
    whole level is over budget x the PSP size, the largest group drops to the next scale."""
    d = psp_tex
    src = {}
    for gid, goff, _ in T.read_table(d):
        cache = {}
        src[gid] = [(im['rec'] - goff, T.decode(d, goff, im, cache)) for im in T.images(d, goff)]
    order = list(src)

    def encode(gid, scale):
        imgs, gd = [], {}
        for rec, (w, h, pal, px) in src[gid]:
            nw, nh, npx = upscale_image(w, h, pal, px, scale)
            gd[(gid, rec)] = (w, h, nw, nh)
            imgs.append((nw, nh, npx, pal))
        return T.encode_group(imgs), gd

    level = {}
    for gid in order:
        do_up = upscale and gid not in skip and (only is None or gid in only)
        scales = [x for x in SCALES if do_up or x == 1.0]
        for i, sc in enumerate(scales):
            g, gd = encode(gid, sc)
            if len(g) <= GROUP_LIMIT or sc == 1.0:
                break
        level[gid] = [scales[i:], g, gd]
    limit = (LEVEL_BUDGET if budget is None else budget) * len(d)
    while sum(len(v[1]) for v in level.values()) > limit:
        cand = [gid for gid in order if len(level[gid][0]) > 1]
        if not cand:
            break
        gid = max(cand, key=lambda k: len(level[k][1]))
        level[gid][0] = level[gid][0][1:]
        level[gid][1], level[gid][2] = encode(gid, level[gid][0][0])
    dims, groups = {}, []
    for gid in order:
        scales, g, gd = level[gid]
        dims.update(gd)
        groups.append((gid, g))
        if log:
            log(f'  tex group {gid:#06x}: {len(src[gid])} images, scale {scales[0]}, {len(g):#x} bytes')
    out = T.build_tex(groups)
    if log:
        log(f'  tex total {len(out):#x} bytes ({len(out) / len(d):.2f}x PSP)')
    return out, dims


# ------------------------------------------------------------------ embedded .tex (header +0x6c)
def psp_tex_to_xbox(b):
    w, h, fmt, fl = struct.unpack_from('<HHBB', b, 0)
    hdr = b[8]
    bpp = 8 if fmt & 0x40 else 4
    npal = 256 if bpp == 8 else 16
    body = b[hdr:]
    pal = body[:4 * npal]
    pix = body[4 * npal:]
    stride = ((w * bpp // 8) + 15) // 16 * 16
    ph = (h + 7) // 8 * 8
    lin = bytearray(stride * ph)
    t = 0
    for ty in range(ph // 8):
        for tx in range(stride // 16):
            for r in range(8):
                dst = (ty * 8 + r) * stride + tx * 16
                lin[dst:dst + 16] = pix[t * 128 + r * 16:t * 128 + r * 16 + 16]
            t += 1
    out_px = bytearray()
    for y in range(h):
        line = lin[y * stride:(y + 1) * stride]
        if bpp == 8:
            out_px += line[:w]
        else:
            out_px += bytes((line[x >> 1] >> (4 * (x & 1))) & 0xF for x in range(w))
    xh = bytearray(0x40)
    struct.pack_into('<HHBB', xh, 0, w, h, (fmt & 0xF0) | 0x04, 0x40 | (fl & 0x80))
    xh[8] = 0x40
    size = hdr + 4 * npal + stride * ph
    return bytes(xh) + pal + b'\0' * (1024 - len(pal)) + bytes(out_px), size


# ------------------------------------------------------------------ world
def convert_world(P, dims, log=None):
    d = bytearray(P)
    h = W.header(P)
    objs = W.objects(P)
    tail = bytearray()
    base = (len(d) + 15) & ~15
    d += b'\0' * (base - len(d))

    def put(b, align=16):
        nonlocal tail
        while (base + len(tail)) % align:
            tail += b'\0'
        off = base + len(tail)
        tail += b
        return off

    # embedded texture
    if h[27]:
        xt, _ = psp_tex_to_xbox(P[h[27]:])
        struct.pack_into('<I', d, 27 * 4, put(xt))

    # Build all meshes first. Layout matters: after creating the D3D buffers the loader
    # (0x79231) deletes Σ(2·nindices + vbsize) bytes starting at the lowest index/vertex
    # address and shifts the rest down, so descriptors must lie BELOW the geometry, and the
    # geometry must be one packed block at the end: per mesh  u16 indices | u32 vbsize | vertices.
    cache, meshes = {}, []
    skipped = 0
    for r in objs:
        if r['flags'] & 0xC880:
            skipped += 1
            continue
        pw, ph_, nw, nh = dims.get((r['tex'], r['f20']), (1, 1, 1, 1))
        key = (r['ptr'], pw, ph_, nw, nh)
        if key not in cache:
            verts, strips, vtype = W.psp_mesh(P, r['ptr'])
            if vtype != 0x122:
                raise ValueError(f'object {r["idx"]}: unexpected vertex type {vtype:#x}')
            su, sv = nw / pow2(nw), nh / pow2(nh)
            vmap, vb, ib = {}, bytearray(), []
            for prim, idxs in strips:
                if prim != 4:
                    raise ValueError(f'object {r["idx"]}: primitive {prim}')
                seq = []
                for i in idxs:
                    u, v, nx, ny, nz, x, y, z = verts[i]
                    xv = (x, y, z, max(-32767, min(32767, nx * 258)), max(-32767, min(32767, ny * 258)),
                          max(-32767, min(32767, nz * 258)),
                          min(32767, round(u * su)), min(32767, round(v * sv)))
                    if xv not in vmap:
                        vmap[xv] = len(vmap)
                        vb += struct.pack('<6h2h', *xv)
                    seq.append(vmap[xv])
                if ib:                      # join strips with degenerates, keep winding
                    ib += [ib[-1], seq[0]]
                    if len(ib) % 2:
                        ib.append(seq[0])
                ib += seq
            cache[key] = len(meshes)
            meshes.append((bytes(vb), len(vmap), ib))
        r['_mesh'] = cache[key]
    desc_base = put(b'\0' * (0x80 * len(meshes)), 16)
    geo = base + len(tail)                  # packed, no alignment padding (like the Xbox files)
    for k, (vb, nv, ib) in enumerate(meshes):
        ip = base + len(tail)
        tail += struct.pack(f'<{len(ib)}H', *ib)
        vp = base + len(tail)
        tail += struct.pack('<I', len(vb)) + vb
        struct.pack_into('<4I', tail, desc_base - base + 0x80 * k, vp, nv, ip, len(ib))
    for r in objs:
        if '_mesh' in r:
            struct.pack_into('<II', d, h[9] + r['idx'] * W.REC, desc_base + 0x80 * r['_mesh'], 1)
    if log:
        log(f'  world: {len(objs)} objects, {len(meshes)} meshes, {skipped} special objects left as-is')
    return bytes(d + tail), skipped


# ------------------------------------------------------------------ packaging
def build_gob(entries):
    hdr = 0x800
    body, table, pos = bytearray(), bytearray(), hdr
    for name, data in entries:
        table += name.encode('latin-1').ljust(32, b'\0') + struct.pack('<II', pos, len(data))
        body += data + b'\0' * ((-len(data)) % 0x800)
        pos = hdr + len(body)
    table += b'\0' * (hdr - len(table))
    return bytes(table + body)


def convert_level(psp_dir, lvl, music_bytes, music_name, xenv_dir, out_dir, upscale=True, log=print, only=None, skip=()):
    def find(name):
        for f in os.listdir(psp_dir):
            if f.lower() == name.lower():
                return os.path.join(psp_dir, f)
        raise FileNotFoundError(name)
    os.makedirs(out_dir, exist_ok=True)
    gob = L.read_gob(open(find(lvl + '.gob'), 'rb').read())
    inner = dict(gob)[lvl + '.lmp'] if lvl + '.lmp' in dict(gob) else next(b for n, b in gob if n.lower() == lvl + '.lmp')
    entries = [(n, b) for n, b, _ in lmp.read_bytes(inner)]

    log(f'{lvl}: textures')
    xtex, dims = convert_tex(open(find(lvl + '.tex'), 'rb').read(), upscale, log, only, skip)

    dialog = L.build_dialog([dict(name=music_name, size=len(music_bytes), offset=0, a=0, flags=0x90000)])
    new_entries = []
    for n, b in entries:
        ln = n.lower()
        if ln.endswith('.world'):
            log(f'{lvl}: world')
            b, _ = convert_world(b, dims, log)
        elif ln.endswith('_dialog.bin'):
            b = dialog
        new_entries.append((n, b))
    tmp = os.path.join(out_dir, f'_{lvl}_inner.lmp')
    lmp.build(new_entries, tmp)
    inner_x = open(tmp, 'rb').read()
    os.remove(tmp)
    env = open(os.path.join(xenv_dir, 'env.lmp'), 'rb').read()
    wenv = open(os.path.join(xenv_dir, 'waterenv.lmp'), 'rb').read()
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, lvl + '.gob'), 'wb').write(build_gob([(lvl + '.lmp', inner_x), ('env.lmp', env), ('waterenv.lmp', wenv)]))
    open(os.path.join(out_dir, lvl + '.tex'), 'wb').write(xtex)
    open(os.path.join(out_dir, lvl + '.vat'), 'wb').write(music_bytes)
    log(f'{lvl}: done -> {out_dir}')


def main():
    psp_dir, lvl, music, music_name, xenv, out = sys.argv[1:7]
    convert_level(psp_dir, lvl, open(music, 'rb').read(), music_name, xenv, out)


if __name__ == '__main__':
    main()
