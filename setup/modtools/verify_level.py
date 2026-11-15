#!/usr/bin/env python3
"""
verify_level.py - check a converted Xbox level (.gob/.tex/.vat) against every failure seen so far.

  python verify_level.py out/levels/e1l8      (path without extension)

Checks
  gob    : 40-byte entries, 0x800-aligned, <lvl>.lmp + env.lmp + waterenv.lmp; inner lmp has
           <lvl>.world, level.amx, objects.ob, ntsc/pal dialog
  dialog : 80-byte records, end record offset = total, every stream inside the .vat, .vat size
  world  : Xbox mesh descriptors ({vp, nverts, ip, nindices}) all BELOW the geometry; geometry
           one packed block (indices | u32 vbsize | vertices) per mesh, vp -> vbsize; vbsize = 16*nverts;
           indices < nverts; every object's texture group / image record exists in the .tex
  tex    : table terminated by 0xFFFFFFFE, every image of every group decodes, group size and
           image size limits, total size
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import level as L  # noqa: E402
import leveltex as T  # noqa: E402
import lmp  # noqa: E402
import world as W  # noqa: E402

GROUP_LIMIT = 0x160000
MAX_DIM = 512


def check(path):
    lvl = os.path.basename(path)
    errs, info = [], []
    gob = open(path + '.gob', 'rb').read()
    tex = open(path + '.tex', 'rb').read()
    vat = open(path + '.vat', 'rb').read()

    # gob
    ents = L.read_gob(gob)
    names = [n.lower() for n, _ in ents]
    if names != [lvl + '.lmp', 'env.lmp', 'waterenv.lmp']:
        errs.append(f'gob entries {names}')
    o = 0
    while gob[o:o + 1] != b'\0':
        off, size = struct.unpack_from('<II', gob, o + 32)
        if off % 0x800 or off + size > len(gob):
            errs.append(f'gob entry at {o}: offset {off:#x} size {size:#x}')
        o += 40
    inner = {n.lower(): b for n, b, _ in lmp.read_bytes(dict(ents)[lvl + '.lmp'])}
    for need in (lvl + '.world', 'level.amx', 'objects.ob', 'ntsc_dialog.bin', 'pal_en_dialog.bin'):
        if need not in inner:
            errs.append(f'missing {need} in {lvl}.lmp')

    # dialog
    for dn in ('ntsc_dialog.bin', 'pal_en_dialog.bin'):
        d = inner.get(dn, b'')
        if len(d) % 80:
            errs.append(f'{dn}: size {len(d)} not a multiple of 80')
        recs = L.read_dialog(d)
        end = struct.unpack_from('<I', d, len(d) - 80 + 64)[0] if len(d) >= 80 else -1
        tot = max((r['offset'] + r['size'] for r in recs), default=0)
        if end != tot:
            errs.append(f'{dn}: end record offset {end} != {tot}')
        if tot > len(vat):
            errs.append(f'{dn}: streams end {tot} > vat {len(vat)}')
        info.append(f'{dn}: ' + ', '.join(f"{r['name']} {r['size']}" for r in recs))

    # tex
    table = L.read_tex_table(tex)
    groups = {}
    total_imgs = 0
    for gid, off, size in table:
        if size > GROUP_LIMIT:
            errs.append(f'tex group {gid:#x} size {size:#x} > limit')
        try:
            imgs = T.images(tex, off)
            cb = {}
            recs = {}
            for k, img in enumerate(imgs):
                w, h = img['w'], img['h']
                if w > MAX_DIM or h > MAX_DIM or w <= 0 or h <= 0:
                    errs.append(f'tex group {gid:#x} image {k}: {w}x{h}')
                T.decode(tex, off, img, cb)
                recs[0x40 + 64 * k] = (w, h)
                total_imgs += 1
            groups[gid] = recs
        except Exception as e:  # noqa: BLE001
            errs.append(f'tex group {gid:#x}: decode failed: {type(e).__name__} {e}')
    info.append(f'tex: {len(table)} groups, {total_imgs} images, {len(tex)} bytes')

    # world
    wd = inner.get(lvl + '.world', b'')
    h = W.header(wd)
    objs = W.objects(wd)
    descs = {}
    for r in objs:
        if r['flags'] & 0xC880:
            continue
        if r['n'] != 1:
            errs.append(f'object {r["idx"]}: +4 = {r["n"]} (Xbox = 1)')
        descs[r['ptr']] = struct.unpack_from('<4I', wd, r['ptr'])
        g = groups.get(r['tex'])
        if g is None:
            errs.append(f'object {r["idx"]}: texture group {r["tex"]:#x} not in .tex')
        elif r['f20'] not in g:
            errs.append(f'object {r["idx"]}: image record {r["f20"]:#x} not in group {r["tex"]:#x}')
    if descs:
        geo_lo = min(min(vp, ip) for vp, nv, ip, ni in descs.values())
        if max(descs) + 0x80 > geo_lo:
            errs.append(f'descriptor at {max(descs):#x} overlaps geometry starting {geo_lo:#x}')
        blocks = sorted((ip, vp, nv, ni) for vp, nv, ip, ni in descs.values())
        pos = blocks[0][0]
        need = 0
        for ip, vp, nv, ni in blocks:
            if ip != pos:
                errs.append(f'mesh at {ip:#x}: geometry not packed (expected {pos:#x})')
                break
            if vp != ip + 2 * ni:
                errs.append(f'mesh at {ip:#x}: vp {vp:#x} != ip + 2*ni')
                break
            vbsize = struct.unpack_from('<I', wd, vp)[0]
            if vbsize != 16 * nv:
                errs.append(f'mesh at {ip:#x}: vbsize {vbsize} != 16*{nv}')
            idx = struct.unpack_from(f'<{ni}H', wd, ip)
            if idx and max(idx) >= nv:
                errs.append(f'mesh at {ip:#x}: index {max(idx)} >= {nv} vertices')
            if nv > 65535:
                errs.append(f'mesh at {ip:#x}: {nv} vertices')
            pos = vp + 4 + 16 * nv
            need += 16 * nv + 2 * ni
        info.append(f'world: {len(objs)} objects, {len(descs)} meshes, geometry {blocks[0][0]:#x}-{pos:#x} '
                    f'of {len(wd):#x}, max nv {max(d[1] for d in descs.values())}, '
                    f'max ni {max(d[3] for d in descs.values())}')
    return errs, info


def main():
    bad = 0
    for p in sys.argv[1:]:
        errs, info = check(p)
        print(f'== {p}: {"OK" if not errs else str(len(errs)) + " PROBLEMS"}')
        for i in info:
            print('   ', i)
        for e in errs[:20]:
            print('   !!', e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
