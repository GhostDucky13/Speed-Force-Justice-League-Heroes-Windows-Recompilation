#!/usr/bin/env python3
"""
leveltex.py - Decode Justice League Heroes level texture packs (<level>.tex), PSP and Xbox.

Reimplements the XBE's tile decoder (0x73684). File layout:
  u32 0, then {u32 group id, u32 offset, u32 size} ... until id 0xFFFFFFFE.
  Group: u32 image count, 60 bytes pad, then 64-byte image records:
      s16 w, s16 h, u16 flags (0x0100 = tiled/compressed, 0x4000 = raw), u16 cache slot,
      u32 descriptor offset (relative to the group), rest runtime.
  Raw image (flag 0x4000): 256x RGBA palette then w*h 8-bit pixels (row stride w).
  Tiled image: descriptor = u32 base offset, then runs {s8 x0, s8 y0, s8 x1, s8 y1} each
      followed by (x1-x0+1)*(y1-y0+1) u32 tile offsets (row by row), ended by 0xFF.
      16x16 tiles. Base ("codebook", shared by the images of a group):
        +0x000 palette 256 x {R,G,B,A}
        +0x400 context table [256 prev][8] (u8)
        +0xC00 u32 n, n x u16 symbols, then u32 first[18], u32 limit[18]
      Tile = 256 Huffman symbols, MSB-first in big-endian u16 words:
        sym < 0x100       literal palette index
        0x100..0x104      copy neighbour pixel at offset -1, -16, -17, -15, -2
        >= 0x105          ctx[prev pixel][sym - 0x105]
  The game boosts palette saturation by 1.3 when uploading; decode() returns the stored colours.

  python leveltex.py dump file.tex outdir [group_id_hex]    writes PNGs
"""
import os
import struct
import sys
import zlib

NEIGH = [-1, -16, -17, -15, -2]


def read_table(d):
    ents, o = [], 4
    while o + 12 <= len(d):
        i, off, sz = struct.unpack_from('<3I', d, o)
        if i == 0xFFFFFFFE:
            break
        ents.append((i, off, sz))
        o += 12
    return ents


def images(d, goff):
    n = struct.unpack_from('<I', d, goff)[0]
    out = []
    for k in range(n):
        r = goff + 0x40 + 64 * k
        w, h, flags, slot, desc = struct.unpack_from('<hhHHI', d, r)
        out.append(dict(w=w, h=h, flags=flags, desc=desc, rec=r))
    return out


class Codebook:
    def __init__(self, d, base):
        self.base = base
        self.pal = [tuple(d[base + 4 * i:base + 4 * i + 4]) for i in range(256)]
        self.ctx = d[base + 0x400:base + 0xC00]
        n = struct.unpack_from('<I', d, base + 0xC00)[0]
        self.syms = struct.unpack_from(f'<{n}h', d, base + 0xC04)
        t = base + 0xC04 + 2 * n
        self.first = struct.unpack_from('<18i', d, t)
        self.limit = struct.unpack_from('<18i', d, t + 0x48)
        # fast table for codes up to 8 bits
        self.fast = []
        for i in range(256):
            L, sh = 1, 7
            while sh >= 0 and (i >> sh) > self.limit[L]:
                L += 1; sh -= 1
            if L > 8:
                self.fast.append(None)
            else:
                self.fast.append((self.syms[self.first[L] + (i >> (8 - L))], L))

    def tile(self, d, p):
        out = bytearray(256)
        pos, prev = 0, 0
        for k in range(256):
            wi = p + (pos >> 4) * 2
            v =(_word(d, wi) << 16) | _word(d, wi + 2)
            v = ((v << (pos & 15)) & 0xFFFFFFFF) >> 16
            f = self.fast[v >> 8]
            if f:
                sym, L = f
            else:
                L = 9
                while (v >> (16 - L)) > self.limit[L]:
                    L += 1
                sym = self.syms[self.first[L] + (v >> (16 - L))]
            pos += L
            if sym < 0x100:
                px = sym
            elif sym < 0x105:
                px = out[k + NEIGH[sym - 0x100]]
            else:
                px = self.ctx[prev * 8 + sym - 0x105]
            out[k] = px
            prev = px
        return out


def _word(d, o):
    return d[o] | (d[o + 1] << 8)


def decode(d, goff, img, cbcache=None):
    """Returns (w, h, palette, indices) for one image (indices row-major, stride w)."""
    w, h = img['w'], img['h']
    desc = goff + img['desc']
    if img['flags'] & 0x4000 or not img['flags'] & 0x0100:
        pal = [tuple(d[desc + 4 * i:desc + 4 * i + 4]) for i in range(256)]
        px = d[desc + 0x400:desc + 0x400 + w * h]
        return w, h, pal, bytes(px)
    base = goff + struct.unpack_from('<I', d, desc)[0]
    cb = (cbcache or {}).get(base) or Codebook(d, base)
    if cbcache is not None:
        cbcache[base] = cb
    tw, th = (w + 15) // 16, (h + 15) // 16
    buf = bytearray(tw * 16 * th * 16)
    stride = tw * 16
    o = desc + 4
    while d[o] != 0xFF:
        x0, y0, x1, y1 = struct.unpack_from('4b', d, o)
        o += 4
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                tp = goff + struct.unpack_from('<I', d, o)[0]
                o += 4
                t = cb.tile(d, tp)
                for r in range(16):
                    yy = ty * 16 + r
                    if 0 <= tx < tw and 0 <= ty < th:
                        buf[yy * stride + tx * 16:yy * stride + tx * 16 + 16] = t[r * 16:r * 16 + 16]
    px = bytes(b for y in range(h) for b in buf[y * stride:y * stride + w])
    return w, h, cb.pal, px


def to_rgba(w, h, pal, px, opaque=True):
    """Alpha is 0 in level palettes (unused for opaque surfaces), so force 255 by default."""
    lut = [bytes(p[:3]) + (b'\xff' if opaque else bytes(p[3:4])) for p in pal]
    return b''.join(lut[i] for i in px)


def write_png(path, w, h, rgba):
    raw = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xFFFFFFFF)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def main():
    cmd, path, outdir = sys.argv[1:4]
    want = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    d = open(path, 'rb').read()
    os.makedirs(outdir, exist_ok=True)
    for gid, goff, _ in read_table(d):
        if want is not None and gid != want:
            continue
        cache = {}
        for k, img in enumerate(images(d, goff)):
            w, h, pal, px = decode(d, goff, img, cache)
            write_png(os.path.join(outdir, f'{gid:04x}_{k:02d}_{w}x{h}.png'), w, h, to_rgba(w, h, pal, px))


if __name__ == '__main__':
    main()


# ----------------------------------------------------------------------------- encoder
import heapq  # noqa: E402


def _huff_lengths(freq, maxlen=16):
    """freq: dict sym->count. Returns dict sym->code length (<= maxlen)."""
    f = dict(freq)
    if len(f) == 1:
        s = next(iter(f))
        f[s + 1 if s + 1 not in f else s - 1] = 1
    while True:
        heap = [(c, i, (s,)) for i, (s, c) in enumerate(sorted(f.items()))]
        heapq.heapify(heap)
        depth = {s: 0 for s in f}
        cnt = len(heap)
        while len(heap) > 1:
            c1, _, a = heapq.heappop(heap)
            c2, _, b = heapq.heappop(heap)
            for s in a + b:
                depth[s] += 1
            heapq.heappush(heap, (c1 + c2, cnt, a + b)); cnt += 1
        if max(depth.values()) <= maxlen:
            return depth
        f = {s: c // 2 + 1 for s, c in f.items()}


def _canonical(lengths):
    """-> (codes {sym:(code,len)}, syms list, first[18], limit[18]) matching the game's decoder."""
    order = sorted(lengths, key=lambda s: (lengths[s], s))
    codes, syms = {}, []
    first, limit = [0] * 18, [-1] * 18
    code, idx, L = 0, 0, 1
    by_len = {}
    for s in order:
        by_len.setdefault(lengths[s], []).append(s)
    for L in range(1, 18):
        group = by_len.get(L, [])
        first[L] = idx - code
        for s in group:
            codes[s] = (code, L)
            syms.append(s)
            code += 1; idx += 1
        limit[L] = code - 1
        code <<= 1
    limit[17] = 0x7FFFFFFF
    return codes, syms, first, limit


def _tile_symbols(tile):
    """Literal palette index, or a copy of the neighbour at -1, -16, -17, -15, -2 (0x100-0x104)."""
    out = []
    for k, px in enumerate(tile):
        for code, off in enumerate(NEIGH):
            if k + off >= 0 and tile[k + off] == px:
                out.append(0x100 + code)
                break
        else:
            out.append(px)
    return out


def _pack_bits(symbols, codes):
    bits, nbits = 0, 0
    acc = bytearray()
    out_bits = []
    for s in symbols:
        c, L = codes[s]
        out_bits.append((c, L))
    # build big integer bitstring
    total = sum(L for _, L in out_bits)
    v = 0
    for c, L in out_bits:
        v = (v << L) | c
    nwords = (total + 15) // 16 + 2          # +2 words: decoder reads ahead
    v <<= nwords * 16 - total
    for i in range(nwords):
        w = (v >> ((nwords - 1 - i) * 16)) & 0xFFFF
        acc += struct.pack('<H', w)
    return bytes(acc)


def _tiles(w, h, px):
    tw, th = (w + 15) // 16, (h + 15) // 16
    tl = []
    for ty in range(th):
        for tx in range(tw):
            t = bytearray(256)
            for r in range(16):
                y = min(ty * 16 + r, h - 1)
                row = px[y * w:(y + 1) * w]
                for c in range(16):
                    t[r * 16 + c] = row[min(tx * 16 + c, w - 1)]
            tl.append(_tile_symbols(t))
    return tw, th, tl


def encode_group(images):
    """images: list of (w, h, indices bytes row-major, palette 256x(r,g,b,a)).
    One codebook (palette + Huffman tables) per distinct palette. Returns group bytes."""
    n = len(images)
    pal_ids, pals = [], []
    for img in images:
        key = tuple(tuple(c) for c in img[3])
        if key not in pals:
            pals.append(key)
        pal_ids.append(pals.index(key))
    tiled = [_tiles(w, h, px) for w, h, px, _ in images]
    out = bytearray(struct.pack('<I', n) + b'\0' * 60)
    rec_off = len(out)
    out += b'\0' * (64 * n)
    books = []
    for pi, pal in enumerate(pals):
        freq = {}
        for (tw, th, tl), pid in zip(tiled, pal_ids):
            if pid == pi:
                for t in tl:
                    for sy in t:
                        freq[sy] = freq.get(sy, 0) + 1
        codes, syms, first, limit = _canonical(_huff_lengths(freq))
        while len(out) % 4:
            out += b'\0'
        books.append((len(out), codes))
        out += b''.join(bytes(c[:4]) for c in pal) + b'\0' * (1024 - 4 * len(pal))
        out += b'\0' * 0x800
        out += struct.pack('<I', len(syms)) + struct.pack(f'<{len(syms)}h', *syms)
        out += struct.pack('<18i', *first) + struct.pack('<18i', *limit)
    for k, ((w, h, _, _), (tw, th, tl), pid) in enumerate(zip(images, tiled, pal_ids)):
        cb_off, codes = books[pid]
        while len(out) % 4:
            out += b'\0'
        desc = len(out)
        struct.pack_into('<hhHHI', out, rec_off + 64 * k, w, h, 0x010C, 0, desc)
        out += struct.pack('<I', cb_off) + struct.pack('4b', 0, 0, tw - 1, th - 1)
        ptr_pos = len(out)
        out += b'\0' * (4 * tw * th) + b'\xff\0\0\0'
        for i, syms_t in enumerate(tl):
            while len(out) % 2:
                out += b'\0'
            struct.pack_into('<I', out, ptr_pos + 4 * i, len(out))
            out += _pack_bits(syms_t, codes)
    return bytes(out)


def build_tex(groups):
    """groups: list of (id, group bytes) -> .tex file bytes."""
    table = bytearray(struct.pack('<I', 0))
    body = bytearray()
    pos = 0x800 if 4 + 12 * (len(groups) + 1) <= 0x800 else (4 + 12 * (len(groups) + 1) + 0x7FF) & ~0x7FF
    hdr_size = pos
    for gid, g in groups:
        table += struct.pack('<3I', gid, pos, len(g))
        body += g
        pad = (-len(g)) % 0x800
        body += b'\0' * pad
        pos += len(g) + pad
    table += struct.pack('<3I', 0xFFFFFFFE, 0, 0)
    table += b'\0' * (hdr_size - len(table))
    return bytes(table + body)
