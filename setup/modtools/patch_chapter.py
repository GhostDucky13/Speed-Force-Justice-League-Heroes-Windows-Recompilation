#!/usr/bin/env python3
"""
patch_chapter.py - Chapter Select for the Xbox frontend.lmp (on top of patch_menus frontend_challenge).

The Challenge Missions screen becomes a 4-page list (down past the last item / up past the
first flips the page; the challenge page wraps onto itself, the three episode pages wrap among
themselves):
  page 0  the four challenge missions (as before)
  page 1  Episode 1-4    page 2  Episode 5-8    page 3  Episode 9-11
(episodes are labelled with their first level's name from the game text).
Picking an episode remembers its ~~Levels row (chapterRow) and enters the normal New Game
flow (save slot -> players -> difficulty). The difficulty screen sends, after the usual
CMD_START_GAME, "CMD_WARP2LEVEL,<row>": the game starts at that episode, and the XBE patch
(patch_unlock.py build_maxheroes) maxes every hero on WARP2LEVEL.

A completed save picked in Load Saved Game ("Completed Game", which the game refuses to load)
starts Chapter Select's Episode 1 instead: save slot -> players -> difficulty -> Episode 1, with
every hero maxed and the character selector.

Usage: python patch_chapter.py frontend.lmp frontend_patched.lmp
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp  # noqa: E402
import patch_menus  # noqa: E402
import swfedit as E  # noqa: E402
from swfedit import push, setvar, uistring, set_target, goto_frame, goto_label, GET, SET, ADD, SUB, MUL, EQ, NOT, \
    TRACE, PLAY, SADD, SETPROP, if_var_eq  # noqa: E402

PAGES = [
    [('ebonus1', None), ('ebonus2', None), ('ebonus3', None), ('ebonus4', None)],
    [('e1l1a', 0), ('e2l1', 7), ('e3l1', 13), ('e4l1', 18)],
    [('e5l1', 24), ('e6l1', 28), ('e7l1', 30), ('e8l1', 39)],
    [('e9l1', 44), ('e10l1', 52), ('e11l1', 56)],
]
NONE = '-1'


def page_text():
    """Set m0..m3 texts, m3 visibility and nItems for the current chPage."""
    items = []
    for p, entries in enumerate(PAGES):
        body = [uistring(f'/Missions/m{i}', key) for i, (key, _) in enumerate(entries)]
        visible = '1' if len(entries) == 4 else '0'
        body.append(push('/Missions/m3', 7.0, visible) + SETPROP)       # _visible
        body.append(setvar('nItems', str(len(entries))))
        items += E.if_var_eq('chPage', str(p), body)
    return items


def selector_to_fevar():
    return push('/Missions/Selector', 1.0, 'feVar') + GET + push('26') + MUL + SETPROP   # _y = feVar*26


def chapter_select_items(end_label):
    """On the missions screen select: if chPage != 0 start the chosen episode as a new game."""
    body = []
    for p, entries in enumerate(PAGES[1:], start=1):
        for i, (key, row) in enumerate(entries):
            body += E.if_var_eq('chPage', str(p), E.if_var_eq('feVar', str(i), [setvar('chapterRow', str(row))]))
    body += [setvar('bChallenge', '0'), setvar('prevItem3', '0'), setvar('prevItem4', '0'),
             setvar('mode', 'SAVE'), goto_frame(36) + PLAY, ('jump', end_label)]
    skip = E._Lbl.new()
    return [push('chPage') + GET + push('0') + EQ, ('if', skip)] + body + [('label', skip)]


def apply(data):
    data = patch_menus.apply('frontend_challenge', data)
    sw = E.SWF(data)
    # 0. Continued Play is replaced by Chapter Select (update 13): the frontend starts with
    #    gameWon = 1, so item 1 is never greyed/skipped (gameWon only gates item 1, Challenge
    #    Missions and the two top difficulties, the last two already unlocked).
    sw.edit('/ DoAction@0xf4', [(692, 711, [setvar('gameWon', '1')])])
    # 1. main menu init (frame 15): no chapter chosen; item 1 text = "Chapter Select"
    sw.edit('/ DoAction@0x442e9', [(279422, 279422, [setvar('chapterRow', NONE), setvar('chStart', '0'),
                                                      uistring('FrontEnd/menu1', 'chsel')])])
    # 1b. main menu select: item 1 opens the missions screen on the first episode page,
    #     Challenge Missions (item 6) on the challenge page
    sw.edit('/ button43 cond 0xc200', [
        (282249, 282255, [setvar('bChallenge', '1'), setvar('chStart', '1'), goto_frame(203) + PLAY]),
        (282629, 282629, [setvar('chStart', '0')]),
    ])
    # 2. missions screen init: feVar = 0, chPage = chStart, page texts (replaces the fixed names)
    sw.edit('/ DoAction@0x6f202', [
        (455194, 455216, [setvar('feVar', '0'), push('chPage', 'chStart') + GET + SET]),
        (455261, 455461, page_text()),
    ])
    # 3. down at the last item: next page (instead of wrapping on the same page)
    # (update 14) the challenge page (0) wraps onto itself, the episode pages 1-3 among themselves
    down = E.if_var_eq('chPage', '0', [setvar('chPage', '9')])
    down += [push('chPage') + push('chPage') + GET + push('1') + ADD + SET]
    down += E.if_var_eq('chPage', '4', [setvar('chPage', '1')])
    down += E.if_var_eq('chPage', '10', [setvar('chPage', '0')])
    down += page_text() + [setvar('feVar', '0'), push('/Missions/Selector', 1.0, '0') + SETPROP, ('jump', 456477)]
    sw.edit('/ button193 cond 0x1e00', [(456298, 456358, down)])
    # 4. up at the first item: previous page, select its last item
    up = E.if_var_eq('chPage', '0', [setvar('chPage', '9')])
    up += [push('chPage') + push('chPage') + GET + push('1') + SUB + SET]
    up += E.if_var_eq('chPage', '0', [setvar('chPage', '3')])
    up += E.if_var_eq('chPage', '8', [setvar('chPage', '0')])
    up += page_text() + [push('feVar') + push('nItems') + GET + push('1') + SUB + SET, selector_to_fevar(), ('jump', 456039)]
    sw.edit('/ button193 cond 0x1c00', [(455836, 455922, up)])
    # 5. select on the missions screen: episodes start a new game (after the button sound)
    sw.edit('/ button193 cond 0xc200', [(456672, 456672, chapter_select_items(456806))])
    # 6. difficulty screen start: warp to the chosen episode after CMD_START_GAME
    skip = E._Lbl.new()
    warp = [push('chapterRow') + GET + push(NONE) + EQ, ('if', skip),
            push('CMD_WARP2LEVEL,', 'chapterRow') + GET + SADD + TRACE, setvar('chapterRow', NONE), ('label', skip)]
    sw.edit('/ button119 cond 0xc200', [(333814, 333814, warp)])
    # 7. Load Saved Game on a completed save (gs168f): instead of "Completed game cannot be
    #    loaded" (gs185j), start Episode 1 the Chapter Select way. Inserted at the start of the
    #    completed-save branch; 423255 is the branch's common exit.
    done = E._Lbl.new()
    completed = [push('gameName') + GET + push('gs168f') + b'\x13' + NOT, ('if', done),
                 set_target('/Sounds') + goto_label('button') + set_target(''),
                 setvar('chapterRow', '0'), setvar('bChallenge', '0'), setvar('prevItem3', '0'),
                 setvar('prevItem4', '0'), setvar('viewSavedGame', '0'), setvar('mode', 'SAVE'),
                 goto_frame(36) + PLAY, ('jump', 423255), ('label', done)]
    sw.edit('/ button158 cond 0xc200', [(422644, 422644, completed)])
    return sw.build()


def main():
    src, dst = sys.argv[1:3]
    entries = lmp.read(src)
    if [n.lower() for n, _, _ in entries] != ['frontend.swb']:
        sys.exit('expected an archive containing only frontend.swb')
    lmp.build([(entries[0][0], apply(entries[0][1]))], dst)
    print(f'chapter select: patched -> {dst}')


if __name__ == '__main__':
    main()
