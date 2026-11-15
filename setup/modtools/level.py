#!/usr/bin/env python3
"""
level.py - Justice League Heroes level containers (PSP and Xbox).

  <level>.gob : entries of {char name[32], u32 offset, u32 size}, ended by an empty name.
                Holds <level>.lmp (ntsc_dialog.bin, pal_en_dialog.bin, <level>.world,
                level.amx, objects.ob), env.lmp, waterenv.lmp.
  *_dialog.bin: 80-byte stream records {char name[60], u32 size, u32 offset, u32 ?, u32 flags},
                ended by a record with an empty name whose offset = total size.
                They describe the audio streams inside <level>.vat.
  <level>.vat : the streams back to back (2048-aligned).
                Xbox: stereo Xbox ADPCM, 72-byte blocks (two 4-byte headers + 64 bytes).
                PSP : one RIFF/ATRAC3plus stream (mono 44.1 kHz).
  <level>.tex : u32 0, then {u32 texture-group id, u32 offset, u32 size} ... until id 0xFFFFFFFE.

  python level.py gob   file.gob            list entries
  python level.py tracks file.gob           list audio streams named in the level
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp  # noqa: E402


def read_gob(data):
    out, o = [], 0
    while o + 40 <= len(data):
        name = data[o:o + 32].split(b'\0')[0].decode('latin-1')
        if not name:
            break
        off, size = struct.unpack_from('<II', data, o + 32)
        out.append((name, data[off:off + size]))
        o += 40
    return out


def read_dialog(data):
    recs = []
    for o in range(0, len(data) - 79, 80):
        name = data[o:o + 60].split(b'\0')[0].decode('latin-1')
        size, off, a, flags = struct.unpack_from('<4I', data, o + 60)
        if not name:
            break
        recs.append(dict(name=name, size=size, offset=off, a=a, flags=flags))
    return recs


def build_dialog(recs):
    out, pos = bytearray(), 0
    for r in recs:
        out += r['name'].encode('latin-1').ljust(60, b'\0')
        out += struct.pack('<5I', r['size'], r['offset'], r.get('a', 0), r.get('flags', 0x90000), 0)
        pos = max(pos, r['offset'] + r['size'])
    out += b'\0' * 60 + struct.pack('<5I', 0, pos, 0, 0, 0)     # records are 80 bytes
    return bytes(out)


def level_tracks(gob_data):
    """Audio streams of a level: list of dicts from ntsc_dialog.bin."""
    for name, d in read_gob(gob_data):
        if name.lower().endswith('.lmp') and name.lower() not in ('env.lmp', 'waterenv.lmp'):
            for n, body in [(e[0], e[1]) for e in lmp.read_bytes(d)]:
                if n.lower() == 'ntsc_dialog.bin':
                    return read_dialog(body)
    return []


def read_tex_table(data):
    ents, o = [], 4
    while o + 12 <= len(data):
        i, off, sz = struct.unpack_from('<3I', data, o)
        if i == 0xFFFFFFFE:
            break
        ents.append((i, off, sz))
        o += 12
    return ents


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    d = open(path, 'rb').read()
    if cmd == 'gob':
        for n, b in read_gob(d):
            print(f'{len(b):>10}  {n}')
    elif cmd == 'tracks':
        for r in level_tracks(d):
            print(f"{r['offset']:#010x} {r['size']:#010x}  {r['name']}")


if __name__ == '__main__':
    main()
