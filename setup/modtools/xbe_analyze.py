#!/usr/bin/env python3
"""
xbe_analyze.py - Stage 1 analysis of an original Xbox executable (default.xbe)
for the Justice League Heroes recompilation project.

Pure Python, no dependencies. Produces:
  - header summary (base, entry point, retail/debug key detection)
  - certificate (title ID, title name, region, version)
  - section table
  - statically linked XDK library versions (D3D8, DSOUND, XAPILIB, ...)
  - kernel import ordinals (what the runtime must implement)
  - a rough function-start count (prologue scan) per executable section
  - interesting strings (engine/build hints)

Usage:
  python3 -I xbe_analyze.py path/to/default.xbe [--out report_dir]
"""
import argparse
import json
import os
import re
import struct
import sys

ENTRY_KEYS = {"retail": 0xA8FC57AB, "debug": 0x94859D4B, "chihiro": 0x40B5C16E}
THUNK_KEYS = {"retail": 0x5B6D40B6, "debug": 0xEFB1F152, "chihiro": 0x2290059D}

SECTION_FLAGS = {
    0x1: "WRITABLE", 0x2: "PRELOAD", 0x4: "EXECUTABLE",
    0x8: "INSERTED_FILE", 0x10: "HEAD_PAGE_RO", 0x20: "TAIL_PAGE_RO",
}

REGIONS = {0x1: "NA", 0x2: "JP", 0x4: "RestOfWorld", 0x80000000: "Manufacturing"}


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


class XBE:
    def __init__(self, data):
        if data[:4] != b"XBEH":
            raise ValueError("Not an XBE file (missing XBEH magic)")
        self.d = data
        self.base = u32(data, 0x104)
        self.size_headers = u32(data, 0x108)
        self.size_image = u32(data, 0x10C)
        self.timedate = u32(data, 0x114)
        self.cert_addr = u32(data, 0x118)
        self.num_sections = u32(data, 0x11C)
        self.sect_addr = u32(data, 0x120)
        self.init_flags = u32(data, 0x124)
        self.entry_enc = u32(data, 0x128)
        self.tls_addr = u32(data, 0x12C)
        self.debug_filename_addr = u32(data, 0x150)
        self.thunk_enc = u32(data, 0x158)
        self.nonkernel_import_dir = u32(data, 0x15C)
        self.num_libs = u32(data, 0x160)
        self.libs_addr = u32(data, 0x164)
        self.sections = self._sections()
        self.kind, self.entry = self._decode(self.entry_enc, ENTRY_KEYS)
        tk = THUNK_KEYS.get(self.kind)
        self.thunk = (self.thunk_enc ^ tk) if tk is not None else None

    # --- address translation -------------------------------------------
    def hdr_off(self, va):
        """Header-area VA -> file offset."""
        return va - self.base

    def va_to_off(self, va):
        if self.base <= va < self.base + self.size_headers:
            return va - self.base
        for s in self.sections:
            if s["va"] <= va < s["va"] + s["raw_size"]:
                return s["raw_addr"] + (va - s["va"])
        return None

    def cstr(self, off, maxlen=256):
        end = self.d.find(b"\0", off, off + maxlen)
        return self.d[off:end if end != -1 else off + maxlen].decode("latin-1")

    # --- parsing --------------------------------------------------------
    def _decode(self, value, keys):
        # Pick the key that yields an address inside the image.
        for name, key in keys.items():
            va = value ^ key
            if self.base <= va < self.base + self.size_image:
                return name, va
        return "unknown", None

    def _sections(self):
        out = []
        off = self.hdr_off(self.sect_addr)
        for i in range(self.num_sections):
            o = off + i * 56
            flags, va, vsize, raw, rsize, name_addr = struct.unpack_from("<6I", self.d, o)
            name = self.cstr(self.hdr_off(name_addr), 32) if name_addr else f"sect{i}"
            out.append({
                "name": name, "flags": flags,
                "flag_names": [n for f, n in SECTION_FLAGS.items() if flags & f],
                "va": va, "virtual_size": vsize, "raw_addr": raw, "raw_size": rsize,
            })
        return out

    def certificate(self):
        o = self.hdr_off(self.cert_addr)
        title_id = u32(self.d, o + 0x8)
        title_name = self.d[o + 0xC:o + 0xC + 80].decode("utf-16-le").split("\0")[0]
        region = u32(self.d, o + 0xA0)
        version = u32(self.d, o + 0xAC)
        tid_str = "".join(chr(c) if 32 <= c < 127 else "?" for c in
                          [(title_id >> 24) & 0xFF, (title_id >> 16) & 0xFF])
        return {
            "title_id": f"{title_id:08X}",
            "title_id_readable": f"{tid_str}-{title_id & 0xFFFF:03d}",
            "title_name": title_name,
            "region": [n for f, n in REGIONS.items() if region & f] or [f"0x{region:X}"],
            "version": version,
        }

    def libraries(self):
        libs = []
        off = self.hdr_off(self.libs_addr)
        for i in range(self.num_libs):
            o = off + i * 16
            name = self.d[o:o + 8].split(b"\0")[0].decode("latin-1")
            major, minor, build, flags = struct.unpack_from("<4H", self.d, o + 8)
            libs.append({
                "name": name, "version": f"{major}.{minor}.{build}",
                "qfe": flags & 0x1FFF, "approved": (flags >> 13) & 0x3,
                "debug_build": bool(flags & 0x8000),
            })
        return libs

    def kernel_imports(self):
        if self.thunk is None:
            return []
        off = self.va_to_off(self.thunk)
        if off is None:
            return []
        ords = []
        while True:
            v = u32(self.d, off)
            if v == 0:
                break
            ords.append(v & 0x7FFFFFFF)
            off += 4
            if len(ords) > 400:
                break
        return ords

    def function_starts(self):
        """Very rough: count MSVC-style frame prologues in executable sections.
        The real pass (recursive descent + emulator traces) comes later."""
        pats = [
            re.compile(rb"\x55\x8B\xEC"),          # push ebp; mov ebp, esp
            re.compile(rb"\x55\x89\xE5"),          # push ebp; mov ebp, esp (alt enc)
            re.compile(rb"\x83\xEC[\x04-\x7C]\x53\x55\x56\x57"),  # sub esp,N; push regs (FPO)
        ]
        res = {}
        for s in self.sections:
            if not (s["flags"] & 0x4):
                continue
            blob = self.d[s["raw_addr"]:s["raw_addr"] + s["raw_size"]]
            hits = set()
            for p in pats:
                for m in p.finditer(blob):
                    hits.add(m.start())
            res[s["name"]] = len(hits)
        return res

    def strings(self, minlen=6, limit=400):
        keywords = re.compile(
            rb"(?i)(snowblind|justice|league|\.c(pp)?\b|\.h\b|d:\\|c:\\|\\src\\|"
            rb"build|version|\.xbe|\.xpr|\.xwb|\.xsb|\.wad|\.bik|\.ps2|psp|"
            rb"debug|assert|render|shader|texture|model|anim|level|hero|"
            rb"superman|batman|wonder|flash|lantern|manhunter|zatanna|aquaman|"
            rb"arrow|hawkgirl|huntress|rayner|jordan|supergirl|canary)")
        found = []
        for m in re.finditer(rb"[\x20-\x7E]{%d,}" % minlen, self.d):
            s = m.group()
            if keywords.search(s):
                found.append((m.start(), s.decode("latin-1")))
                if len(found) >= limit:
                    break
        return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xbe")
    ap.add_argument("--out", default="report")
    a = ap.parse_args()

    with open(a.xbe, "rb") as f:
        x = XBE(f.read())
    os.makedirs(a.out, exist_ok=True)

    report = {
        "file": os.path.basename(a.xbe),
        "build_kind": x.kind,
        "base": f"0x{x.base:08X}",
        "entry_point": f"0x{x.entry:08X}" if x.entry else None,
        "kernel_thunk": f"0x{x.thunk:08X}" if x.thunk else None,
        "image_size": x.size_image,
        "debug_filename": x.cstr(x.hdr_off(x.debug_filename_addr)) if x.debug_filename_addr else None,
        "certificate": x.certificate(),
        "sections": [{**s, "va": f"0x{s['va']:08X}"} for s in x.sections],
        "xdk_libraries": x.libraries(),
        "kernel_import_ordinals": x.kernel_imports(),
        "approx_function_starts": x.function_starts(),
    }
    with open(os.path.join(a.out, "xbe_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(a.out, "strings.txt"), "w") as f:
        for off, s in x.strings():
            f.write(f"{off:08X}  {s}\n")

    c = report["certificate"]
    print(f"Title      : {c['title_name']}  [{c['title_id_readable']}]  v{c['version']}")
    print(f"Region     : {', '.join(c['region'])}")
    print(f"Build      : {x.kind}   base {report['base']}   entry {report['entry_point']}")
    print(f"PDB/debug  : {report['debug_filename']}")
    print(f"\nSections ({len(x.sections)}):")
    for s in x.sections:
        print(f"  {s['name']:<10} va 0x{s['va']:08X}  size 0x{s['virtual_size']:07X}  "
              f"{'|'.join(s['flag_names'])}")
    print(f"\nXDK libraries ({len(report['xdk_libraries'])}):")
    for l in report["xdk_libraries"]:
        print(f"  {l['name']:<9} {l['version']}{'  (debug)' if l['debug_build'] else ''}")
    ko = report["kernel_import_ordinals"]
    print(f"\nKernel imports: {len(ko)} ordinals")
    print(f"Approx. function starts: {report['approx_function_starts']}")
    print(f"\nWrote {a.out}/xbe_report.json and {a.out}/strings.txt")


if __name__ == "__main__":
    main()
