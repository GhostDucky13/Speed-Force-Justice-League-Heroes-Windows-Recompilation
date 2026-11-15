#!/usr/bin/env python3
"""
patch_menus.py - Xbox menu patches for Justice League Heroes.

  stats.lmp    (Hero menu / shield shop): show the last two shop items,
               Supergirl (item 22) and Black Canary (item 23), 95 shields each.
               The Xbox shop already has all 23 prices and the game already
               unlocks items 22/23, but on non-PSP platforms the menu hides them
               (maxscroll = numBuyItems - 2, a 'nonpsp' cover, row 22 blanked).
               Fix: the four `platform == 3` checks take the PSP branch
               (`equals; not; if` -> `equals; toInteger; if`).

  frontend.lmp (main menu): Challenge Missions always selectable. The menu skips
               item 3 while gameWon == 0; the check `i == 3` is changed to
               `i == 9` (no such item). Continued Play keeps its normal rule.
               Difficulty screen: always 5 items, Elite and Superhero not greyed
               (nItems 3 -> 5, and the two `gameWon == 0` grey checks compare to 9).

Usage:
  python patch_menus.py stats    stats.lmp    stats_patched.lmp
  python patch_menus.py frontend frontend.lmp frontend_patched.lmp
  python patch_menus.py frontend_diff frontend.lmp frontend_patched.lmp   (difficulties only)
  python patch_menus.py frontend_challenge frontend.lmp frontend_patched.lmp (difficulties + Challenge Missions item)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp  # noqa: E402
import swb  # noqa: E402

PATCHES = {
    'stats': dict(
        member='stats.swb', size=752307,
        # offsets of `not` (0x12) that follow `push '/:platform'; getVariable; push '3'; equals`
        force_psp=[0x006933, 0x008EA5, 0x0B4826, 0x0B66DA],
        string_edits=[],
    ),
    'frontend': dict(
        member='frontend.swb', size=468470,
        force_psp=[],
        # (offset of the push action, old string, new string) - same length
        string_edits=[(0x000532, '3', '9'),      # Challenge Missions: never skipped
                      (0x050E8C, '3', '5'),      # Difficulty: always 5 items (Elite, Superhero)
                      (0x050D2F, '0', '9'),      # Difficulty: don't grey out Elite
                      (0x050D87, '0', '9')],     # Difficulty: don't grey out Superhero
    ),
}
# Difficulty unlock only (safe before the challenge levels are installed)
PATCHES['frontend_diff'] = dict(PATCHES['frontend'], string_edits=PATCHES['frontend']['string_edits'][1:])


def _push(*strs):
    """One Push action per value: the Xbox Flash player reads only the first value of a
    multi-value Push (the original menus never use them)."""
    out = b''
    for x in strs:
        body = b'\0' + x.encode('latin-1') + b'\0'
        out += b'\x96' + struct.pack('<H', len(body)) + body
    return out


def _set_target(t):
    b = t.encode('latin-1') + b'\0'
    return b'\x8b' + struct.pack('<H', len(b)) + b


def _uistring(target, var, key):
    """setTarget target; trace "CMD_UISTRING,var,key"; - the XBE sets the text (as on the Difficulty screen)."""
    return _set_target(target) + _push(f'CMD_UISTRING,{var},{key}') + b'\x26'


def _pad(code, size):
    """Pad with a dummy one-value push (left on the stack). Never pad with End (0x00) bytes:
    the Xbox Flash player stops at an End byte even if a jump skips over it."""
    p = size - len(code)
    if p == 0:
        return code
    if p < 5:
        raise ValueError(f'cannot pad {p} bytes')
    return code + _push('x' * (p - 5))


def challenge_menu_edits():
    """Xbox main menu has 6 items (New Game, Continued Play, Load, Options, Extras, Credits);
    the PSP's Challenge Missions item is missing, although the missions screen, the
    players screen (bChallenge -> CMD_START_CHALLENGE) and an unused 7th slot (menu6) exist."""
    edits = []
    # 1. main-menu init (frame 15): `if (platform == 3) nItems = 7 else nItems = 6` (68 bytes)
    #    -> nItems = 7 ; menu6 text = gs53 "Challenge Missions"
    c = _push('nItems', '7') + b'\x1d' + _uistring('FrontEnd/menu6', 'text', 'gs53') + _set_target('')
    old = bytes.fromhex('960a0000706c6174666f726d001c9603000033000e129d02001700960800006e4974656d7300'
                        '9603000037001d9902001200960800006e4974656d73009603000036001d')
    edits.append((279422, old, _pad(c, len(old))))
    # 2. main-menu select, last item (empty Xbox branch, 33 bytes) -> bChallenge = 1, go to 'missions'
    c = _push('bChallenge', '1') + b'\x1d' + b'\x81\x02\x00' + struct.pack('<H', 203) + b'\x06'
    old = bytes.fromhex('960a0000706c6174666f726d001c9603000033000e129d02000600810200b90006')
    edits.append((282629, old, _pad(c, len(old))))
    # 3. missions screen (0x6F202):
    #    a) feVar = prev5 -> feVar = 0 (the selector-position line is dropped below)
    old = _push('feVar', 'prev5') + b'\x1c\x1d'
    edits.append((455194, old, _pad(_push('feVar', '0') + b'\x1d', len(old))))
    #    b) Header/Selector/`m<i>/:text = /:mission<i>name` (200 bytes; "~~U:" keys don't render
    #       on Xbox) -> CMD_UISTRING per mission. The block sets target '' right after.
    old = (_push('Header', 'gs53') + b'\x1d' + _push('Selector') +
           b'\x96\x05\x00\x01\x00\x00\x80\x3f' + _push('/:feVar') + b'\x1c' +
           b'\x96\x04\x00\x00\x32\x36\x00' + b'\x0c\x23' +
           b''.join(_push(f'm{i}/:text', f'/:mission{i}name') + b'\x1c\x1d' for i in range(4)))
    c = b''.join(_uistring(f'Missions/m{i}', 'text', f'ebonus{i + 1}') for i in range(4))
    edits.append((455261, old, _pad(c, len(old))))
    # 4. players screen (button113 0xc200): the Xbox XBE has no START_CHALLENGE command.
    #    "CMD_START_CHALLENGE,<players>,<map>" -> "CMD_WARP2LEVEL,<map>" (debug command: start
    #    request with level row <map>; 0x1495cf -> 0x45550 -> 0x454d5 copies the row's name into
    #    the next-level buffer). No START_GAME: its new-game init would reset the loaded profile.
    old = (_push('CMD_START_CHALLENGE,', 'numPlayers') + b'\x1c\x21' + _push(',') + b'\x21' +
           _push('map') + b'\x1c\x21\x26')
    c = _push('CMD_WARP2LEVEL,', 'map') + b'\x1c\x21\x26'
    edits.append((329580, old, _pad(c, len(old))))
    return edits


PATCHES['frontend_challenge'] = dict(PATCHES['frontend_diff'], raw_edits=challenge_menu_edits())


def apply(kind, data):
    p = PATCHES[kind]
    if len(data) != p['size'] or data[:3] != b'FWS':
        raise ValueError(f'not the Xbox {p["member"]} this patch was made for')
    d = bytearray(data)
    for off in p['force_psp']:
        # verify context: ... push '3' (96 03 00 00 33 00) equals (0E) not (12) if (9D)
        if bytes(d[off - 7:off + 2]) != bytes.fromhex('9603000033000e129d'):
            raise ValueError(f'unexpected bytes before {off:#x}: {d[off-7:off+2].hex()}')
        d[off] = 0x18
    for off, old, new in p['string_edits']:
        ins = next(swb.disasm(bytes(d), off, off + 64))
        if ins[1] != 'push' or ins[2][0][1] != old or len(old) != len(new):
            raise ValueError(f'unexpected push at {off:#x}: {ins}')
        so = ins[2][0][2]       # offset of the string bytes (after the type byte)
        d[so:so + len(new)] = new.encode('latin-1')
    for off, old, new in p.get('raw_edits', []):
        if bytes(d[off:off + len(old)]) != old or len(old) != len(new):
            raise ValueError(f'unexpected bytes at {off:#x}')
        d[off:off + len(new)] = new
    return bytes(d)


def main():
    kind, src, dst = sys.argv[1:4]
    entries = lmp.read(src)
    names = [n.lower() for n, _, _ in entries]
    if names != [PATCHES[kind]['member']]:
        sys.exit(f'expected an archive containing only {PATCHES[kind]["member"]}')
    lmp.build([(entries[0][0], apply(kind, entries[0][1]))], dst)
    print(f'{kind}: patched -> {dst}')


if __name__ == '__main__':
    main()
