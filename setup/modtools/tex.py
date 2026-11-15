#!/usr/bin/env python3
"""
tex.py - Decode/convert Justice League Heroes .tex textures (PSP and Xbox).

Header (both platforms):
  u16 width, u16 height, u8 platform (0x10 = PSP, 0x14 = Xbox), u8 flags,
  PSP: u8 log2(pow2 width), u8 log2(pow2 height); u8 header_size at +8 (PSP 0x80, Xbox 0x40)

Xbox: 256-colour RGBA palette (1024 bytes) then width*height 8-bit indices, linear.
PSP : 4-bit indices, rows padded to 16 bytes, height padded to 8, swizzled in
      16-byte x 8-row tiles; 16-colour RGBA palette (64 bytes) before the pixels.

Usage:
  python tex.py png    in.tex out.png
  python tex.py toxbox in_psp.tex out_xbox.tex
"""
import struct
import sys
import zlib


def parse(data):
    w, h, plat, flags = struct.unpack_from("<HHBB", data, 0)
    hdr = data[8]
    return w, h, plat, flags, hdr


def decode(data):
    """-> (w, h, list of (r,g,b,a) palette, list of index rows), platform"""
    w, h, plat, flags, hdr = parse(data)
    body = data[hdr:]
    if plat == 0x14:  # Xbox
        pal = [tuple(body[i * 4:i * 4 + 4]) for i in range(256)]
        px = body[1024:1024 + w * h]
        rows = [list(px[y * w:(y + 1) * w]) for y in range(h)]
        return w, h, pal, rows, "xbox"
    if plat == 0x10:  # PSP
        stride = ((w + 1) // 2 + 15) // 16 * 16
        ph = (h + 7) // 8 * 8
        palb = body[:64]
        pix = body[64:64 + stride * ph]
        pal = [tuple(palb[i * 4:i * 4 + 4]) for i in range(16)]
        # unswizzle: tiles of 16 bytes x 8 rows, row-major
        lin = bytearray(stride * ph)
        tiles_x = stride // 16
        t = 0
        for ty in range(ph // 8):
            for tx in range(tiles_x):
                for r in range(8):
                    src = t * 128 + r * 16
                    dst = (ty * 8 + r) * stride + tx * 16
                    lin[dst:dst + 16] = pix[src:src + 16]
                t += 1
        rows = []
        for y in range(h):
            row = []
            line = lin[y * stride:(y + 1) * stride]
            for x in range(w):
                b = line[x >> 1]
                row.append(b & 0x0F if x % 2 == 0 else b >> 4)
            rows.append(row)
        return w, h, pal, rows, "psp"
    raise ValueError(f"unknown platform byte 0x{plat:02X}")


def write_png(path, w, h, pal, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for i in row:
            r, g, b, a = pal[i]
            raw += bytes((r, g, b, min(255, a * 2) if a <= 0x80 else a))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def to_xbox(data, flags=None):
    w, h, pal, rows, plat = decode(data)
    if plat == "xbox":
        return data
    _, _, _, pflags, _ = parse(data)
    # PSP flags 0x20/0xA0 -> Xbox 0x40/0xC0 (keep the 0x80 bit)
    xflags = flags if flags is not None else (0x40 | (pflags & 0x80))
    hdr = bytearray(0x40)
    struct.pack_into("<HHBB", hdr, 0, w, h, 0x14, xflags)
    hdr[8] = 0x40
    pal256 = b"".join(bytes(c) for c in pal) + b"\0" * (1024 - 4 * len(pal))
    px = bytes(i for row in rows for i in row)
    return bytes(hdr) + pal256 + px


def main():
    cmd, src, dst = sys.argv[1:4]
    data = open(src, "rb").read()
    if cmd == "png":
        w, h, pal, rows, plat = decode(data)
        write_png(dst, w, h, pal, rows)
        print(f"{plat} {w}x{h}, {len(pal)} colours -> {dst}")
    elif cmd == "toxbox":
        open(dst, "wb").write(to_xbox(data))
        print(f"-> {dst}")


if __name__ == "__main__":
    main()
