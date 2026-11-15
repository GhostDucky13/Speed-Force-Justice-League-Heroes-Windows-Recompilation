#!/usr/bin/env python3
"""
gdt.py - Read/write Snowblind .gdt data tables (Justice League Heroes gamedata).

Layout: "<file>.gdt\\0", u16 table count, then per table:
  "~~Name\\0", u32 rows, u32 cols, rows x row-name strings, cols x column-name strings,
  then rows*cols cells as a packed stream: one control byte per 4 cells
  (2 bits each, LSB first): 0 = empty, 1 = f32, 2 = string (NUL-terminated), 3 = u32.
  Tables named ~~U:... use type 3 for UTF-16LE strings (2-byte aligned, filler byte
  0xFF before an odd offset, double-NUL terminated).

  python gdt.py dump file.gdt [table]
"""
import struct
import sys


def _cstr(d, o):
    e = d.index(b'\0', o)
    return d[o:e].decode('latin-1'), e + 1


def _wstr(d, o):
    e = o
    while d[e:e + 2] != b'\0\0':
        e += 2
    return d[o:e].decode('utf-16-le'), e + 2


def parse(d):
    head, o = _cstr(d, 0)
    ntab = struct.unpack_from('<H', d, o)[0]
    o += 2
    tables = []
    for _ in range(ntab):
        name, o = _cstr(d, o)
        wide = name.startswith('~~U:')
        rows, cols = struct.unpack_from('<II', d, o)
        o += 8
        rnames, cnames = [], []
        for _ in range(rows):
            s, o = _cstr(d, o); rnames.append(s)
        for _ in range(cols):
            s, o = _cstr(d, o); cnames.append(s)
        cells = []
        n = rows * cols
        while len(cells) < n:
            ctl = d[o]; o += 1
            for k in range(4):
                if len(cells) >= n:
                    break
                t = (ctl >> (2 * k)) & 3
                if t == 0:
                    cells.append(None)
                elif t == 1:
                    cells.append(struct.unpack_from('<f', d, o)[0]); o += 4
                elif t == 2:
                    s, o = _cstr(d, o); cells.append(s)
                elif wide:
                    pad = None
                    if o & 1:
                        pad = d[o]; o += 1
                    s, o = _wstr(d, o); cells.append(('w', s, pad))
                else:
                    cells.append(('u32', struct.unpack_from('<I', d, o)[0])); o += 4
        grid = [cells[r * cols:(r + 1) * cols] for r in range(rows)]
        tables.append(dict(name=name, rows=rnames, cols=cnames, grid=grid, wide=wide))
    return dict(head=head, tables=tables, end=o, size=len(d))


def build(g):
    out = bytearray(g['head'].encode('latin-1') + b'\0' + struct.pack('<H', len(g['tables'])))
    for t in g['tables']:
        out += t['name'].encode('latin-1') + b'\0'
        out += struct.pack('<II', len(t['rows']), len(t['cols']))
        for s in t['rows'] + t['cols']:
            out += s.encode('latin-1') + b'\0'
        cells = [c for row in t['grid'] for c in row]
        for i in range(0, len(cells), 4):
            grp = cells[i:i + 4]
            ctl, body = 0, bytearray()
            for k, c in enumerate(grp):
                if c is None:
                    t2 = 0
                elif isinstance(c, float):
                    t2 = 1; body += struct.pack('<f', c)
                elif isinstance(c, str):
                    t2 = 2; body += c.encode('latin-1') + b'\0'
                elif c[0] == 'w':
                    t2 = 3
                    if (len(out) + 1 + len(body)) & 1:
                        body += bytes([c[2] if c[2] is not None else 0xFF])
                    body += c[1].encode('utf-16-le') + b'\0\0'
                else:
                    t2 = 3; body += struct.pack('<I', c[1])
                ctl |= t2 << (2 * k)
            out += bytes([ctl]) + body
    return bytes(out)


def fmt(c):
    if c is None:
        return ''
    if isinstance(c, float):
        return f'{c:g}'
    if isinstance(c, tuple) and c[0] == 'w':
        return c[1].replace('\n', '\\n')
    if isinstance(c, tuple):
        return f'#{c[1]}'
    return c


def main():
    g = parse(open(sys.argv[2], 'rb').read())
    want = sys.argv[3] if len(sys.argv) > 3 else None
    for t in g['tables']:
        if want and t['name'] != want:
            continue
        print(f"== {t['name']} ({len(t['rows'])} x {len(t['cols'])})")
        print('row\t' + '\t'.join(t['cols']))
        for r, row in zip(t['rows'], t['grid']):
            print(r + '\t' + '\t'.join(fmt(c) for c in row))


if __name__ == '__main__':
    main()
