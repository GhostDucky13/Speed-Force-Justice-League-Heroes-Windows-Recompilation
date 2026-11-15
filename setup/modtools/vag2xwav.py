#!/usr/bin/env python3
"""
vag2xwav.py - Convert PSP .vag sounds to the Xbox .wav format used by
Justice League Heroes (Xbox ADPCM, RIFF format tag 0x0069, mono).

Usage:
  python vag2xwav.py in.vag out.wav
  python vag2xwav.py --dir in_folder out_folder   (converts every .vag)

Also exposes decode_vag(), decode_xbox_adpcm() and encode_xbox_adpcm() for testing.
"""
import os
import struct
import sys

# ------------------------------------------------------------------ VAG ---
VAG_COEF = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def decode_vag(data):
    """Returns (pcm list of int, sample_rate)."""
    if data[:4] != b"VAGp":
        raise ValueError("not a VAG file")
    size = struct.unpack_from(">I", data, 0x0C)[0]
    rate = struct.unpack_from(">I", data, 0x10)[0]
    pos, end = 0x30, min(len(data), 0x30 + size)
    s1 = s2 = 0
    pcm = []
    while pos + 16 <= end:
        hdr, flags = data[pos], data[pos + 1]
        if flags == 7:  # end marker frame
            break
        shift, pred = hdr & 0x0F, min(hdr >> 4, 4)
        c0, c1 = VAG_COEF[pred]
        for b in data[pos + 2:pos + 16]:
            for nib in (b & 0x0F, b >> 4):
                v = (nib << 12) & 0xFFFF
                if v & 0x8000:
                    v -= 0x10000
                v = (v >> shift) + ((s1 * c0 + s2 * c1) >> 6)
                v = max(-32768, min(32767, v))
                pcm.append(v)
                s2, s1 = s1, v
        pos += 16
        if flags == 1:  # end of sample
            break
    return pcm, rate


# ----------------------------------------------------- Xbox / IMA ADPCM ---
STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
        50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
        253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
        1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
        3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
        12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8]
BLOCK = 36            # bytes per mono block
SPB = 64              # samples per block (header sample + 63 decoded... see below)


def _step(pred, idx, nib):
    st = STEP[idx]
    diff = st >> 3
    if nib & 1: diff += st >> 2
    if nib & 2: diff += st >> 1
    if nib & 4: diff += st
    pred = pred - diff if nib & 8 else pred + diff
    pred = max(-32768, min(32767, pred))
    idx = max(0, min(88, idx + IDX[nib & 7]))
    return pred, idx


def decode_xbox_adpcm(data):
    """Decode mono Xbox ADPCM block data -> pcm (65 samples per 36-byte block)."""
    pcm = []
    for b in range(0, len(data) - BLOCK + 1, BLOCK):
        pred, idx = struct.unpack_from("<hB", data, b)
        idx = min(idx, 88)
        pcm.append(pred)
        for byte in data[b + 4:b + BLOCK]:
            for nib in (byte & 0x0F, byte >> 4):
                pred, idx = _step(pred, idx, nib)
                pcm.append(pred)
    return pcm


def encode_xbox_adpcm(pcm):
    """Encode mono pcm -> Xbox ADPCM blocks. Each block: header sample + 64 coded samples."""
    out = bytearray()
    idx = 0
    i = 0
    n = len(pcm)
    while i < n:
        pred = pcm[i]
        out += struct.pack("<hBB", pred, idx, 0)
        i += 1
        nibs = []
        for _ in range(64):
            target = pcm[i] if i < n else pcm[-1] if n else 0
            i += 1
            st = STEP[idx]
            d = target - pred
            nib = 0
            if d < 0:
                nib, d = 8, -d
            if d >= st: nib |= 4; d -= st
            if d >= st >> 1: nib |= 2; d -= st >> 1
            if d >= st >> 2: nib |= 1
            pred, idx = _step(pred, idx, nib)
            nibs.append(nib)
        out += bytes(nibs[k] | (nibs[k + 1] << 4) for k in range(0, 64, 2))
    return bytes(out)


def build_wav(adpcm, rate):
    fmt = struct.pack("<HHIIHHHH", 0x0069, 1, rate, rate * BLOCK // SPB, BLOCK, 4, 2, SPB)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(adpcm)) + adpcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


def read_wav(data):
    """Returns (fmt_tag, rate, data bytes)."""
    pos, fmt_tag, rate, payload = 12, None, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if cid == b"fmt ":
            fmt_tag, _, rate = struct.unpack_from("<HHI", data, pos + 8)
        elif cid == b"data":
            payload = data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    return fmt_tag, rate, payload


def convert(src, dst):
    pcm, rate = decode_vag(open(src, "rb").read())
    open(dst, "wb").write(build_wav(encode_xbox_adpcm(pcm), rate))
    return len(pcm), rate


def main():
    if sys.argv[1] == "--dir":
        src, dst = sys.argv[2], sys.argv[3]
        os.makedirs(dst, exist_ok=True)
        n = 0
        for f in sorted(os.listdir(src)):
            if f.lower().endswith(".vag"):
                convert(os.path.join(src, f), os.path.join(dst, f[:-4] + ".wav"))
                n += 1
        print(f"{n} sounds converted -> {dst}")
    else:
        n, rate = convert(sys.argv[1], sys.argv[2])
        print(f"{n} samples @ {rate} Hz -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
