"""objects.ob: u32 count, u32 string-table offset, then records
{u32 type str, u16 size, u16 flags, f32 x, y, z, u32 rot?, u32 prop str offsets...}."""
import struct


def parse(d):
    n, st = struct.unpack_from('<II', d, 0)
    S = d[st:]
    s = lambda o: S[o:S.index(b'\0', o)].decode('latin-1')
    o, out = 8, []
    for i in range(n):
        t, size, fl = struct.unpack_from('<IHH', d, o)
        x, y, z, r = struct.unpack_from('<3fI', d, o + 8)
        props = [s(v) for v in struct.unpack_from(f'<{(size - 24) // 4}I', d, o + 24)]
        out.append(dict(i=i, off=o, type=s(t), size=size, flags=fl, pos=(x, y, z), rot=r, props=props))
        o += size
    return out
