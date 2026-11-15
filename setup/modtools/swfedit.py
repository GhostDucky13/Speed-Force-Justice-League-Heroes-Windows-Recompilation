#!/usr/bin/env python3
"""
swfedit.py - Edit action code in a Flash 4 .swb (Snowblind menus) with size changes.

  sw = SWF(data)
  sw.edit(label, edits)      label as printed by swb.action_blocks ("/ DoAction@0x6f202",
                             "/ button193 cond 0x1e00", "/sprite36 DoAction@0x43d13", ...)
  data = sw.build()          tag / sprite / button lengths and the SWF file length recomputed

edits: list of (start, end, items) on ORIGINAL instruction offsets: the instructions in
[start, end) are replaced by items (start == end inserts before `start`). Branches into a
replaced range land on the start of its new code. items: bytes | ('if', target) | ('jump', target)
| ('label', name); targets are original offsets or label names.

Helpers below assemble Flash 4 actions. Rules learned on the Xbox player: one value per Push,
never pad with End bytes, set visible text only via XBE commands (CMD_UISTRING).
"""
import struct

import swb

# ------------------------------------------------------------------ assembler helpers
def push(*vals):
    out = b''
    for v in vals:
        if isinstance(v, float):
            body = b'\x01' + struct.pack('<f', v)
        else:
            body = b'\x00' + str(v).encode('latin-1') + b'\x00'
        out += b'\x96' + struct.pack('<H', len(body)) + body
    return out


def set_target(t):
    b = t.encode('latin-1') + b'\x00'
    return b'\x8b' + struct.pack('<H', len(b)) + b


def goto_frame(n):
    return b'\x81\x02\x00' + struct.pack('<H', n)


def goto_label(name):
    b = name.encode('latin-1') + b'\x00'
    return b'\x8c' + struct.pack('<H', len(b)) + b


GET, SET, TRACE, PLAY, STOP = b'\x1c', b'\x1d', b'\x26', b'\x06', b'\x07'
ADD, SUB, MUL, EQ, LESS, AND, OR, NOT, SADD = b'\x0a', b'\x0b', b'\x0c', b'\x0e', b'\x0f', b'\x10', b'\x11', b'\x12', b'\x21'
SETPROP, SETTARGET2, TOINT = b'\x23', b'\x20', b'\x18'


def setvar(name, value):
    return push(name, value) + SET


def uistring(target, key, var='text'):
    return set_target(target) + push(f'CMD_UISTRING,{var},{key}') + TRACE + set_target('')


class _Lbl:
    n = 0

    @classmethod
    def new(cls):
        cls.n += 1
        return f'_L{cls.n}'


def if_var_eq(var, value, body):
    """items: if (var == value) { body }"""
    skip = _Lbl.new()
    return [push(var) + GET + push(value) + EQ + NOT, ('if', skip)] + list(body) + [('label', skip)]


# ------------------------------------------------------------------ assembler
def assemble(items, orig_labels=None):
    """items: bytes | ('if'|'jump', target) | ('label', name). Returns bytes."""
    flat = []
    for it in items:
        if isinstance(it, (bytes, bytearray)):
            flat.append(('raw', bytes(it)))
        else:
            flat.append(it)
    pos, labels = 0, {}
    for it in flat:
        if it[0] == 'label':
            labels[it[1]] = pos
        elif it[0] == 'raw':
            pos += len(it[1])
        else:
            pos += 5
    end = pos
    out = bytearray()
    for it in flat:
        if it[0] == 'raw':
            out += it[1]
        elif it[0] in ('if', 'jump'):
            tgt = labels[it[1]] if it[1] in labels else end
            rel = tgt - (len(out) + 5)
            out += (b'\x9d' if it[0] == 'if' else b'\x99') + struct.pack('<Hh', 2, rel)
    return bytes(out), labels


def rewrite_block(d, s, e, edits):
    """Re-emit actions [s, e) of d applying edits; returns new bytes (ending with the block's End)."""
    ins = list(swb.disasm(d, s, e))
    offs = [p for p, _, _ in ins]
    edits = sorted(edits, key=lambda x: (x[0], x[1]))
    items, k, ei = [], 0, 0
    while k < len(ins) or ei < len(edits):
        p = offs[k] if k < len(ins) else e
        if ei < len(edits) and edits[ei][0] <= p:
            st, en, new = edits[ei]
            items.append(('label', st))
            while k < len(ins) and offs[k] < en:      # branches into a replaced range
                items.append(('label', offs[k]))      # land on the start of its new code
                k += 1
            items.extend(new)
            ei += 1
            continue
        if k >= len(ins):
            break
        op, name, args = ins[k]
        items.append(('label', op))   # for an insertion this later label wins: old branches skip it
        ln = 3 + struct.unpack_from('<H', d, op + 1)[0] if d[op] >= 0x80 else 1
        if name in ('if', 'jump'):
            items.append((name, args))
        else:
            items.append(d[op:op + ln])
        k += 1
    items.append(('label', e))
    fixed = items
    code, _ = assemble(fixed)
    if not code.endswith(b'\x00'):
        code += b'\x00'
    return code


# ------------------------------------------------------------------ SWF tree
class SWF:
    def __init__(self, data):
        self.d = bytes(data)
        self.hdr_end = swb.header_end(self.d)
        self.new = {}     # (tag_offset, cond_index or None) -> new action bytes

    def _label_map(self):
        m = {}
        for label, s, e in swb.action_blocks(self.d):
            m[label] = (s, e)
        return m

    def edit(self, label, edits):
        s, e = self._label_map()[label]
        code = rewrite_block(self.d, s, e, edits)
        self.new[s] = code
        return code

    def replace_code(self, label, code):
        s, e = self._label_map()[label]
        if not code.endswith(b'\x00'):
            code += b'\x00'
        self.new[s] = code

    # serialization -------------------------------------------------
    def _tags(self, start, end):
        o = start
        while o < end:
            code, ln, hdr = swb._tag_header(self.d, o)
            yield o, code, o + hdr, ln
            if code == 0:
                return
            o += hdr + ln

    @staticmethod
    def _tag(code, body, long_form):
        if long_form or len(body) >= 0x3F:
            return struct.pack('<HI', (code << 6) | 0x3F, len(body)) + body
        return struct.pack('<H', (code << 6) | len(body)) + body

    def _build_tags(self, start, end):
        out = bytearray()
        for o, code, body, ln in self._tags(start, end):
            long_form = (body - o) == 6
            if code == 0:
                out += self.d[o:body + ln]
                return bytes(out)
            if code == 39:              # DefineSprite: id, frames, nested tags
                b = self.d[body:body + 4] + self._build_tags(body + 4, body + ln)
            elif code == 12 and body in self.new:   # DoAction
                b = self.new[body]
            elif code == 34:            # DefineButton2
                b = self._build_button(body, ln)
            else:
                out += self.d[o:body + ln]          # untouched tag: copied byte for byte
                continue
            out += self._tag(code, bytes(b), long_form)
        return bytes(out)

    def _build_button(self, body, ln):
        d = self.d
        aoff = struct.unpack_from('<H', d, body + 3)[0]
        if aoff == 0:
            return d[body:body + ln]
        head = bytearray(d[body:body + 3 + aoff])
        conds, o, end = [], body + 3 + aoff, body + ln
        while True:
            size, cond = struct.unpack_from('<HH', d, o)
            a_end = o + size if size else end
            code = self.new.get(o + 4, d[o + 4:a_end])
            conds.append((cond, code))
            if size == 0:
                break
            o += size
        out = head
        for i, (cond, code) in enumerate(conds):
            last = i == len(conds) - 1
            out += struct.pack('<HH', 0 if last else 4 + len(code), cond) + code
        return bytes(out)

    def build(self):
        body = self._build_tags(self.hdr_end, len(self.d))
        out = bytearray(self.d[:self.hdr_end]) + body
        struct.pack_into('<I', out, 4, len(out))
        return bytes(out)
