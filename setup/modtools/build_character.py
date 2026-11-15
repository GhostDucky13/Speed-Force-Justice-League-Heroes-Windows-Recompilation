#!/usr/bin/env python3
"""
build_character.py - Convert a PSP character archive (.lmp) into an Xbox one.

  .anm  animations  -> copied unchanged (same format on both platforms)
  .vag  sounds      -> Xbox ADPCM .wav            (vag2xwav)
  .tex  textures    -> Xbox 8-bit paletted .tex   (tex)
  <name>.vif models -> Xbox .vif                  (vif_psp2xbox)
  cape8.vif         -> Xbox cloth cape, using an Xbox cape8.vif as structural template

Usage:
  python build_character.py psp_char.lmp out_xbox_char.lmp [xbox_cape_template.vif]
  (the cape template is any Xbox character's cape8.vif, e.g. from the Xbox zatanna.lmp;
   only needed if the character has a cape)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp  # noqa: E402
import tex  # noqa: E402
import vag2xwav  # noqa: E402
import vif_psp2xbox  # noqa: E402
import cape_psp2xbox  # noqa: E402


def build(psp_lmp, cape_template=None, log=print):
    entries = lmp.read(psp_lmp)
    files = {name.lower(): data for name, data, _ in entries}
    out, stats = [], {}
    for name, data, _ in entries:
        low = name.lower()
        ext = low.rsplit('.', 1)[-1]
        if ext == 'anm':
            out.append((name, data))
        elif ext == 'vag':
            pcm, rate = vag2xwav.decode_vag(data)
            out.append((name[:-4] + '.wav', vag2xwav.build_wav(vag2xwav.encode_xbox_adpcm(pcm), rate)))
        elif ext == 'tex':
            out.append((name, tex.to_xbox(data)))
        elif ext == 'vif':
            base = low[:-4]
            texdata = files.get(base + '.tex')
            if texdata is None:
                raise ValueError(f'{name}: no matching {base}.tex in archive')
            w, h = struct.unpack_from('<HH', texdata, 0)
            if base.startswith('cape'):
                if cape_template is None:
                    raise ValueError(f'{name}: a cape template (Xbox cape8.vif) is required')
                out.append((name, cape_psp2xbox.convert(data, w, h, cape_template)))
                log(f'  {name}: cape rebuilt on Xbox cloth template')
            else:
                conv, info = vif_psp2xbox.convert(data, w, h)
                out.append((name, conv))
                log(f'  {name}: {info}')
        else:
            raise ValueError(f'{name}: unhandled file type .{ext}')
        stats[ext] = stats.get(ext, 0) + 1
    return out, stats


def main():
    src, dst = sys.argv[1], sys.argv[2]
    tmpl = open(sys.argv[3], 'rb').read() if len(sys.argv) > 3 else None
    out, stats = build(src, tmpl)
    lmp.build(out, dst)
    print(f'{os.path.basename(src)} -> {dst}: {stats}, {os.path.getsize(dst):,} bytes')


if __name__ == '__main__':
    main()
