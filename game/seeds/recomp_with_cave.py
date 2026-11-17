"""Runs tools.recomp with the XBE-header code cave (the user's mod,
0x10E00-0x10F5B) added to its section layout. The generator reads sections
from the XBE itself, where the cave is part of the header, so without this
it treats those 12 functions as non-code and emits empty bodies.
Run from the toolkit directory with the same arguments as tools.recomp."""
import os, sys, runpy
sys.path.insert(0, os.getcwd())
import tools.recomp.config as cfg

_orig = cfg.configure_from_xbe

def _with_cave(xbe_path):
    _orig(xbe_path)
    secs = [s for s in cfg._SECTIONS if s.name != "HDRCAVE"]
    secs.append(cfg.Section(name="HDRCAVE", va=0x10E00, va_size=0x15B,
                            raw_addr=0xE00, raw_size=0x15B, is_code=True))
    cfg._install(secs, cfg.ENTRY_POINT, cfg.KERNEL_THUNK_ADDR, xbe_path)
    print("recomp_with_cave: HDRCAVE 0x00010E00+0x15B added to the layout", flush=True)

cfg.configure_from_xbe = _with_cave
sys.argv = ["tools.recomp"] + sys.argv[1:]
runpy.run_module("tools.recomp", run_name="__main__", alter_sys=True)
