#!/usr/bin/env python3
"""
patch_charsel.py - Turn on the 15-portrait character select grid in the Xbox
char_sel.lmp (Justice League Heroes), so Supergirl and Black Canary get slots.

The Xbox menu (char_sel.swb, Flash 4) already contains the PSP's 15-portrait grid
(portraits p13/p14, 5x3 layout, GetRow*PSP navigation), gated by `platform == 3`
(PSP; Xbox reports "1"). This patch:
  1. Player 1: forces the four layout checks (maxPortraits, GetRow, GetRowAbove,
     GetRowBelow) to the 15-portrait branch, by turning `equals; not; if` into
     `equals; toInteger; if`. Button-icon checks are untouched, so prompts stay Xbox.
  2. Player 2 (2-player mode): only had the 13-portrait row tables. Its GetRow,
     GetRowAbove, GetRowBelow blocks are overwritten in place with the PSP grid code
     (player-1 variable names renamed to player 2), padded with End actions.
No sizes change, so no SWF/LMP offsets need fixing.

Usage: python patch_charsel.py char_sel.lmp char_sel_patched.lmp
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp  # noqa: E402
import swb  # noqa: E402

EXPECTED_SWB_SHA1 = None   # filled at first verified run; checked by structure below

# 1. byte offsets in char_sel.swb of the `not` (0x12) after `equals` in each platform==3 check
P1_CHECKS = [0x0001E9, 0x0BC361, 0x0BC575, 0x0BC999]

# 2. (source PSP block, destination player-2 block) DoAction tag offsets
#    labels: GetRowPSP/GetRowAbovePSP/GetRowBelowPSP (sprite295) -> GetRow/GetRowAbove/GetRowBelow (sprite346)
BLOCKS = [(0x0BCD9B, 0x0CAC9D, 'GetRow'),
          (0x0BCE51, 0x0CAE7C, 'GetRowAbove'),
          (0x0BCF66, 0x0CB266, 'GetRowBelow')]

RENAME = {'/:row0': '/:row1', '/:minRow0': '/:minRow1', '/:maxRow0': '/:maxRow1',
          '/:curPortrait0': '/:curPortrait1', 'temp0': 'temp1', 'target0': 'target1',
          'GetRowPSP': 'GetRow'}


# 3. Costume cycle (X button, player 1 button288 / player 2 button345): nextCostume wraps to 0
#    when it is not < 3. Superman and Wonder Woman have a 4th costume (portrait frame 4 exists:
#    Superman's third alternate, Wonder Woman's armour), so the limit becomes 4. Heroes without
#    a 4th costume skip it (CMD_IS_COSTUME_AVAIL is false). Offsets of the '3' in push '3'.
COSTUME_LIMITS = [758793, 759060, 825444, 825711]


def block(d, tag_off):
    """(code start, code end) of the DoAction tag at tag_off."""
    for label, s, e in swb.action_blocks(d):
        if label.endswith(f'DoAction@{tag_off:#x}'):
            return s, e
    raise ValueError(f'no DoAction tag at {tag_off:#x}')


def encode_push(vals):
    out = bytearray()
    for kind, v, _ in vals:
        if kind == 'str':
            out += b'\x00' + v.encode('latin-1') + b'\x00'
        elif kind == 'float':
            out += b'\x01' + struct.pack('<f', v)
        elif kind == 'int':
            out += b'\x07' + struct.pack('<i', v)
        elif kind == 'bool':
            out += b'\x05' + bytes([v])
        else:
            raise NotImplementedError(kind)
    return b'\x96' + struct.pack('<H', len(out)) + bytes(out)


def reassemble(d, s, e, rename):
    """Re-emit an action block with string renames, fixing forward/back branch targets."""
    ins = list(swb.disasm(d, s, e))
    pieces, old_off = [], []
    for p, name, args in ins:
        old_off.append(p)
        if name == 'push':
            vals = [(k, rename.get(v, v) if k == 'str' else v, q) for k, v, q in args]
            pieces.append(['raw', encode_push(vals)])
        elif name in ('if', 'jump'):
            pieces.append(['br', d[p], args])
        elif name == 'end':
            pieces.append(['raw', b'\x00'])
        else:
            op = d[p]
            ln = 3 + struct.unpack_from('<H', d, p + 1)[0] if op >= 0x80 else 1
            pieces.append(['raw', d[p:p + ln]])
    # layout
    new_off, pos = {}, 0
    for (p, _, _), pc in zip(ins, pieces):
        new_off[p] = pos
        pos += len(pc[1]) if pc[0] == 'raw' else 5
    new_off[e] = pos
    out = bytearray()
    for pc in pieces:
        if pc[0] == 'raw':
            out += pc[1]
        else:
            tgt = pc[2]
            if tgt not in new_off:
                # target = end of block (offset of trailing End or block end)
                tgt = max(k for k in new_off if k <= tgt)
            rel = new_off[tgt] - (len(out) + 5)
            out += bytes([pc[1]]) + struct.pack('<Hh', 2, rel)
    return bytes(out)


def patch_swb(d):
    d = bytearray(d)
    for off in P1_CHECKS:
        if d[off - 1] != 0x0E or d[off] != 0x12 or d[off + 1] != 0x9D:
            raise ValueError(f'unexpected bytes at {off:#x}: {d[off-1:off+2].hex()}')
        d[off] = 0x18   # toInteger
    for src, dst, name in BLOCKS:
        ss, se = block(bytes(d), src)
        code = reassemble(bytes(d), ss, se, RENAME)
        ds, de = block(bytes(d), dst)
        room = de - ds
        if len(code) > room:
            raise ValueError(f'{name}: new code {len(code)} > room {room}')
        d[ds:de] = code + b'\x00' * (room - len(code))
    for off in COSTUME_LIMITS:
        if d[off - 4:off + 2] != b'\x96\x03\x00\x003\x00':
            raise ValueError(f'unexpected costume limit bytes at {off}: {d[off-4:off+2].hex()}')
        d[off] = ord('4')
    return bytes(d)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    entries = lmp.read(src)
    if [n.lower() for n, _, _ in entries] != ['char_sel.swb']:
        sys.exit('expected an archive containing only char_sel.swb')
    data = entries[0][1]
    if data[:3] != b'FWS' or struct.unpack_from('<I', data, 4)[0] != len(data) or len(data) != 835187:
        sys.exit('this is not the Xbox char_sel.swb this patch was made for')
    out = patch_swb(data)
    lmp.build([(entries[0][0], out)], dst)
    print(f'patched -> {dst}  (sha1 {hashlib.sha1(out).hexdigest()[:12]})')


if __name__ == '__main__':
    main()
