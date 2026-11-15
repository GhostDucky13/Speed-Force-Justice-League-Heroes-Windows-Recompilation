#!/usr/bin/env python3
"""
build_gametext.py - Xbox gametext.lmp with the text of the PSP story levels (build_psp_story.py):
  uistrings      e1l8 / e5l5 / e11l2 = the PSP rows pspe1 / pspe5 / pspe11 (level names)
  scriptstrings  pspe1title pspe1intro pspe1end pspe5introtitle pspe5 pspe11 (used by the
                 level scripts / objects under their PSP keys)
  missionstrings e11part4 ("Protect the perimeter", objective of e11l2)
  uistrings      chsel "Chapter Select" (main-menu item 1, replaces Continued Play)
All five languages are copied from the PSP table.

  python build_gametext.py xbox_gametext.lmp psp_gametext.lmp out_gametext.lmp
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gdt  # noqa: E402
import lmp  # noqa: E402

ADD = {
    '~~U:uistrings': [('pspe1', 'e1l8'), ('pspe5', 'e5l5'), ('pspe11', 'e11l2')],
    '~~U:scriptstrings': [(k, k) for k in ('pspe1title', 'pspe1intro', 'pspe1end', 'pspe5introtitle', 'pspe5', 'pspe11')],
    '~~U:missionstrings': [('e11part4', 'e11part4')],
}


NEW_ROWS = {   # rows that exist on neither disc (update 13: main-menu item 1)
    '~~U:uistrings': [('chsel', ['Chapter Select', 'Selección de capítulo', 'Kapitelauswahl',
                                 'Sélection du chapitre', 'Selezione capitolo'])],
}


def build(xd, pd):
    gx, gp = gdt.parse(xd), gdt.parse(pd)
    tp = {t['name']: t for t in gp['tables']}
    for t in gx['tables']:
        for src, dst in ADD.get(t['name'], []):
            if dst in t['rows']:
                continue
            p = tp[t['name']]
            assert p['cols'] == t['cols']
            t['rows'].append(dst)
            t['grid'].append(list(p['grid'][p['rows'].index(src)]))
        for key, texts in NEW_ROWS.get(t['name'], []):
            if key not in t['rows']:
                assert len(texts) == len(t['cols'])
                t['rows'].append(key)
                t['grid'].append([('w', x, None) for x in texts])
    return gdt.build(gx)


def main():
    xs, ps, out = sys.argv[1:4]
    pe = dict((n, b) for n, b, _ in lmp.read(ps))
    lmp.build([(n, build(b, pe[n]) if n.endswith('.gdt') else b) for n, b, _ in lmp.read(xs)], out)
    print('gametext ->', out)


if __name__ == '__main__':
    main()
