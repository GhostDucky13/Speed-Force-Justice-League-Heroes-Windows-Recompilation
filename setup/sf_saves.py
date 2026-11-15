#!/usr/bin/env python3
"""
sf_saves.py - bring Justice League Heroes saves from a real Xbox to Speed Force.

  python sf_saves.py --in <folder or slot.bin> --out <install dir>\\saves [--dry-run]

An Xbox save (UDATA\\57520001\\<id>\\slot.bin) is a 53,248-byte record plus a 20-byte
signature made with the console's own key. Speed Force runs the same game code, so the
record is used as it is and only signed again with the PC version's key.

A completed save ("Completed Game", which the original game
refuses to load) starts Episode 1 the Chapter Select way when you pick it in Load Saved Game:
that is done by the game's menu (modtools/patch_chapter.py), so it also works for completed
saves made on the PC.

The game keeps five slots, each in a fixed folder (ACCD073B22C1 for slot 1, then +0x3B per
slot). Imported saves go into the free slots; existing PC saves are never overwritten.

Only Xbox saves are supported.
Standard library only.
"""
import argparse
import hashlib
import hmac
import os
import sys

RECORD = 53248
TITLE = '57520001'
SLOTS = 5
FIRST_FOLDER = 0xACCD073B22C1
FOLDER_STEP = 0x3B
log_lines = []


def log(m):
    print(m, flush=True)
    log_lines.append(m)


def folder_name(n):
    return '%012X' % (FIRST_FOLDER + FOLDER_STEP * (n - 1))


def level_of(rec):
    return rec[:16].split(b'\0')[0].decode('latin-1')


def plausible(rec):
    name = rec[:16].split(b'\0')[0]
    return (len(rec) == RECORD and name[:1] == b'e' and 3 <= len(name) <= 8
            and all(32 < c < 127 for c in name))


def sign(rec):
    return rec + hmac.new(b'\0' * 16, rec, hashlib.sha1).digest()


def meta(n):
    return ('﻿' + f'Name=JLH Save {n} - \r\n').encode('utf-16-le')


def used_slots(out):
    root = os.path.join(out, 'UDATA', TITLE)
    return {n for n in range(1, SLOTS + 1)
            if os.path.isfile(os.path.join(root, folder_name(n), 'slot.bin'))}


def collect(src):
    """[(where, record, note)] for every usable save under src."""
    found = []
    paths = [src] if os.path.isfile(src) else sorted(
        os.path.join(dp, f) for dp, _, fs in os.walk(src) for f in fs)
    for p in paths:
        low = os.path.basename(p).lower()
        try:
            if low == 'slot.bin':
                d = open(p, 'rb').read()
                if len(d) != RECORD + 20 or not plausible(d[:RECORD]):
                    log(f'{p}: not a Justice League Heroes Xbox save, skipped')
                else:
                    found.append((p, d[:RECORD], f'Xbox save ({level_of(d)})'))
        except OSError as e:
            log(f'{p}: skipped ({e})')
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not os.path.exists(a.src):
        log(f'{a.src}: not found')
        return 1
    seen, saves = set(), []
    for p, rec, note in collect(a.src):
        h = hashlib.sha1(rec).digest()
        if h not in seen:
            seen.add(h)
            saves.append((p, rec, note))
    free = [n for n in range(1, SLOTS + 1) if n not in used_slots(a.out)]
    log(f'{len(saves)} save(s) to import; free slots: {", ".join(map(str, free)) or "none"}')
    done = 0
    for (p, rec, note), n in zip(saves, free):
        log(f'  slot {n}: {note}  <- {p}')
        if a.dry_run:
            continue
        d = os.path.join(a.out, 'UDATA', TITLE, folder_name(n))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'slot.bin'), 'wb') as f:
            f.write(sign(rec))
        with open(os.path.join(d, 'SaveMeta.xbx'), 'wb') as f:
            f.write(meta(n))
        done += 1
    for p, _, _ in saves[len(free):]:
        log(f'  no free slot for {p} (delete a save in game first)')
    if not a.dry_run:
        t = os.path.join(a.out, 'UDATA', TITLE, 'TitleMeta.xbx')
        if os.path.isdir(os.path.dirname(t)) and not os.path.exists(t):
            with open(t, 'wb') as f:
                f.write(('﻿' + 'TitleName=Justice League Heroes\r\n').encode('utf-16-le'))
        with open(os.path.join(a.out, 'import.log'), 'a', encoding='utf-8') as f:
            f.write('\n'.join(log_lines) + '\n')
    log(f'{done} save(s) imported')
    return 0 if done or not saves else 1


if __name__ == '__main__':
    sys.exit(main())
