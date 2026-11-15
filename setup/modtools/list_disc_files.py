#!/usr/bin/env python3
"""
list_disc_files.py - List every file on a Justice League Heroes disc dump.

Works on either:
  - an Xbox ISO (XDVDFS / XISO, including full Redump images), or
  - an already-extracted folder (Xbox or PSP).

Writes files.txt next to where you run it, and prints whether the
Supergirl / Black Canary data files were found.

Usage (Windows, Command Prompt):
  python list_disc_files.py "D:\\Games\\Justice League Heroes.iso"
  python list_disc_files.py "D:\\Games\\JLH_extracted"
Optional:
  --scan   also search inside every file for the names "supergrl" and "bcanary"
           (slower; finds them even if they are packed inside an archive)
"""
import argparse
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Where the game partition starts in the different kinds of Xbox ISO dumps.
PARTITION_OFFSETS = [0, 0x18300000, 0x2080000, 0xFD90000]
NEEDLES = [b"supergrl", b"bcanary"]


# ---------------------------------------------------------------- XISO ---
def find_partition(f):
    for base in PARTITION_OFFSETS:
        f.seek(base + 32 * SECTOR)
        if f.read(len(MAGIC)) == MAGIC:
            return base
    return None


def walk_xiso(f, base, sector, size, path, out):
    if size == 0:
        return
    f.seek(base + sector * SECTOR)
    table = f.read(size)
    seen = set()
    stack = [0]
    while stack:
        off = stack.pop()
        if off in seen or off + 14 > len(table):
            continue
        seen.add(off)
        left, right, start, fsize, attr, nlen = struct.unpack_from("<HHIIBB", table, off)
        if left == 0xFFFF and right == 0xFFFF:
            continue  # padding
        name = table[off + 14:off + 14 + nlen].decode("latin-1")
        full = f"{path}/{name}" if path else name
        if attr & 0x10:
            out.append((full + "/", 0, None))
            walk_xiso(f, base, start, fsize, full, out)
        else:
            out.append((full, fsize, base + start * SECTOR))
        if left and left != 0xFFFF:
            stack.append(left * 4)
        if right and right != 0xFFFF:
            stack.append(right * 4)


def list_iso(iso):
    out = []
    with open(iso, "rb") as f:
        base = find_partition(f)
        if base is None:
            sys.exit("This doesn't look like an Xbox ISO (no XDVDFS header found).\n"
                     "If it's the PSP .iso, extract it first with 7-Zip and run this on the folder.")
        f.seek(base + 32 * SECTOR + 20)
        root_sector, root_size = struct.unpack("<II", f.read(8))
        walk_xiso(f, base, root_sector, root_size, "", out)
    return sorted(out, key=lambda e: e[0].lower())


# -------------------------------------------------------------- folder ---
def list_folder(folder):
    out = []
    for dirpath, dirs, files in os.walk(folder):
        rel = os.path.relpath(dirpath, folder).replace("\\", "/")
        rel = "" if rel == "." else rel
        for d in dirs:
            out.append((f"{rel}/{d}/" if rel else f"{d}/", 0, None))
        for fn in files:
            p = os.path.join(dirpath, fn)
            out.append((f"{rel}/{fn}" if rel else fn, os.path.getsize(p), p))
    return sorted(out, key=lambda e: e[0].lower())


# ---------------------------------------------------------------- scan ---
def scan_contents(src, entries, is_iso):
    hits = []
    fh = open(src, "rb") if is_iso else None
    files = [e for e in entries if e[2] is not None and e[1] > 0]
    for i, (name, size, loc) in enumerate(files, 1):
        print(f"\r  scanning {i}/{len(files)}", end="", flush=True)
        f = fh if is_iso else open(loc, "rb")
        if is_iso:
            f.seek(loc)
        remaining, tail = size, b""
        found = set()
        while remaining > 0:
            chunk = f.read(min(remaining, 8 << 20))
            if not chunk:
                break
            remaining -= len(chunk)
            buf = (tail + chunk).lower()
            for n in NEEDLES:
                if n in buf:
                    found.add(n.decode())
            tail = chunk[-16:]
        if not is_iso:
            f.close()
        if found:
            hits.append((name, sorted(found)))
    if fh:
        fh.close()
    print()
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Xbox .iso file, or an extracted disc folder")
    ap.add_argument("-o", "--out", default="files.txt")
    ap.add_argument("--scan", action="store_true", help="search inside files for supergrl/bcanary")
    a = ap.parse_args()

    is_iso = os.path.isfile(a.source)
    entries = list_iso(a.source) if is_iso else list_folder(a.source)

    total = sum(s for _, s, _ in entries)
    nfiles = sum(1 for n, _, _ in entries if not n.endswith("/"))
    label = os.path.basename(a.source.rstrip("/\\"))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"# {label}: {nfiles} files, {total:,} bytes\n")
        for name, size, _ in entries:
            f.write(f"{name}\n" if name.endswith("/") else f"{name}\t{size}\n")

    print(f"{nfiles} files, {total / 1048576:.1f} MB -> {a.out}")
    print("\nSupergirl / Black Canary files by name:")
    named = [n for n, _, _ in entries if any(k.decode() in n.lower() for k in NEEDLES)]
    print("\n".join(f"  FOUND  {n}" for n in named) or "  none found by filename")

    if a.scan:
        print("\nSearching inside files...")
        hits = scan_contents(a.source, entries, is_iso)
        with open(a.out, "a", encoding="utf-8") as f:
            f.write("\n# Files containing supergrl/bcanary\n")
            for n, w in hits:
                f.write(f"{n}\t{','.join(w)}\n")
                print(f"  {n}: {', '.join(w)}")
        if not hits:
            print("  no matches inside any file")

    print(f"\nSend me {a.out}.")


if __name__ == "__main__":
    main()
