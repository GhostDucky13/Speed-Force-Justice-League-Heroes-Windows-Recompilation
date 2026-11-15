"""Shared helpers: load default.xbe sections, VA<->offset, string at VA."""
import json, struct, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = open(os.path.join(ROOT, 'input/default.xbe'), 'rb').read()
REP = json.load(open(os.path.join(ROOT, 'report/xbe_report.json')))
SECS = [(s['name'], int(s['va'], 16), s['raw_addr'], s['raw_size'], s['virtual_size']) for s in REP['sections']]
def va2off(v):
    for n, va, ra, rs, vs in SECS:
        if va <= v < va + rs: return ra + v - va
def off2va(o):
    for n, va, ra, rs, vs in SECS:
        if ra <= o < ra + rs: return va + o - ra
def sec_of(v):
    for n, va, ra, rs, vs in SECS:
        if va <= v < va + vs: return n
def cstr(v, n=64):
    o = va2off(v)
    if o is None: return None
    e = D.find(b'\0', o, o + n); t = D[o:e]
    return t.decode('latin-1') if t and all(32 <= c < 127 or c in (9, 10) for c in t) else None
def u32(v): return struct.unpack_from('<I', D, va2off(v))[0]
