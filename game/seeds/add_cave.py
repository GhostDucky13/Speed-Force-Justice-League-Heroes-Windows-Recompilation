"""Adds the XBE-header code cave (the user's mod, 0x10E00-0x10F5B) to the
xboxrecomp analysis JSON as an executable section, and writes a seed list of
its entry points, so the lifter translates it like any other code."""
import json, sys, os
analysis, seeds_out = sys.argv[1], sys.argv[2]
a = json.load(open(analysis))
a["sections"] = [s for s in a["sections"] if s["name"] != "HDRCAVE"]
a["sections"].insert(0, {
    "name": "HDRCAVE", "virtual_addr": "0x00010E00", "virtual_size": 0x15B,
    "raw_addr": "0x00000E00", "raw_size": 0x15B, "flags": "PRE, X",
    "writable": False, "executable": True})
json.dump(a, open(analysis, "w"), indent=2)
entries = [0x10E00, 0x10E24, 0x10E46, 0x10E5A, 0x10E74, 0x10E84,
           0x10EC0, 0x10ED4, 0x10EF3, 0x10F07, 0x10F1B, 0x10F32]
json.dump([{"start": "0x%08X" % e, "note": "header cave (mod)"} for e in entries],
          open(seeds_out, "w"), indent=1)
print("HDRCAVE added; %d seeds -> %s" % (len(entries), seeds_out))
