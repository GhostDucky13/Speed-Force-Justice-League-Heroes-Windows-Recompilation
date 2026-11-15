#!/usr/bin/env python3
"""
sf_extract.py - extract a Justice League Heroes disc dump the player made themselves.

  python sf_extract.py xbox <Xbox .iso/.xiso> <out dir>
  python sf_extract.py psp  <PSP .iso>         <out dir>

Xbox: XDVDFS (plain XISO or a full Redump image, the game partition is found).
PSP:  ISO 9660 (UMD dump). Standard library only.
"""
import os
import struct
import sys

SECTOR = 2048
XMAGIC = b"MICROSOFT*XBOX*MEDIA"
PARTITION_OFFSETS = [0, 0x18300000, 0x2080000, 0xFD90000]


def _copy(f, pos, size, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    f.seek(pos)
    with open(dst, "wb") as o:
        left = size
        while left > 0:
            b = f.read(min(left, 8 << 20))
            if not b:
                raise IOError("dump ends early: " + dst)
            o.write(b)
            left -= len(b)


def extract_xbox(iso, out, progress=print):
    with open(iso, "rb") as f:
        base = None
        for b in PARTITION_OFFSETS:
            f.seek(b + 32 * SECTOR)
            if f.read(len(XMAGIC)) == XMAGIC:
                base = b
                break
        if base is None:
            raise ValueError("not an Xbox disc image (no XDVDFS header)")
        f.seek(base + 32 * SECTOR + 20)
        root_sector, root_size = struct.unpack("<II", f.read(8))
        files = []

        def walk(sector, size, path):
            if size == 0:
                return
            f.seek(base + sector * SECTOR)
            table = f.read(size)
            seen, stack = set(), [0]
            while stack:
                off = stack.pop()
                if off in seen or off + 14 > len(table):
                    continue
                seen.add(off)
                left, right, start, fsize, attr, nlen = struct.unpack_from("<HHIIBB", table, off)
                if left == 0xFFFF and right == 0xFFFF:
                    continue
                name = table[off + 14:off + 14 + nlen].decode("latin-1")
                full = os.path.join(path, name)
                if attr & 0x10:
                    walk(start, fsize, full)
                else:
                    files.append((full, base + start * SECTOR, fsize))
                if left and left != 0xFFFF:
                    stack.append(left * 4)
                if right and right != 0xFFFF:
                    stack.append(right * 4)

        walk(root_sector, root_size, "")
        for i, (name, pos, size) in enumerate(sorted(files)):
            _copy(f, pos, size, os.path.join(out, name))
            progress(f"xbox {i + 1}/{len(files)} {name}")
    return len(files)


def extract_psp(iso, out, progress=print):
    with open(iso, "rb") as f:
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)
        if pvd[1:6] != b"CD001":
            raise ValueError("not a PSP disc image (no ISO 9660 header)")
        root = pvd[156:156 + 34]
        files = []

        def walk(extent, size, path):
            f.seek(extent * SECTOR)
            data = f.read(size)
            off = 0
            while off < len(data):
                ln = data[off]
                if ln == 0:
                    off = (off // SECTOR + 1) * SECTOR
                    continue
                ext = struct.unpack_from("<I", data, off + 2)[0]
                sz = struct.unpack_from("<I", data, off + 10)[0]
                flags = data[off + 25]
                nlen = data[off + 32]
                name = data[off + 33:off + 33 + nlen]
                off += ln
                if name in (b"\x00", b"\x01"):
                    continue
                name = name.decode("latin-1").split(";")[0]
                full = os.path.join(path, name)
                if flags & 2:
                    walk(ext, sz, full)
                else:
                    files.append((full, ext * SECTOR, sz))

        walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
        for i, (name, pos, size) in enumerate(sorted(files)):
            _copy(f, pos, size, os.path.join(out, name))
            progress(f"psp {i + 1}/{len(files)} {name}")
    return len(files)


def main():
    kind, iso, out = sys.argv[1:4]
    n = (extract_xbox if kind == "xbox" else extract_psp)(iso, out, progress=lambda s: None)
    print(f"{kind}: {n} files -> {out}")


if __name__ == "__main__":
    main()
