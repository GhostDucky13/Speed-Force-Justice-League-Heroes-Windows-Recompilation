#!/usr/bin/env python3
"""
patch_unlock.py - Patch Justice League Heroes (Xbox, NTSC/PAL "WR-001" v1) so that
Supergirl and Black Canary start unlocked on a new game.

Background (see FINDINGS.md): the Xbox build already contains both characters as
IDs 13 and 14. The new-game routine at 0x000713D7 sets every character's lock flag
to (id > 6), so IDs 7-14 start locked and the Xbox game never unlocks 13 and 14.

Modes:
  --mode standard (default)  nobody unlocked: the original new-game locks; Supergirl and
                         Black Canary are bought in the shop (items 22/23, stats.lmp patch).
                         All other logic of this file is included.
  --mode sgbc            lock = (7 <= id <= 12): Supergirl + Black Canary unlocked,
                         the normal unlockables (GL Kyle/Hal, Green Arrow, Aquaman,
                         Hawkgirl, Huntress) stay locked as usual.
  --mode all             every character unlocked (1-byte change).

The sgbc mode needs 5 more bytes than the original code, so it jumps out to two
int3 alignment-padding gaps (unreachable bytes after a ret) and back.
The .text section SHA-1 digest in the XBE header is updated. The RSA header signature
is not (not possible); xemu and modded consoles do not check it.

Only works on an unmodified default.xbe with SHA-1 264550fa8337b43f14a630120be854d2f32bb6a9.
Also clears the Supergirl/Black Canary lock flags whenever a save is loaded, so existing
profiles work too.

Also: main menu gets a 7th name (gs53 Challenge Missions) for the item added by frontend.lmp.

Usage: python patch_unlock.py default.xbe default_patched.xbe [--mode standard|sgbc|all]
"""
import argparse
import hashlib
import struct
import sys

EXPECTED_SHA1 = '264550fa8337b43f14a630120be854d2f32bb6a9'
SITE = 0x000713D7          # cmp [ebp-4],6 / mov [eax-1],0x10 / setg cl / mov [eax-2],cl (14 bytes)
SITE_ORIG = bytes.fromhex('837dfc06c640ff100f9fc18848fe')
SITE_RETURN = 0x000713E5
CAVE1, CAVE2 = 0x001602B1, 0x00160761   # 15-byte int3 padding runs, each after a ret


def rel32(frm, to, length=5):
    return struct.pack('<i', to - (frm + length))


def build_sgbc():
    # site: jmp CAVE1 ; nop x9
    site = b'\xE9' + rel32(SITE, CAVE1) + b'\x90' * 9
    # cave1: mov byte [eax-1],0x10 ; mov ecx,[ebp-4] ; sub ecx,7 ; jmp CAVE2
    c1 = bytes.fromhex('c640ff10') + bytes.fromhex('8b4dfc') + bytes.fromhex('83e907')
    c1 += b'\xE9' + rel32(CAVE1 + len(c1), CAVE2)
    # cave2: cmp ecx,6 ; setb cl ; mov [eax-2],cl ; jmp SITE_RETURN
    c2 = bytes.fromhex('83f906') + bytes.fromhex('0f92c1') + bytes.fromhex('8848fe')
    c2 += b'\xE9' + rel32(CAVE2 + len(c2), SITE_RETURN)
    assert len(site) == 14 and len(c1) <= 15 and len(c2) <= 15
    return [(SITE, SITE_ORIG, site), (CAVE1, b'\xCC' * len(c1), c1), (CAVE2, b'\xCC' * len(c2), c2)]


# Startup preload loop (0x1B6EB) loads character archives for IDs 0-12 only:
# cmp esi,0xD at 0x1B75D. Raise to 15 so supergrl.lmp / bcanary.lmp are loaded too.
# Their slots in the handle list (0x2ADCD4, 0x2ADCD8) are otherwise unused.
PRELOAD = (0x0001B75D, bytes.fromhex('83fe0d'), bytes.fromhex('83fe0f'))


# Save-data load (0x71472) copies the 15-character table (0x708 bytes) from the save
# over the live table, so an existing profile keeps Supergirl/Black Canary locked.
# After the copy, clear their lock bytes: [0x1DF638 + 13*0x78] and [0x1DF638 + 14*0x78].
LOAD_SITE = 0x0007149B          # add esp,0x18 ; mov eax,esi  (5 bytes) -> jmp CAVE3
LOAD_ORIG = bytes.fromhex('83c4188bc6')
LOAD_RETURN = 0x000714A0
CAVE3, CAVE4 = 0x00160801, 0x00161472   # 15- and 14-byte int3 padding runs after a ret
LOCK13, LOCK14 = 0x001DF638 + 13 * 0x78, 0x001DF638 + 14 * 0x78


def build_loadfix(clear_locks=True):
    site = b'\xE9' + rel32(LOAD_SITE, CAVE3)
    if not clear_locks:          # standard: only the Continued Play hook (LH)
        c3 = bytes.fromhex('83c418') + b'\xE9' + rel32(CAVE3 + 3, HDR_LABELS['LH'])
        return [(LOAD_SITE, LOAD_ORIG, site), (CAVE3, b'\xCC' * len(c3), c3)]
    c3 = bytes.fromhex('83c418') + b'\xC6\x05' + struct.pack('<I', LOCK13) + b'\x00'
    c3 += b'\xE9' + rel32(CAVE3 + len(c3), CAVE4)
    c4 = b'\xC6\x05' + struct.pack('<I', LOCK14) + b'\x00'
    c4 += b'\xE9' + rel32(CAVE4 + len(c4), HDR_LABELS['LH'])     # LH: Continued Play grant, mov eax,esi
    assert len(site) == 5 and len(c3) <= 15 and len(c4) <= 14
    return [(LOAD_SITE, LOAD_ORIG, site), (CAVE3, b'\xCC' * len(c3), c3), (CAVE4, b'\xCC' * len(c4), c4)]


# Main menu names (FRONTEND handler 0x14eb12): the loop fills menu0..menu5 from a 6-entry
# table on the stack (gs50 gs51 gs52 gs54 gs62 gs55). The Challenge Missions item added in
# frontend.lmp is menu6, so the loop runs to 7 and index 6 gets "gs53" ("Challenge Missions").
MENU_SITE = 0x0014EBA5            # push esi ; push [esp+ebp*4+0x20]  (5 bytes)
MENU_ORIG = bytes.fromhex('56ff74ac20')
MENU_RET = 0x0014EBAA
MENU_LOOP = (0x0014EBBB, bytes.fromhex('83fd06'), bytes.fromhex('83fd07'))
CAVE5, CAVE6, CAVE7 = 0x001616E1, 0x00161811, 0x00162CA1   # 15-byte int3 runs after a ret/jmp


def build_menu7():
    """NOT USED: froze the game at the title screen (index 6 overruns something in the XBE)."""
    site = b'\xE9' + rel32(MENU_SITE, CAVE5)
    # cave5: push esi ; cmp ebp,6 ; jne cave6 ; jmp cave7
    c5 = b'\x56' + bytes.fromhex('83fd06') + b'\x0f\x85' + rel32(CAVE5 + 4, CAVE6, 6)
    c5 += b'\xE9' + rel32(CAVE5 + len(c5), CAVE7)
    # cave6: push [esp+ebp*4+0x20] ; jmp back
    c6 = bytes.fromhex('ff74ac20') + b'\xE9' + rel32(CAVE6 + 4, MENU_RET)
    # cave7: push offset "gs53" ; jmp back ; "gs53\0"
    s_addr = CAVE7 + 10
    c7 = b'\x68' + struct.pack('<I', s_addr) + b'\xE9' + rel32(CAVE7 + 5, MENU_RET) + b'gs53\0'
    assert len(c5) <= 15 and len(c6) <= 15 and len(c7) <= 15
    return [(MENU_SITE, MENU_ORIG, site), MENU_LOOP,
            (CAVE5, b'\xCC' * len(c5), c5), (CAVE6, b'\xCC' * len(c6), c6), (CAVE7, b'\xCC' * len(c7), c7)]


# Max every hero whenever a level is started through WARP2LEVEL (used by the frontend for
# Challenge Missions and Chapter Select). For hero 0..14:
#   unlock (record +0 = 0), 0x70c94(hero, 5) = all 9 power/stat slots rank 5 (the cap used by
#   USE_CREDIT 0x7211e), 0x71310(hero, 20) = level 20 with its XP and points.
# Hook: the WARP2LEVEL handler's `call 0x14903d` (0x14CA47) -> W: call MAXHEROES; jmp 0x14903d.
WARP_CALL = 0x0014CA47
WARP_ORIG = b'\xE8' + struct.pack('<i', 0x0014903D - (0x0014CA47 + 5))
START_REQ = 0x0014903D
F_SLOTS, F_LEVEL = 0x00070C94, 0x00071310
CW, CA, CB, CE, CC, CD = 0x00076DD3, 0x001604A4, 0x0015D0D3, 0x00161811, 0x00163F23, 0x001616E1
CAVE_SIZES = {0x001604A4: 12, 0x0015D0D3: 13, 0x00161811: 15, 0x00163F23: 13, 0x001616E1: 15}


def build_maxheroes():
    """Hero-maxing loop A..D in int3 caves; the WARP2LEVEL call now goes to W2 (header code)."""
    jmp = lambda frm, to: b'\xE9' + rel32(frm, to)
    call = lambda frm, to: b'\xE8' + rel32(frm, to)
    a = b'\x53' + b'\x33\xdb' + jmp(CA + 3, CB)                                  # push ebx; xor ebx,ebx
    b = b'\x6a\x05' + b'\x53' + call(CB + 3, F_SLOTS) + jmp(CB + 8, CE)          # 0x70c94(ebx, 5)
    e = bytes.fromhex('6bc378') + b'\xc6\x80' + struct.pack('<I', 0x1DF638) + b'\x00' + jmp(CE + 10, CC)  # unlock
    c = b'\x6a\x14' + b'\x53' + call(CC + 3, F_LEVEL) + jmp(CC + 8, CD)          # 0x71310(ebx, 20)
    d = bytes.fromhex('83c410') + b'\x43' + bytes.fromhex('83fb0f') + b'\x0f\x8c' + rel32(CD + 7, CB, 6) + b'\x5b\xc3'
    out = [(WARP_CALL, WARP_ORIG, call(WARP_CALL, HDR_LABELS['W2']))]
    for va, code in ((CA, a), (CB, b), (CE, e), (CC, c), (CD, d)):
        assert len(code) <= CAVE_SIZES[va], (hex(va), len(code))
        out.append((va, b'\xCC' * len(code), code))
    return out


# ------------------------------------------------------------------ header code (update 10)
# The XBE headers end at 0xDF0 but the file is zero up to 0x1000 (.text starts there), and the
# loader maps the headers at the base address 0x10000. SizeOfHeaders is raised to 0x1000 so
# 0x10E00-0x10FFF holds new code.
#
# Hero record +1 (0x1DF639 + id*0x78): low nibble = worn costume, bit 4 = set by New Game for
# every hero (0x713DB) and otherwise never read, bits 5/6/7 = alternate costumes 1/2/3 owned.
#   * Story flag = bit 4 of Superman's byte. New Game (and the boot reset) set it; it is saved
#     with the profile, so loading a New Game save keeps story rules.
#   * GRANT: every hero -> (worn) | 0x60, Superman / Wonder Woman also 0x80 (their 4th costume:
#     Superman's third alternate supr_kdr, Wonder Woman's armour wwo_armd). Clears bit 4.
#     Called by WARP2LEVEL (Chapter Select, Challenge Missions) and after a Continued Play load
#     (CMD_LOAD_REPLAY sets 0x46BC52 = 1; CMD_LOAD_GAME clears it).
#   * BUYALL (update 12): every unbought shop item is bought through the game's own routine
#     (costumes + hero unlocks). Before GRANT/maxing (a hero unlock sets level 5).
#   * New Game starts with request 0 (row 0 = e1l1a) instead of -1, Continued Play likewise
#     (CPS), so the first level's character select is set up like any other level change
#     (with -1 the greyed-out list was never built: stale list from the previous select).
#   * RST: Restart Episode in a challenge (current level "ebon...") reloads that level; the
#     episode snapshot it would restore is only taken for e<N>l<M> levels (crash before).
#   * SEL: the level-start code reads the greyed-out list from column "charExclude"
#     (0x46EEC mov ebx,"charExclude"); with the story flag set it reads "charExclNew" instead.
#   * WWA: Wonder Woman's model/HUD/status files: worn costume 3 -> the armour set (the game's
#     own Episode 11 path at 0x7C6B2), otherwise the original check.
#   * NOAS (2.1.1): no autosave in Challenge Missions. A level change stores its autosave request
#     in 0x46A3A8 (0x148E74, from 0x148E2D's third argument); at the next level start 0x148EEC
#     saves to the current slot, and the pause menu's init (CMD_AUTOSAVE_STATUS) opens its
#     auto-save screen, which asks for a slot when none is set. A challenge is played with
#     whatever slot was current (the story save loaded earlier, or none, so the player was asked
#     and picked one), so finishing a challenge overwrote a story save with it. While the
#     current or the next level is a challenge ("ebon..."), the request is stored as 0.
HDR = 0x00010E00
SOH_FIELD, SOH_ORIG, SOH_NEW = 0x108, 0xDF0, 0x1000
REC1 = 0x001DF639
REPLAY_FLAG = 0x0046BC52
COL_EXCLUDE = 0x001B8B54
SEL_SITE, SEL_ORIG = 0x00046EEC, bytes.fromhex('bb548b1b00')
WW_SITE, WW_ORIG = 0x0007C692, bytes.fromhex('68da442c00')
WW_ARMOUR, WW_ARMOUR_MODEL, WW_CONT = 0x0007C6B2, 0x001B4AB8, 0x0007C697
NG_COLUMN = b'charExclNew'
# update 13: in story mode (New Game save) the level table's select / team columns are read
# from story copies, so the fixed story pairs come from Player1/Player2 again (no select).
COL_CHARSEL, COL_TEAMID = 0x001B8B7C, 0x001BD030
CS_SITE1, CS_ORIG1 = 0x00046E27, bytes.fromhex('bb7c8b1b00')     # level change: select screen?
CS_SITE2, CS_ORIG2 = 0x0007F76F, bytes.fromhex('687c8b1b00')     # level start: team source
TID_SITE, TID_ORIG = 0x0007F831, bytes.fromhex('bb30d01b00')
# update 12
SHOP, SHOP_BUY = 0x00437358, 0x0007CC2F      # 23 bought flags (item 1..23); buy(item, 1) applies it
CUR_LEVEL, NEXT_LEVEL, STRCPY = 0x002C44D9, 0x002C44D0, 0x00161EB0
RESTART_EP = 0x00067FCE                      # restores the episode-start snapshot, next = e<N>l1
RST_SITE, RST_ORIG = 0x00148FB3, b'\xE9' + struct.pack('<i', 0x00067FCE - (0x00148FB3 + 5))
CPS_SITE, CPS_ORIG = 0x00149AF4, bytes.fromhex('6aff') + b'\xE8' + struct.pack('<i', 0x0014903D - (0x00149AF6 + 5)) + b'\x59\xc3'
NEWGAME_ROW = (0x001504B6, bytes.fromhex('6aff'), bytes.fromhex('6a00'))
# 2.1.1
AUTOSAVE_REQ = 0x0046A3A8
NOAS_SITE, NOAS_ORIG = 0x00148E74, bytes.fromhex('a3a8a34600')   # mov [0x46A3A8],eax


def _assemble(base, items):
    """items: bytes | ('label', n) | ('call'|'jmp', target) | ('abs', label) (u32 address of label)."""
    labels, pos = {}, base
    for it in items:
        if isinstance(it, bytes):
            pos += len(it)
        elif it[0] == 'label':
            labels[it[1]] = pos
        else:
            pos += 5 if it[0] in ('call', 'jmp') else 4      # 'abs' / 'rel32' = 4 bytes
    out = bytearray()
    for it in items:
        here = base + len(out)
        if isinstance(it, bytes):
            out += it
        elif it[0] in ('call', 'jmp'):
            tgt = labels.get(it[1], it[1])
            out += (b'\xE8' if it[0] == 'call' else b'\xE9') + rel32(here, tgt)
        elif it[0] == 'abs':
            out += struct.pack('<I', labels[it[1]])
        elif it[0] == 'rel32':                     # displacement of a jcc whose opcode precedes
            out += struct.pack('<i', labels.get(it[1], it[1]) - (here + 4))
    return bytes(out), labels


def _header_items():
    u32 = lambda v: struct.pack('<I', v)
    return [
        ('label', 'GRANT'),
        b'\xB8' + u32(REC1),                               # mov eax,REC1
        ('label', 'G_L'),
        b'\x80\x20\x0F', b'\x80\x08\x60', b'\x83\xC0\x78',   # and [eax],0F ; or [eax],60 ; add eax,78
        b'\x3D' + u32(REC1 + 15 * 0x78), b'\x72\xF0',          # cmp eax,end ; jb G_L
        b'\x80\x0D' + u32(REC1) + b'\x80',                   # or [Superman],80
        b'\x80\x0D' + u32(REC1 + 3 * 0x78) + b'\x80',        # or [Wonder Woman],80
        b'\xC3',
        ('label', 'BUYALL'),                                 # every shop item not yet bought:
        b'\x53', b'\xBB' + u32(1),                            # push ebx ; mov ebx,1
        ('label', 'B_L'),
        b'\x80\xBB' + u32(SHOP - 1) + b'\x00', b'\x75\x0B',     # cmp byte [ebx+SHOP-1],0 ; jne B_N
        b'\x6A\x01', b'\x53', ('call', SHOP_BUY), b'\x83\xC4\x08',   # 0x7CC2F(item, 1)
        ('label', 'B_N'),
        b'\x43', b'\x83\xFB\x17', b'\x76\xE6',                  # inc ebx ; cmp ebx,23 ; jbe B_L
        b'\x5B', b'\xC3',
        ('label', 'W2'),
        ('call', 'BUYALL'), ('call', CA), ('call', 'GRANT'), ('jmp', START_REQ),
        ('label', 'LH'),
        b'\x80\x3D' + u32(REPLAY_FLAG) + b'\x00', b'\x74\x0A',    # cmp byte [replay],0 ; je +10
        ('call', 'BUYALL'), ('call', 'GRANT'),
        b'\x8B\xC6', ('jmp', LOAD_RETURN),                     # mov eax,esi ; jmp back
        ('label', 'CPS'),                                    # load finished: start request
        b'\x0F\xB6\x05' + u32(REPLAY_FLAG), b'\x48', b'\x50',   # Continued Play -> row 0, Load -> -1
        ('call', START_REQ), b'\x59', b'\xC3',
        ('label', 'RST'),                                    # Restart Episode
        b'\x81\x3D' + u32(CUR_LEVEL) + b'ebon', b'\x0F\x85', ('rel32', RESTART_EP),
        b'\x6A\x08', ('call', 0x0003A06C), b'\x59',             # same resets as 0x67FCE
        ('call', 0x0006CA36), ('call', 0x00069054),
        b'\x68' + u32(CUR_LEVEL), b'\x68' + u32(NEXT_LEVEL), ('call', STRCPY), b'\x83\xC4\x08',
        b'\xC6\x05' + u32(0x002C3025) + b'\x01',              # allow reloading the same level
        b'\xC3',
        ('label', 'SEL'),
        b'\xBB' + u32(COL_EXCLUDE),                          # mov ebx,"charExclude"
        b'\xF6\x05' + u32(REC1) + b'\x10', b'\x74\x05',         # test byte [Superman],10 ; jz +5
        b'\xBB', ('abs', 'NG'),                               # mov ebx,"charExclNew"
        b'\xC3',
        ('label', 'WWA'),
        b'\xA0' + u32(REC1 + 3 * 0x78), b'\x24\x0F', b'\x3C\x03', b'\x75\x0A',   # worn costume == 3 ?
        b'\xBE' + u32(WW_ARMOUR_MODEL), ('jmp', WW_ARMOUR),
        b'\x68' + u32(0x002C44DA), ('jmp', WW_CONT),          # original push ; continue
        ('label', 'SELCS'),                                  # story: "charSel" -> "charSelNew"
        b'\xBB' + u32(COL_CHARSEL), b'\xF6\x05' + u32(REC1) + b'\x10', b'\x74\x05',
        b'\xBB', ('abs', 'CSN'), b'\xC3',
        ('label', 'SELTID'),                                 # story: "teamID" -> "teamIDNew"
        b'\xBB' + u32(COL_TEAMID), b'\xF6\x05' + u32(REC1) + b'\x10', b'\x74\x05',
        b'\xBB', ('abs', 'TIN'), b'\xC3',
        ('label', 'PUSHCS'),                                 # replaces `push "charSel"`
        b'\xB8' + u32(COL_CHARSEL), b'\xF6\x05' + u32(REC1) + b'\x10', b'\x74\x05',
        b'\xB8', ('abs', 'CSN'),
        b'\x59', b'\x50', b'\xFF\xE1',                          # pop ecx ; push eax ; jmp ecx
        ('label', 'NOAS'),                                   # no autosave in challenges
        b'\x81\x3D' + u32(CUR_LEVEL) + b'ebon', b'\x74\x12',      # cmp [current],'ebon' ; je Z
        b'\x81\x3D' + u32(NEXT_LEVEL) + b'ebon', b'\x74\x06',     # cmp [next],'ebon' ; je Z
        b'\xA3' + u32(AUTOSAVE_REQ), b'\xC3',                   # mov [req],eax ; ret
        b'\xC7\x05' + u32(AUTOSAVE_REQ) + u32(0), b'\xC3',       # Z: mov dword [req],0 ; ret
        ('label', 'NG'),
        NG_COLUMN + b'\x00',
        ('label', 'CSN'), b'charSelNew\x00',
        ('label', 'TIN'), b'teamIDNew\x00',
    ]


HDR_CODE, HDR_LABELS = _assemble(HDR, _header_items())
assert HDR + len(HDR_CODE) <= 0x00011000
assert HDR_CODE[HDR_LABELS['G_L'] - HDR + 14:HDR_LABELS['G_L'] - HDR + 16] == b'\x72\xF0'   # jb G_L


def build_header():
    jmp_site = lambda frm, to: b'\xE9' + rel32(frm, to)
    call_site = lambda frm, to: b'\xE8' + rel32(frm, to)
    return [
        (HDR, b'\x00' * len(HDR_CODE), HDR_CODE),
        (SEL_SITE, SEL_ORIG, call_site(SEL_SITE, HDR_LABELS['SEL'])),
        (WW_SITE, WW_ORIG, jmp_site(WW_SITE, HDR_LABELS['WWA'])),
        (RST_SITE, RST_ORIG, jmp_site(RST_SITE, HDR_LABELS['RST'])),
        (CPS_SITE, CPS_ORIG, jmp_site(CPS_SITE, HDR_LABELS['CPS']) + b'\xCC' * 4),
        NEWGAME_ROW,
        (CS_SITE1, CS_ORIG1, call_site(CS_SITE1, HDR_LABELS['SELCS'])),
        (CS_SITE2, CS_ORIG2, call_site(CS_SITE2, HDR_LABELS['PUSHCS'])),
        (TID_SITE, TID_ORIG, call_site(TID_SITE, HDR_LABELS['SELTID'])),
        (NOAS_SITE, NOAS_ORIG, call_site(NOAS_SITE, HDR_LABELS['NOAS'])),
    ]


# Greyed-out heroes (charExclude) are parsed into 4 dword slots 0x2ADCF4-0x2AD00 (0x1B13B-0x1B1AA)
# and tested by 0x1B49F. Longer lists overflowed into the cutscene names at 0x2AD04 and heroes
# after the 4th were never greyed. The list becomes a bitmask in the first slot:
#   init: or eax,-1 -> xor eax,eax (slots = 0)
#   store: bts [slot0],hero ; the slot pointer no longer advances
#   test 0x1B49F: bt [0x2ADCF4],hero ; setc al ; ret
def build_exclmask():
    store_orig = bytes.fromhex('eb05' '8b4510' '8918' '85ff' '7409' '83451004' '8d7701' 'ebbe')
    store_new = bytes.fromhex('eb06' '8b4510' '0fab18' '85ff' '7408' '8d7701' 'ebc1' '909090')
    test_orig = bytes.fromhex('b8f4dc2a00' '8b08' '3b4c2404' '740d' '83c004' '3d04dd2a00' '7cee' '32c0' 'c3' 'b001' 'c3')
    test_new = bytes.fromhex('8b442404' '0fa305f4dc2a00' '0f92c0' 'c3')
    test_new += b'\xCC' * (len(test_orig) - len(test_new))
    assert len(store_orig) == len(store_new) == 20
    return [(0x0001B13B, bytes.fromhex('83c8ff'), bytes.fromhex('31c090')),
            (0x0001B198, store_orig, store_new),
            (0x0001B49F, test_orig, test_new)]


def build_all():
    # cmp [ebp-4],6 -> cmp [ebp-4],0x7F : (id > 127) is never true -> nothing locked
    return [(SITE + 3, b'\x06', b'\x7F')]


class XBE:
    def __init__(self, data):
        self.d = bytearray(data)
        self.base = struct.unpack_from('<I', self.d, 0x104)[0]
        self.n = struct.unpack_from('<I', self.d, 0x11C)[0]
        self.sh = struct.unpack_from('<I', self.d, 0x120)[0] - self.base

    def sections(self):
        for i in range(self.n):
            o = self.sh + 56 * i
            fl, va, vs, ra, rs = struct.unpack_from('<5I', self.d, o)
            yield i, o, va, vs, ra, rs

    def off(self, va):
        if self.base <= va < self.base + 0x1000:          # header page (see build_header)
            return va - self.base, None
        for i, o, sva, vs, ra, rs in self.sections():
            if sva <= va < sva + rs:
                return ra + va - sva, i
        raise ValueError(f'VA {va:#x} not in any section')

    def fix_digest(self, idx):
        for i, o, va, vs, ra, rs in self.sections():
            if i == idx:
                dig = hashlib.sha1(struct.pack('<I', rs) + bytes(self.d[ra:ra + rs])).digest()
                self.d[o + 36:o + 56] = dig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--mode', choices=['standard', 'sgbc', 'all'], default='standard')
    a = ap.parse_args()
    data = open(a.src, 'rb').read()
    sha = hashlib.sha1(data).hexdigest()
    if sha != EXPECTED_SHA1:
        sys.exit(f'Unexpected default.xbe (SHA-1 {sha}). This patch is only for {EXPECTED_SHA1}.')
    x = XBE(data)
    touched = set()
    soh = struct.unpack_from('<I', x.d, SOH_FIELD)[0]
    if soh != SOH_ORIG or any(x.d[SOH_ORIG:SOH_NEW]):
        sys.exit('Unexpected XBE header size/padding; aborting.')
    struct.pack_into('<I', x.d, SOH_FIELD, SOH_NEW)
    unlock = {'standard': [], 'sgbc': build_sgbc(), 'all': build_all()}[a.mode]
    for va, orig, new in (unlock + [PRELOAD] + build_loadfix(clear_locks=a.mode != 'standard')
                          + build_maxheroes() + build_header() + build_exclmask()):
        o, sec = x.off(va)
        if bytes(x.d[o:o + len(orig)]) != orig:
            sys.exit(f'Bytes at {va:#x} are not what the patch expects; aborting.')
        x.d[o:o + len(new)] = new
        touched.add(sec)
    for s in touched - {None}:
        x.fix_digest(s)
    open(a.dst, 'wb').write(x.d)
    print(f'Patched ({a.mode}) -> {a.dst}')


if __name__ == '__main__':
    main()
