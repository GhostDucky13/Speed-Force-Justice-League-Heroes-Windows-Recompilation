#!/usr/bin/env python3
"""
swb.py - Inspect Justice League Heroes .swb menu files (uncompressed Flash SWF, version 4).

  python swb.py tags  file.swb          list tags (including inside sprites)
  python swb.py asm   file.swb [-o out] disassemble every DoAction / button action block

Exposes parse_tags(), actions(), disasm() for patch scripts.
"""
import struct
import sys

TAGS = {0: 'End', 1: 'ShowFrame', 2: 'DefineShape', 4: 'PlaceObject', 5: 'RemoveObject',
        6: 'DefineBits', 7: 'DefineButton', 8: 'JPEGTables', 9: 'SetBackgroundColor',
        10: 'DefineFont', 11: 'DefineText', 12: 'DoAction', 13: 'DefineFontInfo',
        14: 'DefineSound', 15: 'StartSound', 17: 'DefineButtonSound', 18: 'SoundStreamHead',
        19: 'SoundStreamBlock', 20: 'DefineBitsLossless', 21: 'DefineBitsJPEG2', 22: 'DefineShape2',
        24: 'Protect', 26: 'PlaceObject2', 28: 'RemoveObject2', 32: 'DefineShape3',
        33: 'DefineText2', 34: 'DefineButton2', 35: 'DefineBitsJPEG3', 36: 'DefineBitsLossless2',
        37: 'DefineEditText', 39: 'DefineSprite', 43: 'FrameLabel', 45: 'SoundStreamHead2',
        46: 'DefineMorphShape', 48: 'DefineFont2'}

OPS = {0x04: 'nextFrame', 0x05: 'prevFrame', 0x06: 'play', 0x07: 'stop', 0x08: 'toggleQuality',
       0x09: 'stopSounds', 0x0A: 'add', 0x0B: 'subtract', 0x0C: 'multiply', 0x0D: 'divide',
       0x0E: 'equals', 0x0F: 'less', 0x10: 'and', 0x11: 'or', 0x12: 'not', 0x13: 'stringEquals',
       0x14: 'stringLength', 0x15: 'stringExtract', 0x17: 'pop', 0x18: 'toInteger',
       0x1C: 'getVariable', 0x1D: 'setVariable', 0x20: 'setTarget2', 0x21: 'stringAdd',
       0x22: 'getProperty', 0x23: 'setProperty', 0x24: 'cloneSprite', 0x25: 'removeSprite',
       0x26: 'trace', 0x27: 'startDrag', 0x28: 'endDrag', 0x29: 'stringLess', 0x30: 'randomNumber',
       0x31: 'mbStringLength', 0x32: 'charToAscii', 0x33: 'asciiToChar', 0x34: 'getTime',
       0x35: 'mbStringExtract', 0x36: 'mbCharToAscii', 0x37: 'mbAsciiToChar',
       0x81: 'gotoFrame', 0x83: 'getURL', 0x88: 'constantPool', 0x8A: 'waitForFrame',
       0x8B: 'setTarget', 0x8C: 'gotoLabel', 0x8D: 'waitForFrame2', 0x96: 'push', 0x99: 'jump',
       0x9A: 'getURL2', 0x9D: 'if', 0x9E: 'call', 0x9F: 'gotoFrame2'}


def _tag_header(d, o):
    code_len = struct.unpack_from('<H', d, o)[0]
    code, ln, hdr = code_len >> 6, code_len & 0x3F, 2
    if ln == 0x3F:
        ln = struct.unpack_from('<I', d, o + 2)[0]
        hdr = 6
    return code, ln, hdr


def header_end(d):
    nbits = d[8] >> 3
    rect_bytes = (5 + 4 * nbits + 7) // 8
    return 8 + rect_bytes + 4


def parse_tags(d, start=None, end=None, depth=0, path=''):
    """Yield (offset_of_tag, code, body_offset, body_len, depth, sprite_path)."""
    o = header_end(d) if start is None else start
    end = len(d) if end is None else end
    while o < end:
        code, ln, hdr = _tag_header(d, o)
        body = o + hdr
        yield o, code, body, ln, depth, path
        if code == 39:  # DefineSprite: id, frame count, then nested tags
            sid = struct.unpack_from('<H', d, body)[0]
            yield from parse_tags(d, body + 4, body + ln, depth + 1, f'{path}/sprite{sid}')
        if code == 0 and depth > 0:
            break
        o = body + ln


def action_blocks(d):
    """Yield (label, start, end) for every action byte-code block."""
    for o, code, body, ln, depth, path in parse_tags(d):
        if code == 12:
            yield f'{path or "/"} DoAction@{o:#x}', body, body + ln
        elif code == 34:  # DefineButton2: id, flags, action offset
            bid = struct.unpack_from('<H', d, body)[0]
            aoff = struct.unpack_from('<H', d, body + 3)[0]
            if aoff == 0:
                continue
            p = body + 3 + aoff
            while p < body + ln:
                nxt, cond = struct.unpack_from('<HH', d, p)
                s = p + 4
                e = p + nxt if nxt else body + ln
                yield f'{path or "/"} button{bid} cond {cond:#06x}', s, e
                if not nxt:
                    break
                p += nxt


def push_values(d, s, ln):
    out, p = [], s
    while p < s + ln:
        t = d[p]; p += 1
        if t == 0:
            e = d.index(b'\0', p); out.append(('str', d[p:e].decode('latin-1'), p)); p = e + 1
        elif t == 1:
            out.append(('float', struct.unpack_from('<f', d, p)[0], p)); p += 4
        elif t == 2:
            out.append(('null', None, p))
        elif t == 3:
            out.append(('undef', None, p))
        elif t == 4:
            out.append(('reg', d[p], p)); p += 1
        elif t == 5:
            out.append(('bool', d[p], p)); p += 1
        elif t == 6:
            hi, lo = struct.unpack_from('<II', d, p)
            out.append(('double', struct.unpack('<d', struct.pack('<II', lo, hi))[0], p)); p += 8
        elif t == 7:
            out.append(('int', struct.unpack_from('<i', d, p)[0], p)); p += 4
        elif t == 8:
            out.append(('const', d[p], p)); p += 1
        elif t == 9:
            out.append(('const', struct.unpack_from('<H', d, p)[0], p)); p += 2
        else:
            out.append(('?', t, p)); break
    return out


def disasm(d, s, e):
    """Yield (offset, opname, args)."""
    p = s
    while p < e:
        op = d[p]
        if op == 0:
            yield p, 'end', None
            return
        if op >= 0x80:
            ln = struct.unpack_from('<H', d, p + 1)[0]
            a = p + 3
            if op == 0x96:
                args = push_values(d, a, ln)
            elif op in (0x99, 0x9D):
                args = struct.unpack_from('<h', d, a)[0] + a + 2
            elif op == 0x8C:
                args = d[a:a + ln - 1].decode('latin-1')
            elif op == 0x83:
                args = d[a:a + ln].split(b'\0')[:2]
            elif op == 0x81:
                args = struct.unpack_from('<H', d, a)[0]
            else:
                args = d[a:a + ln].hex()
            yield p, OPS.get(op, f'op{op:02x}'), args
            p = a + ln
        else:
            yield p, OPS.get(op, f'op{op:02x}'), None
            p += 1


def fmt(args):
    if isinstance(args, list):
        return ', '.join(repr(v) if k == 'str' else f'{v}' for k, v, _ in args)
    if isinstance(args, int):
        return f'-> {args:#x}'
    return '' if args is None else str(args)


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    d = open(path, 'rb').read()
    out = open(sys.argv[4], 'w') if len(sys.argv) > 4 and sys.argv[3] == '-o' else sys.stdout
    if cmd == 'tags':
        for o, code, body, ln, depth, sp in parse_tags(d):
            print(f'{o:08x} {"  " * depth}{TAGS.get(code, code)} len={ln} {sp}', file=out)
    elif cmd == 'asm':
        for label, s, e in action_blocks(d):
            print(f'\n=== {label}', file=out)
            for p, name, args in disasm(d, s, e):
                print(f'  {p:08x} {name} {fmt(args)}', file=out)


if __name__ == '__main__':
    main()
