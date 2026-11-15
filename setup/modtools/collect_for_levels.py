#!/usr/bin/env python3
"""
collect_for_levels.py - Gather the few files still needed to port the PSP levels.

Run it on your PC with your own dumps:

  python collect_for_levels.py  <xbox res folder>  <psp folder with E1L7.GOB>  [out.zip]

It writes one ZIP (default jlh_level_files.zip) containing:
  1. psp/E1L7.GOB, .TEX, .VAT  - the one level that exists on both platforms, used to
                                 calibrate the PSP -> Xbox level converter.
  2. xbox_tracks/<name>.xadpcm - the Xbox versions of the four music tracks the challenge
                                 missions use (they live inside other Xbox levels' .vat files),
                                 plus tracks.txt saying which Xbox level each came from.
Nothing else is copied. Only standard Python 3 is needed.
"""
import os
import struct
import sys
import zipfile

WANTED = ['env_e03_arctic_a.vag', 'env_e09_brain.vag', 'env_e11_dark.vag', 'env_e02_subwy_a.vag']


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


def read_lmp(d):
    n = struct.unpack_from('<I', d, 0)[0]
    out = []
    for i in range(n):
        no, do, sz = struct.unpack_from('<III', d, 4 + i * 12)
        out.append((d[no:d.index(b'\0', no)].decode('latin-1'), d[do:do + sz]))
    return out


def tracks(gob_path):
    try:
        for name, body in read_gob(open(gob_path, 'rb').read()):
            if name.lower().endswith('.lmp') and name.lower() not in ('env.lmp', 'waterenv.lmp'):
                for n, b in read_lmp(body):
                    if n.lower() == 'ntsc_dialog.bin':
                        for o in range(0, len(b) - 79, 80):
                            nm = b[o:o + 60].split(b'\0')[0].decode('latin-1')
                            if not nm:
                                return
                            size, off = struct.unpack_from('<II', b, o + 60)
                            yield nm, off, size
    except Exception as e:  # not a level gob
        return


def find_ci(folder, name):
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    xres, pdir = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else 'jlh_level_files.zip'
    z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)

    for ext in ('GOB', 'TEX', 'VAT'):
        p = find_ci(pdir, 'E1L7.' + ext)
        if p:
            z.write(p, 'psp/E1L7.' + ext)
            print('added', p)
        else:
            print('MISSING in PSP folder: E1L7.' + ext)

    found, report = set(), []
    for f in sorted(os.listdir(xres)):
        if not f.lower().endswith('.gob'):
            continue
        lvl = f[:-4]
        for nm, off, size in tracks(os.path.join(xres, f)):
            if nm.lower() in WANTED and nm.lower() not in found:
                vat = find_ci(xres, lvl + '.vat')
                if not vat:
                    continue
                with open(vat, 'rb') as fh:
                    fh.seek(off)
                    data = fh.read(size)
                z.writestr('xbox_tracks/' + nm[:-4] + '.xadpcm', data)
                found.add(nm.lower())
                report.append(f'{nm}\t{lvl}\toffset {off:#x}\tsize {size:#x}')
                print('added', nm, 'from', lvl)
    for w in WANTED:
        if w not in found:
            report.append(f'{w}\tNOT FOUND')
            print('not found on Xbox:', w)
    z.writestr('xbox_tracks/tracks.txt', '\n'.join(report) + '\n')
    z.close()
    print('wrote', out)


if __name__ == '__main__':
    main()
