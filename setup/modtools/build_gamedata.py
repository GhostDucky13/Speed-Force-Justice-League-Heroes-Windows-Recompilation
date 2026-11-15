#!/usr/bin/env python3
"""
build_gamedata.py - Xbox gamedata.lmp with:
  * the four PSP challenge missions (ebonus1-4 rows from the PSP levels.gdt, at the end)
  * character select at the start of every episode. Episodes 1-5, 7 and 10 had a fixed story
    pair (Player1/Player2); they now use team 0 like the free episodes 6, 8, 9, 11, with
    charSel "c1,2" on their first level. Flight episodes grey out the heroes that can't fly
    (charExclude): Episode 2 (Queen Bee's throne), Episode 7 (space) and Episode 10 part 3.
    Episode 10's three parts each get their own selection (they had three different teams).
New Game (update 13): while the save is in story mode the game reads charSelNew / teamIDNew /
charExclNew instead of charSel / teamID / charExclude (patch_unlock.py). Those hold the original
values, and Player1/Player2 are no longer cleared, so a New Game plays the original fixed story
pairs with no selection. Episode 11's fixed level e11l3 also gets a selection outside New Game.
Fliers (models with fly_* animations): Superman, Supergirl, Wonder Woman, Martian Manhunter,
Hawkgirl, the three Green Lanterns, Zatanna. Ground: Batman, Flash, Green Arrow, Aquaman,
Huntress, Black Canary.

  python build_gamedata.py xbox_gamedata.lmp psp_gamedata.lmp out_gamedata.lmp
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gdt  # noqa: E402
import lmp  # noqa: E402

GROUND = 'bm,fl,ga,am,hu,bc'
EPISODES = {           # episode prefix: {first-level rows that get a selection: exclude}
    'e1': {'e1l1a': None},
    'e2': {'e2l1': GROUND},
    'e3': {'e3l1': None},
    'e4': {'e4l1': None},
    'e5': {'e5l1': GROUND},       # Mars: fliers only (user request)
    'e7': {'e7l1': GROUND},
    'e10': {'e10l1': None, 'e10l2': None, 'e10l5': GROUND},
}
STORY_LEVELS = [('pspe1', 'e1l8'), ('pspe5', 'e5l5'), ('pspe11', 'e11l2')]
EXTRA_ROWS = {'e11l3': None}     # fixed single levels inside otherwise free episodes
HEROES = 'sm mm bm ww fl gl za gk gh ga am hg hu sg bc'.split()
CODE = {'superman': 'sm', 'manhunter': 'mm', 'batman': 'bm', 'wwoman': 'ww', 'flash': 'fl',
        'glantern': 'gl', 'zatanna': 'za'}
NG_COLUMN = 'charExclNew'
STORY_COLS = {'charExclude': NG_COLUMN, 'charSel': 'charSelNew', 'teamID': 'teamIDNew'}



def episode_of(row):
    return row.split('l')[0] if row.startswith('e') and 'l' in row else None


def build(xg, pg):
    gx, gp = gdt.parse(xg), gdt.parse(pg)
    tx, tp = gx['tables'][0], gp['tables'][0]
    assert tx['cols'] == tp['cols']
    for lv in ('ebonus1', 'ebonus2', 'ebonus3', 'ebonus4'):
        if lv not in tx['rows']:
            tx['rows'].append(lv)
            tx['grid'].append(list(tp['grid'][tp['rows'].index(lv)]))
    # PSP story levels (build_psp_story.py), inserted before the challenge rows: the challenge
    # list is the last 4 rows of ~~Levels, the chapter-select row numbers are all below 60.
    first_bonus = tx['rows'].index('ebonus1')
    for k, (psp, new) in enumerate(STORY_LEVELS):
        if new not in tx['rows']:
            tx['rows'].insert(first_bonus + k, new)
            tx['grid'].insert(first_bonus + k, list(tp['grid'][tp['rows'].index(psp)]))
    # Story copies (read instead of the originals while the save is a New Game one, see
    # patch_unlock.py SEL/SELCS/PUSHCS/SELTID): the original select / team / greyed-out values,
    # so New Game plays the original fixed story pairs (Player1/Player2 are kept in every row;
    # the game only reads them when the level has neither charSel nor teamID).
    for col in STORY_COLS.values():
        tx['cols'].append(col)
        for row in tx['grid']:
            row.append(None)
    c = {name: i for i, name in enumerate(tx['cols'])}
    for r, row in zip(tx['rows'], tx['grid']):
        for src, dst in STORY_COLS.items():
            row[c[dst]] = row[c[src]]
        ep = episode_of(r)
        sel = EPISODES.get(ep, {}) if ep in EPISODES else EXTRA_ROWS
        if ep not in EPISODES and r not in EXTRA_ROWS:
            continue
        row[c['teamID']] = 0.0
        if r in sel:
            row[c['charSel']] = 'c1,2'
            row[c['charExclude']] = sel[r]
    return gdt.build(gx)


def main():
    xs, ps, out = sys.argv[1:4]
    ex = [(n, b) for n, b, _ in lmp.read(xs)]
    ep = dict((n, b) for n, b, _ in lmp.read(ps))
    lmp.build([(n, build(b, ep['levels.gdt']) if n == 'levels.gdt' else b) for n, b in ex], out)
    print('gamedata ->', out)


if __name__ == '__main__':
    main()
