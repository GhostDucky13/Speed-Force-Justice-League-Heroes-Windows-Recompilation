#!/usr/bin/env python3
"""
render_preview.py - Quick software render of a decoded mesh (front + side views,
textured if a texture is given), to visually verify model decoding.

Usage: python render_preview.py model.vif [texture.tex] out.png
Works on PSP .vif (via vif_psp) and Xbox .vif (via vif_xbox, when available).
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tex as texmod  # noqa: E402


def strips_to_tris(strips):
    tris = []
    for s in strips:
        for i in range(len(s) - 2):
            a, b, c = s[i], s[i + 1], s[i + 2]
            if a['pos'] == b['pos'] or b['pos'] == c['pos'] or a['pos'] == c['pos']:
                continue
            tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return tris


def raster(tris, view, size, tex=None, uvscale=(1, 1)):
    W = H = size
    P = np.array([[v['pos'] for v in t] for t in tris], float)
    # models are Z-up: front view looks along -Y, side view along X
    if view == 'side':
        P = P[:, :, [1, 2, 0]]
    else:
        P = P[:, :, [0, 2, 1]] * np.array([1, 1, -1])
    allp = P.reshape(-1, 3)
    lo, hi = allp.min(0), allp.max(0)
    scale = 0.9 * min(W / (hi[0] - lo[0] + 1e-9), H / (hi[1] - lo[1] + 1e-9))
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    img = np.full((H, W, 3), 245, np.uint8)
    zb = np.full((H, W), -1e9)
    light = np.array([0.3, 0.5, 0.8]); light /= np.linalg.norm(light)
    for t, p in zip(tris, P):
        sx = (p[:, 0] - cx) * scale + W / 2
        sy = H / 2 - (p[:, 1] - cy) * scale
        z = p[:, 2]
        x0, x1 = int(max(0, np.floor(sx.min()))), int(min(W - 1, np.ceil(sx.max())))
        y0, y1 = int(max(0, np.floor(sy.min()))), int(min(H - 1, np.ceil(sy.max())))
        if x1 < x0 or y1 < y0:
            continue
        d = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
        if abs(d) < 1e-9:
            continue
        n = np.cross(p[1] - p[0], p[2] - p[0]); nl = np.linalg.norm(n)
        shade = 0.35 + 0.65 * abs(np.dot(n / nl, light)) if nl else 1
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        l0 = ((sy[1] - sy[2]) * (xs - sx[2]) + (sx[2] - sx[1]) * (ys - sy[2])) / d
        l1 = ((sy[2] - sy[0]) * (xs - sx[2]) + (sx[0] - sx[2]) * (ys - sy[2])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -0.01) & (l1 >= -0.01) & (l2 >= -0.01)
        zz = l0 * z[0] + l1 * z[1] + l2 * z[2]
        m &= zz > zb[ys, xs]
        if not m.any():
            continue
        zb[ys[m], xs[m]] = zz[m]
        if tex is not None and 'uv' in t[0]:
            th, tw = tex.shape[:2]
            uv = np.array([v['uv'] for v in t], float) / 32768.0
            u = (l0 * uv[0, 0] + l1 * uv[1, 0] + l2 * uv[2, 0])[m] * uvscale[0]
            vv = (l0 * uv[0, 1] + l1 * uv[1, 1] + l2 * uv[2, 1])[m] * uvscale[1]
            tx = np.clip((u * tw).astype(int), 0, tw - 1); ty = np.clip((vv * th).astype(int), 0, th - 1)
            col = tex[ty, tx, :3].astype(float) * (0.55 + 0.45 * shade)
        else:
            col = np.array([180, 190, 210]) * shade
        img[ys[m], xs[m]] = np.clip(col, 0, 255).astype(np.uint8)
    return img


def load_tex(path):
    w, h, pal, rows, plat = texmod.decode(open(path, 'rb').read())
    pal = np.array([p[:3] for p in pal], np.uint8)
    return pal[np.array(rows)], w, h


def write_png(path, img):
    import struct, zlib
    h, w = img.shape[:2]
    raw = b''.join(b'\0' + img[y].tobytes() for y in range(h))
    def ch(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                           + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b''))


def main():
    args = sys.argv[1:]
    model, out = args[0], args[-1]
    texpath = args[1] if len(args) == 3 else None
    d = open(model, 'rb').read()
    if d[8:11] == b'PSP':
        import vif_psp
        strips = vif_psp.decode(d)[0]
    else:
        import vif_xbox
        strips = vif_xbox.decode(d)[0]
    tris = strips_to_tris(strips)
    tex, uvs = None, (1, 1)
    if texpath:
        tex, w, h = load_tex(texpath)
        td = open(texpath, 'rb').read()
        if td[4] == 0x10:  # PSP: uv relative to the actual texture size
            uvs = (1, 1)
        else:              # Xbox: uv relative to pow2 of actual size
            p2 = lambda n: 1 << (n - 1).bit_length()
            uvs = (p2(w) / w, p2(h) / h)
    a = raster(tris, 'front', 360, tex, uvs)
    b = raster(tris, 'side', 360, tex, uvs)
    write_png(out, np.concatenate([a, b], 1))
    print(f"{len(tris)} triangles -> {out}")


if __name__ == '__main__':
    main()
