#!/usr/bin/env python3
"""
speedforce_linux.py - Speed Force for Linux: the Speed Force Builder and the launcher in one
program, shipped as an AppImage (see linux/make_appdir.py).

  Builder   install folder, your Xbox and PSP dumps, optional Xbox saves; then it copies the
            build kit and runs setup/sf_install.py with the AppImage's own LLVM-MinGW, CMake,
            Ninja and Python, which cross-compile the same Windows SpeedForce.exe as on Windows.
  Launcher  Play, the main settings (config/config.toml, the file the in-game F10 menu uses),
            save slots and Xbox save import, how the game is run (Proton, Wine or the Wine
            inside the AppImage, with DXVK), the update check and uninstalling.

The game is a Windows program, so it runs through a compatibility layer: Steam's Proton when
it is installed, else the system's Wine, else the portable Wine in the AppImage.

  speedforce_linux.py                 the builder until the game is built, then the launcher
  speedforce_linux.py --setup         the builder
  speedforce_linux.py --play          start the game directly ("Speed Force (game only)")
  speedforce_linux.py --xbox X --psp P [--dir D] [--saves S]   fill the builder in
"""
import base64
import glob
import io
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
from tkinter import filedialog, messagebox

VERSION = '2.0.0'
REPO = 'GhostDucky13/Speed-Force'

HERE = os.path.dirname(os.path.abspath(__file__))
SHARE = os.path.dirname(HERE)                       # usr/share/speedforce in the AppImage
KIT = os.path.join(SHARE, 'kit')
TOOLS = os.path.join(SHARE, 'tools')
BUNDLED_WINE = os.path.join(SHARE, 'wine', 'bin', 'wine')
DXVK = os.path.join(SHARE, 'dxvk')

HOME = os.path.expanduser('~')
CFG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.join(HOME, '.config'), 'speedforce')
DATA_DIR = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local', 'share'), 'speedforce')
STATE_FILE = os.path.join(CFG_DIR, 'linux.json')
APPS_DIR = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local', 'share'), 'applications')
ICON_DIR = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local', 'share'),
                        'icons', 'hicolor', '256x256', 'apps')
NEED_GB = 9

# ---------------------------------------------------------------- colours (as on Windows)
BG, BG2, CARD, CARD2 = '#0a0e1c', '#0e1326', '#141b30', '#1a223c'
BORDER, INPUT, HOVER = '#26304e', '#0c1121', '#222c4c'
TEXT, SUB, DIM = '#ecf0fa', '#8c98b6', '#5c6886'
ACCENT, ACCENT2, ACCENTHI = '#ffc428', '#ff8c1e', '#ffd65c'
OK, BAD = '#3ad29f', '#ff5c5c'
DARK = '#12141e'


def load_state():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=2)


def fmt_time(s):
    s = int(s + 0.5)
    return f'{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60}:{s % 60:02d}'


# ---------------------------------------------------------------- settings (config/config.toml)
CHOICES = [  # key, values, labels, quoted, default, name, description
    ('render.scale', ['1', '2', '3', '4'], ['1x (720p)', '2x (1440p)', '3x (2160p)', '4x (2880p)'], False, '4',
     'Resolution scale', 'The game is drawn at 720p times this, then scaled to your screen.'),
    ('display.output', ['native', '1080', '1440', '2160'], ['Native (screen)', '1080p', '1440p', '4K'], True, 'native',
     'Output resolution', 'The resolution of the picture sent to your screen.'),
    ('present.fullscreen', ['true', 'false'], ['Fullscreen', 'Window'], False, 'true',
     'Display', 'Fullscreen or a window (F11 switches in game).'),
    ('frame.rate', ['60', '120', '144', '240', 'monitor'], ['Off (60, original)', '120', '144', '240', 'Match monitor'],
     True, 'monitor', 'Speed Force', "Frame generation: new frames between the game's own, up to your monitor's rate."),
    ('upscale.mode', ['off', 'dlss', 'fsr', 'xess'], ['Off', 'NVIDIA DLSS', 'AMD FSR', 'Intel XeSS'], True, 'off',
     'Upscaler', 'DLSS, FSR or XeSS when the resolution scale is below your screen size (needs Proton or vkd3d).'),
    ('render.aa', ['off', 'fxaa', 'fxaa_high', 'taa'], ['Off', 'FXAA', 'FXAA (high)', 'TAA'], True, 'off',
     'Anti-aliasing', 'Smooths jagged edges.'),
    ('render.aniso', ['1', '2', '4', '8', '16'], ['Off', '2x', '4x', '8x', '16x'], False, '16',
     'Texture filtering', 'Sharper textures at an angle.'),
    ('input.glyphs', ['auto', 'xbox', 'playstation', 'nintendo', 'gamecube'],
     ['Automatic', 'Xbox', 'PlayStation', 'Nintendo', 'GameCube'], True, 'auto',
     'Button icons', 'The button prompts shown in game.'),
    ('overlay.stats', ['false', 'true'], ['Hidden', 'Shown'], False, 'false',
     'FPS counter', 'Shows the frame rate in a corner.'),
]


class Config:
    """config.toml as lines; only "key = value" lines inside [section]s are touched."""

    def __init__(self, path):
        self.path = path
        self.lines = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                self.lines = f.read().splitlines()
        except OSError:
            self.lines = []

    def _find(self, sec, key):
        cur, sec_line = '', -1
        for i, l in enumerate(self.lines):
            s = l.strip()
            if s.startswith('['):
                cur = s[1:s.find(']')]
                if cur == sec:
                    sec_line = i
                continue
            if cur == sec:
                k = s.split('=', 1)[0].strip()
                if k == key and '=' in s:
                    return i, sec_line
        return -1, sec_line

    def get(self, full):
        sec, key = full.split('.', 1)
        i, _ = self._find(sec, key)
        if i < 0:
            return None
        v = self.lines[i].split('=', 1)[1].split('#')[0].strip()
        return v.strip('"')

    def set(self, full, value, quoted):
        sec, key = full.split('.', 1)
        line = f'{key} = "{value}"' if quoted else f'{key} = {value}'
        i, sl = self._find(sec, key)
        if i >= 0:
            self.lines[i] = line
        elif sl >= 0:
            self.lines.insert(sl + 1, line)
        else:
            if self.lines and self.lines[-1].strip():
                self.lines.append('')
            self.lines += [f'[{sec}]', line]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(self.lines) + '\n')


# ---------------------------------------------------------------- running the game
def steam_roots():
    roots = [os.path.join(HOME, p) for p in ('.steam/steam', '.steam/root', '.local/share/Steam',
                                             '.var/app/com.valvesoftware.Steam/data/Steam')]
    seen, out = set(), []
    for r in roots:
        if os.path.isdir(r):
            rr = os.path.realpath(r)
            if rr not in seen:
                seen.add(rr)
                out.append(rr)
    return out


def find_protons():
    """[(name, path to the proton script, steam root)], newest first."""
    found = []
    for root in steam_roots():
        for pat in ('steamapps/common/Proton*/proton', 'compatibilitytools.d/*/proton'):
            for p in glob.glob(os.path.join(root, pat)):
                found.append((os.path.basename(os.path.dirname(p)), p, root))
    for p in glob.glob('/usr/share/steam/compatibilitytools.d/*/proton'):
        found.append((os.path.basename(os.path.dirname(p)), p, steam_roots()[0] if steam_roots() else HOME))

    def key(item):
        name = item[0].lower()
        exp = 'experimental' in name
        nums = [int(x) for x in ''.join(c if c.isdigit() else ' ' for c in name).split()[:3]]
        return (not exp, nums)
    return sorted(found, key=key, reverse=True)


def system_wine():
    return shutil.which('wine') or shutil.which('wine64')


RUNNERS = ['auto', 'proton', 'wine', 'bundled']
RUNNER_LABELS = {'auto': 'Automatic', 'proton': 'Steam Proton', 'wine': 'System Wine', 'bundled': 'Built-in Wine'}


def pick_runner(choice):
    """('proton', script, root) | ('wine', wine binary) | (None, reason)."""
    protons = find_protons()
    if choice in ('auto', 'proton') and protons:
        return ('proton', protons[0][1], protons[0][2], protons[0][0])
    if choice == 'proton':
        return (None, "Steam's Proton isn't installed (install it from Steam: Library > Tools).")
    if choice in ('auto', 'wine') and system_wine():
        return ('wine', system_wine(), 'System Wine')
    if choice == 'wine':
        return (None, "Wine isn't installed on this system.")
    if os.path.exists(BUNDLED_WINE):
        return ('wine', BUNDLED_WINE, 'Built-in Wine')
    return (None, 'No Proton or Wine was found.')


DLL_OVERRIDES = 'd3d11,d3d10core,dxgi,d3d12,d3d12core=n,b;winemenubuilder.exe=d'
# SPEEDFORCE_WINED3D=1: Wine's own Direct3D (OpenGL) instead of DXVK, for a PC without Vulkan.
WINED3D = os.environ.get('SPEEDFORCE_WINED3D') == '1'


def prepare_wine(wine, prefix, say=lambda m: None):
    """A Wine prefix for Speed Force, with DXVK and vkd3d-proton (Direct3D on Vulkan)."""
    overrides = 'winemenubuilder.exe=d' if WINED3D else DLL_OVERRIDES
    env = dict(os.environ, WINEPREFIX=prefix, WINEDEBUG='-all', WINEDLLOVERRIDES=overrides + ';mscoree,mshtml=')
    wdir = os.path.dirname(wine)
    if wine == BUNDLED_WINE:
        env['PATH'] = wdir + os.pathsep + env.get('PATH', '')
    sys32 = os.path.join(prefix, 'drive_c', 'windows', 'system32')
    if not os.path.isdir(sys32):
        say('Preparing Wine for Speed Force (first start only, about a minute)...')
        os.makedirs(prefix, exist_ok=True)
        subprocess.run([wine, 'wineboot', '-u'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=600)
        server = os.path.join(wdir, 'wineserver')
        subprocess.run([server if os.path.exists(server) else 'wineserver', '-w'], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    if os.path.isdir(sys32) and os.path.isdir(DXVK) and not WINED3D:
        for dll in os.listdir(DXVK):
            dst = os.path.join(sys32, dll)
            src = os.path.join(DXVK, dll)
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copy2(src, dst)
    return env


def launch_game(install, choice, say=lambda m: None):
    """Start SpeedForce.exe; returns (Popen, how) or raises RuntimeError."""
    exe = os.path.join(install, 'SpeedForce.exe')
    if not os.path.exists(exe):
        raise RuntimeError("Speed Force isn't built in this folder. Run the builder (Speed Force > About > Rebuild).")
    r = pick_runner(choice)
    if r[0] is None:
        raise RuntimeError(r[1])
    log = open(os.path.join(install, 'SpeedForce-linux.log'), 'w', encoding='utf-8')
    if r[0] == 'proton':
        _, script, root, name = r
        data = os.path.join(DATA_DIR, 'proton')
        os.makedirs(data, exist_ok=True)
        env = dict(os.environ, STEAM_COMPAT_DATA_PATH=data, STEAM_COMPAT_CLIENT_INSTALL_PATH=root,
                   PROTON_ENABLE_NVAPI='1', SteamGameId='speedforce', SteamAppId='0')
        py = shutil.which('python3') or sys.executable
        p = subprocess.Popen([py, script, 'run', exe], cwd=install, env=env, stdout=log, stderr=log,
                             start_new_session=True)
        return p, name
    _, wine, name = r
    env = prepare_wine(wine, os.path.join(DATA_DIR, 'wine'), say)
    env['WINEDEBUG'] = '-all'
    env['DXVK_LOG_LEVEL'] = 'none'
    env['VKD3D_DEBUG'] = 'none'
    p = subprocess.Popen([wine, exe], cwd=install, env=env, stdout=log, stderr=log, start_new_session=True)
    return p, name


# ---------------------------------------------------------------- desktop integration
def appimage_path():
    return os.environ.get('APPIMAGE') or os.path.abspath(sys.argv[0])


def desktop_dir():
    try:
        d = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, timeout=5).stdout.strip()
        if d and os.path.isdir(d):
            return d
    except (OSError, subprocess.SubprocessError):
        pass
    d = os.path.join(HOME, 'Desktop')
    return d if os.path.isdir(d) else None


def write_desktop_entries(desktop_shortcut):
    os.makedirs(APPS_DIR, exist_ok=True)
    os.makedirs(ICON_DIR, exist_ok=True)
    shutil.copy2(os.path.join(HERE, 'icon.png'), os.path.join(ICON_DIR, 'speedforce.png'))
    exe = appimage_path().replace('"', '\\"')
    entries = {
        'speedforce.desktop': ('Speed Force', 'Justice League Heroes, native recompilation: launcher', f'"{exe}"'),
        'speedforce-game.desktop': ('Speed Force (game only)', 'Justice League Heroes, native recompilation',
                                    f'"{exe}" --play'),
    }
    for fn, (name, comment, cmd) in entries.items():
        text = ('[Desktop Entry]\nType=Application\n'
                f'Name={name}\nComment={comment}\nExec={cmd}\nIcon=speedforce\n'
                'Terminal=false\nCategories=Game;\nStartupWMClass=speedforce\n')
        with open(os.path.join(APPS_DIR, fn), 'w', encoding='utf-8') as f:
            f.write(text)
        if fn == 'speedforce.desktop' and desktop_shortcut and desktop_dir():
            p = os.path.join(desktop_dir(), 'speedforce.desktop')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
            os.chmod(p, 0o755)
    try:
        subprocess.run(['update-desktop-database', APPS_DIR], timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def remove_desktop_entries():
    for p in (os.path.join(APPS_DIR, 'speedforce.desktop'), os.path.join(APPS_DIR, 'speedforce-game.desktop'),
              os.path.join(ICON_DIR, 'speedforce.png')):
        try:
            os.remove(p)
        except OSError:
            pass
    if desktop_dir():
        try:
            os.remove(os.path.join(desktop_dir(), 'speedforce.desktop'))
        except OSError:
            pass


def open_path(p):
    try:
        subprocess.Popen(['xdg-open', p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def pick_file(title, folder=False, initial=''):
    """The desktop's own dialog when there is one (zenity / kdialog), else Tk's."""
    try:
        if shutil.which('zenity'):
            cmd = ['zenity', '--file-selection', '--title', title] + (['--directory'] if folder else [
                '--file-filter', 'Disc images | *.iso *.xiso *.ISO', '--file-filter', 'All files | *'])
            if initial:
                cmd += ['--filename', initial.rstrip('/') + '/']
            r = subprocess.run(cmd, capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else ''
        if shutil.which('kdialog'):
            cmd = ['kdialog', '--title', title] + (['--getexistingdirectory', initial or HOME] if folder else
                                                   ['--getopenfilename', initial or HOME, '*.iso *.xiso|Disc images'])
            r = subprocess.run(cmd, capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else ''
    except OSError:
        pass
    if folder:
        return filedialog.askdirectory(title=title, initialdir=initial or HOME) or ''
    return filedialog.askopenfilename(title=title, initialdir=initial or HOME,
                                      filetypes=[('Disc images', '*.iso *.xiso *.ISO'), ('All files', '*')]) or ''


# ---------------------------------------------------------------- the UI toolkit (a Canvas)
class UI:
    """A Canvas painted like the Windows builder. Tk's own X11 fonts have no anti-aliasing, so
    all text and the round status icons are drawn with Pillow (FreeType) from the bundled
    Inter font and placed as images."""
    FONT_FILES = {'regular': 'Inter-Regular.otf', 'semibold': 'Inter-SemiBold.otf',
                  'display': 'InterDisplay-Bold.otf', 'mono': 'DejaVuSansMono.ttf'}

    def __init__(self, root, w, h):
        from PIL import Image, ImageDraw, ImageFont
        self.PIL = (Image, ImageDraw, ImageFont)
        self.root = root
        self.s = max(1.0, min(2.5, root.winfo_fpixels('1i') / 96.0))
        self.W, self.H = w, h
        root.geometry(f'{self.px(w)}x{self.px(h)}')
        root.resizable(False, False)
        root.configure(bg=BG)
        self.c = tk.Canvas(root, width=self.px(w), height=self.px(h), bg=BG, highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.f = {   # name: (font file, size in logical px)
            'title': ('display', 28), 'h1': ('display', 22), 'h2': ('semibold', 16), 'body': ('regular', 14),
            'bold': ('semibold', 14), 'small': ('regular', 12), 'mono': ('mono', 12), 'huge': ('display', 40),
            'glyph': ('semibold', 13), 'arrow': ('semibold', 22),
        }
        self.tkfont = ('Helvetica', -self.px(14))         # for the EDIT fields (Tk's own text)
        self.monofont = ('Courier', -self.px(12))
        self._fonts, self._imgs, self._items = {}, {}, {}
        self.hot = None
        self.handlers = {}
        self.n = 0
        self.images = {}

    def _font(self, name):
        kind, size = self.f[name]
        key = (kind, size)
        if key not in self._fonts:
            ImageFont = self.PIL[2]
            path = os.path.join(HERE, 'fonts', self.FONT_FILES[kind])
            try:
                self._fonts[key] = ImageFont.truetype(path, self.px(size))
            except OSError:
                self._fonts[key] = ImageFont.load_default(self.px(size))
        return self._fonts[key]

    def _photo(self, im):
        b = io.BytesIO()
        im.save(b, 'PNG')
        return tk.PhotoImage(data=base64.b64encode(b.getvalue()))

    def _text_image(self, t, font, fill, width):
        key = (t, font, fill, width)
        if key in self._imgs:
            return self._imgs[key]
        Image, ImageDraw, _ = self.PIL
        f = self._font(font)
        asc, desc = f.getmetrics()
        lines = []
        for para in t.split('\n'):
            if not width:
                lines.append(para)
                continue
            cur = ''
            for word in para.split(' '):
                trial = (cur + ' ' + word) if cur else word
                if f.getlength(trial) <= self.px(width) or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        lh = asc + desc
        step = int(lh * 1.22) if len(lines) > 1 else lh
        w = max(1, int(max(f.getlength(l) for l in lines)) + 2)
        h = step * (len(lines) - 1) + lh
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, l in enumerate(lines):
            d.text((0, i * step), l, font=f, fill=fill)
        ph = self._photo(im)
        if len(self._imgs) > 3000:
            self._imgs.clear()
        self._imgs[key] = ph
        return ph

    def recolor(self, item, fill):
        t, font, width = self._items.get(item, (None, None, None))
        if t is not None:
            self.c.itemconfigure(item, image=self._text_image(t, font, fill, width))

    def px(self, v):
        return int(round(v * self.s))

    def clear(self):
        self.c.delete('all')
        self.handlers.clear()
        self.hot = None
        self.n = 0

    def round_rect(self, x, y, w, h, r, fill, outline='', tags=()):
        x, y, w, h, r = self.px(x), self.px(y), self.px(w), self.px(h), self.px(r)
        r = min(r, h // 2, w // 2)
        pts = [x + r, y, x + w - r, y, x + w, y, x + w, y + r, x + w, y + h - r, x + w, y + h,
               x + w - r, y + h, x + r, y + h, x, y + h, x, y + h - r, x, y + r, x, y]
        return self.c.create_polygon(pts, smooth=True, splinesteps=12, fill=fill, outline=outline, tags=tags)

    def text(self, x, y, t, font='body', fill=TEXT, anchor='nw', width=None, tags=()):
        img = self._text_image(str(t), font, fill, width)
        item = self.c.create_image(self.px(x), self.px(y), image=img, anchor=anchor, tags=tags)
        self._items[item] = (str(t), font, width)
        return item

    def line(self, x0, y0, x1, y1, fill, w=1):
        return self.c.create_line(self.px(x0), self.px(y0), self.px(x1), self.px(y1), fill=fill, width=self.px(w))

    def _tag(self):
        self.n += 1
        return f'w{self.n}'

    def clickable(self, tag, on_click, on_hover=None):
        self.handlers[tag] = on_click
        self.c.tag_bind(tag, '<Enter>', lambda e: self._hover(tag, True, on_hover))
        self.c.tag_bind(tag, '<Leave>', lambda e: self._hover(tag, False, on_hover))
        self.c.tag_bind(tag, '<ButtonRelease-1>', lambda e: self.root.after(1, on_click))

    def _hover(self, tag, on, cb):
        self.c.configure(cursor='hand2' if on else '')
        if cb:
            cb(on)

    def button(self, x, y, w, h, label, on_click, style=0, enabled=True):
        """style 0 secondary, 1 primary (gold), 2 ghost, 3 danger."""
        tag = self._tag()
        if style == 1:
            fill, hov, tc = (ACCENT, ACCENTHI, DARK) if enabled else ('#46402a', '#46402a', DIM)
            outline = ''
        elif style == 2:
            fill, hov, tc, outline = BG, HOVER, SUB if enabled else DIM, ''
        elif style == 3:
            fill, hov, tc, outline = '#461c24', '#782830', TEXT, '#8c343c'
        else:
            fill, hov, tc, outline = CARD2, HOVER, TEXT if enabled else DIM, BORDER
        bg = self.round_rect(x, y, w, h, 8, fill, outline, tags=(tag,))
        self.text(x + w / 2, y + h / 2, label, 'bold', tc, anchor='center', tags=(tag,))
        if enabled:
            self.clickable(tag, on_click, lambda on: self.c.itemconfigure(bg, fill=hov if on else fill))
        return tag

    def link(self, x, y, label, on_click, font='body'):
        tag = self._tag()
        t = self.text(x, y, label, font, SUB, tags=(tag,))
        self.clickable(tag, on_click, lambda on: self.recolor(t, ACCENTHI if on else SUB))

    def check(self, x, y, label, on, on_click):
        tag = self._tag()
        box = self.round_rect(x, y, 20, 20, 5, ACCENT if on else INPUT, '' if on else BORDER, tags=(tag,))
        if on:
            self.text(x + 10, y + 10, '✓', 'glyph', DARK, anchor='center', tags=(tag,))
        self.text(x + 30, y + 10, label, 'body', TEXT, anchor='w', tags=(tag,))
        # an invisible strip makes the whole row clickable
        self.c.create_rectangle(self.px(x), self.px(y), self.px(x + 520), self.px(y + 20), outline='', fill='',
                                tags=(tag,))
        self.clickable(tag, on_click, None if on else lambda o: self.c.itemconfigure(box, outline=SUB if o else BORDER))

    def _icon(self, state, phase=0):
        key = ('icon', state, phase)
        if key in self._imgs:
            return self._imgs[key]
        Image, ImageDraw, _ = self.PIL
        k = 4
        n = self.px(24)
        im = Image.new('RGBA', (n * k, n * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c, r = n * k / 2, self.px(10) * k
        lw = max(1, int(self.px(1.6) * k))
        box = [c - r, c - r, c + r, c + r]
        if state == 2:
            d.ellipse(box, outline='#3a3218', width=int(self.px(2.2) * k))
            d.arc(box, start=phase, end=phase + 110, fill=ACCENT, width=int(self.px(2.4) * k))
        else:
            col = {1: OK, 3: BAD, 4: ACCENT}.get(state, BORDER)
            fill = {1: '#123a32', 3: '#3e1a22', 4: '#3e3418'}.get(state)
            d.ellipse(box, outline=col, width=lw, fill=fill)
            w2 = int(self.px(2) * k)
            u = r / 10
            if state == 1:
                d.line([(c - 4.5 * u, c + 0.2 * u), (c - 1.2 * u, c + 3.5 * u), (c + 5 * u, c - 3.5 * u)],
                       fill=col, width=w2, joint='curve')
            elif state == 3:
                d.line([(c - 4 * u, c - 4 * u), (c + 4 * u, c + 4 * u)], fill=col, width=w2)
                d.line([(c + 4 * u, c - 4 * u), (c - 4 * u, c + 4 * u)], fill=col, width=w2)
            elif state == 4:
                d.line([(c, c - 4.5 * u), (c, c + 1 * u)], fill=col, width=w2)
                d.ellipse([c - 1.3 * u, c + 3.2 * u, c + 1.3 * u, c + 5.8 * u], fill=col)
        ph = self._photo(im.resize((n, n), Image.LANCZOS))
        self._imgs[key] = ph
        return ph

    def status(self, x, y, state):
        """1 done, 2 running, 3 failed, 4 warning, 0 waiting (x, y = the centre)."""
        phase = int(time.time() * 360) % 360 // 15 * 15 if state == 2 else 0
        self.c.create_image(self.px(x), self.px(y), image=self._icon(state, phase), anchor='center')

    def progress(self, x, y, w, h, frac, c0=ACCENT2, c1=ACCENT):
        self.round_rect(x, y, w, h, h / 2, CARD2)
        if frac > 0:
            fw = max(h, w * min(1.0, frac))
            # a two-colour gradient in a few steps
            steps = 12
            for i in range(steps):
                a = i / steps
                col = '#%02x%02x%02x' % tuple(int(int(c0[k:k + 2], 16) + (int(c1[k:k + 2], 16) - int(c0[k:k + 2], 16)) * a)
                                              for k in (1, 3, 5))
                sx = x + fw * i / steps
                self.round_rect(sx, y, fw / steps + (h if i < steps - 1 else 0), h, h / 2 if i in (0, steps - 1) else 0, col)
            self.round_rect(x + fw - h, y, h, h, h / 2, c1)

    def entry(self):
        e = tk.Entry(self.root, bg=INPUT, fg=TEXT, insertbackground=TEXT, relief='flat', bd=0,
                     highlightthickness=0, font=self.tkfont, disabledbackground=INPUT, disabledforeground=DIM)
        return e

    def place_entry(self, e, x, y, w, h=40):
        self.round_rect(x, y, w, h, 8, INPUT, BORDER)
        self.c.create_window(self.px(x + 12), self.px(y + h / 2), window=e, anchor='w', width=self.px(w - 24),
                             height=self.px(22))

    def image(self, name, path, w, h):
        key = (name, w, h)
        if key not in self.images:
            try:
                from PIL import Image
                im = Image.open(path).convert('RGBA').resize((self.px(w), self.px(h)), Image.LANCZOS)
                b = io.BytesIO()
                im.save(b, 'PNG')
                self.images[key] = tk.PhotoImage(data=base64.b64encode(b.getvalue()))
            except Exception:
                self.images[key] = None
        return self.images[key]

    def draw_image(self, name, path, x, y, w, h):
        img = self.image(name, path, w, h)
        if img:
            self.c.create_image(self.px(x), self.px(y), image=img, anchor='nw')


# ---------------------------------------------------------------- the builder
STEPS = ['Copy the build tools', 'Check your dumps', 'Read both discs', 'Rebuild the mod', 'Place the game files',
         'Translate the game to C', 'Compile', 'Install', 'Clean up']
EXPECT = [20, 70, 30, 1100, 5, 420, 600, 15, 20]


class Builder:
    def __init__(self, root, args, on_done=None):
        self.root = root
        self.ui = UI(root, 980, 640)
        root.title(f'Speed Force Builder {VERSION}')
        self.on_done = on_done
        st = load_state()
        self.page = 0
        self.saves_on = bool(args.get('saves'))
        self.desktop = True
        self.e_dir, self.e_xbox, self.e_psp, self.e_saves = (self.ui.entry() for _ in range(4))
        self.e_dir.insert(0, args.get('dir') or st.get('install') or os.path.join(HOME, 'Games', 'Speed Force'))
        self.e_xbox.insert(0, args.get('xbox') or '')
        self.e_psp.insert(0, args.get('psp') or '')
        self.e_saves.insert(0, args.get('saves') or '')
        for e in (self.e_dir, self.e_xbox, self.e_psp, self.e_saves):
            e.bind('<KeyRelease>', lambda ev: self.redraw())
        self.log = []
        self.q = queue.Queue()
        self.building = False
        self.proc = None
        self.stop = False
        self.details = None
        self.render()
        root.protocol('WM_DELETE_WINDOW', self.close)

    # -- checks
    def checks(self):
        d = os.path.expanduser(self.e_dir.get().strip())
        x = os.path.expanduser(self.e_xbox.get().strip())
        p = os.path.expanduser(self.e_psp.get().strip())
        res = {}
        if not d.startswith('/'):
            res['dir'] = (0, 'Choose a folder, for example ~/Games/Speed Force.')
        elif os.path.exists(os.path.join(d, 'SpeedForce.exe')):
            res['dir'] = (1, 'Speed Force is already here: it is built again, your saves and settings stay.')
        else:
            res['dir'] = (1, 'Speed Force will be installed here.')
        probe = d
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        if probe and os.access(probe, os.W_OK):
            gb = shutil.disk_usage(probe).free / 1073741824
            res['space'] = (1 if gb >= NEED_GB else 0,
                            f'{gb:.0f} GB free here  -  needs about {NEED_GB} GB while building, about 5 GB afterwards.')
        else:
            res['space'] = (0, "You can't write to that folder.")

        def disc(path, kind):
            if not path:
                return (0, f'Choose your dump of the {"Xbox disc (.iso or .xiso)" if kind == "xbox" else "PSP disc (.iso)"}.')
            try:
                if os.path.getsize(path) < (50 << 20):
                    return (0, 'That file is too small to be a disc image.')
                with open(path, 'rb') as f:
                    if kind == 'xbox':
                        for off in (0, 0x18300000, 0x2080000, 0xFD90000):
                            f.seek(off + 32 * 2048)
                            if f.read(20) == b'MICROSOFT*XBOX*MEDIA':
                                return (1, 'Xbox game disc found. It is checked in full when the build starts.')
                        return (0, "This isn't an Xbox game disc image.")
                    f.seek(0x8000)
                    b = f.read(16)
                    if b[1:6] == b'CD001' and b[8:16] == b'PSP GAME':
                        return (1, 'PSP game disc (UMD) found. It is checked in full when the build starts.')
                    return (0, "This isn't a PSP game disc image.")
            except OSError:
                return (0, "That file can't be read.")
        res['xbox'] = disc(x, 'xbox')
        res['psp'] = disc(p, 'psp')
        return res

    # -- drawing
    def header(self):
        u = self.ui
        u.draw_image('icon', os.path.join(HERE, 'icon.png'), 40, 26, 56, 56)
        u.text(110, 24, 'Speed Force Builder', 'title')
        u.text(112, 64, 'Justice League Heroes, native recompilation, built from your own discs (Linux).', 'small', SUB)
        u.round_rect(600, 34, 340, 40, 20, BG2, BORDER)
        cur = self.page if self.page < 3 else (2 if (self.failed or self.cancelled) else 3)
        for i, name in enumerate(('Game files', 'Options', 'Build')):
            x = 606 + i * 111
            state = 1 if i < cur else (2 if i == cur else 0)
            if state == 2:
                u.round_rect(x, 39, 106, 30, 15, CARD2)
            if state == 1:
                u.status(x + 16, 54, 1)
            else:
                cx, cy, r = u.px(x + 16), u.px(54), u.px(9)
                u.c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ACCENT if state == 2 else CARD2, outline='')
                u.text(x + 16, 54, str(i + 1), 'small', DARK if state == 2 else SUB, anchor='center')
            u.text(x + 31, 54, name, 'small', TEXT if state else SUB, anchor='w')

    def check_line(self, y, ok, msg):
        self.ui.status(74, y + 10, 1 if ok else 3)
        self.ui.text(92, y + 10, msg, 'small', SUB if ok else BAD, anchor='w')

    def input_row(self, y, label, e, browse, enabled=True):
        u = self.ui
        u.text(64, y, label, 'bold', TEXT if enabled else DIM)
        u.place_entry(e, 64, y + 26, 700)
        e.configure(state='normal' if enabled else 'disabled')
        u.button(776, y + 26, 108, 40, 'Browse', browse, 0, enabled)

    def page_files(self):
        u = self.ui
        c = self.checks()
        u.round_rect(40, 104, 900, 452, 12, CARD, BORDER)
        self.input_row(124, 'Install folder', self.e_dir, lambda: self.browse(self.e_dir, True, 'Where to install Speed Force'))
        self.check_line(196, *c['dir'])
        self.check_line(220, *c['space'])
        self.input_row(260, 'Your Xbox disc image', self.e_xbox, lambda: self.browse(self.e_xbox, False, 'Your Xbox disc image'))
        self.check_line(332, *c['xbox'])
        self.input_row(372, 'Your PSP disc image', self.e_psp, lambda: self.browse(self.e_psp, False, 'Your PSP disc image'))
        self.check_line(444, *c['psp'])
        u.text(64, 488, 'This project contains no game files and no game code. Speed Force reads your own dumps (it never '
                        'changes them) and builds the game on this PC. Speed Force is built from the Xbox version, with '
                        'the extra characters and levels taken from the PSP version.', 'small', DIM, width=850)
        u.text(40, 598, f'Builder v{VERSION} for Linux', 'small', DIM, anchor='w')
        ready = all(v[0] for v in c.values())
        u.button(780, 576, 160, 44, 'Next', lambda: self.go(1), 1, ready)

    def page_options(self):
        u = self.ui
        u.round_rect(40, 104, 900, 250, 12, CARD, BORDER)
        u.text(64, 122, 'Your Xbox saves (optional)', 'h2')
        u.check(64, 160, 'I have saves from an Xbox to bring over', self.saves_on, self.toggle_saves)
        self.input_row(192, 'Saves folder', self.e_saves,
                       lambda: self.browse(self.e_saves, True, 'The folder with your Xbox saves (UDATA/57520001)'),
                       self.saves_on)
        u.text(64, 286, 'Choose the folder you copied from your Xbox (UDATA/57520001, or a folder that holds it). '
                        'Completed saves work too: they start Episode 1 the Chapter Select way. Saves already on this '
                        'PC are never overwritten.', 'small', SUB, width=840)
        u.round_rect(40, 370, 900, 182, 12, CARD, BORDER)
        u.text(64, 388, 'Shortcuts and playing', 'h2')
        u.check(64, 424, 'Put a Speed Force shortcut on the desktop', self.desktop, self.toggle_desktop)
        r = pick_runner('auto')
        how = {'proton': f'Steam {r[3] if r[0] == "proton" else "Proton"}', 'wine': r[-1]}.get(r[0], 'nothing found')
        u.text(64, 458, 'Your app menu gets "Speed Force" (the launcher: settings, updates and Play) and "Speed Force '
                        f'(game only)". The game is a Windows program and will run with: {how}. Proton or Wine is used '
                        'when you have one; otherwise the Wine inside this AppImage is. The build takes about 20-40 '
                        'minutes; you can keep using your PC.', 'small', SUB, width=840)
        u.button(40, 576, 140, 44, 'Back', lambda: self.go(0), 0)
        u.button(740, 576, 200, 44, 'Build Speed Force', self.start, 1,
                 not self.saves_on or bool(self.e_saves.get().strip()))

    def eta(self):
        t = time.time()
        done_e = sum(EXPECT[:self.step])
        done_a = sum(self.dur[:self.step])
        ratio = min(3.0, max(0.4, done_a / done_e)) if done_e > 120 else 1.0
        rem = 0
        for i in range(self.step, len(STEPS)):
            e = EXPECT[i] * ratio
            if i == self.step:
                e = max(15, e - (t - self.t_step[i]))
            rem += e
        return rem

    def page_build(self):
        u = self.ui
        done = self.page == 3
        u.round_rect(40, 104, 900, 452, 12, CARD, BORDER)
        el = (self.t_end if done else time.time()) - self.t0
        if done and not self.failed and not self.cancelled:
            u.status(76, 142, 1)
            u.text(100, 124, 'Speed Force is ready', 'h1')
            u.text(100, 162, f'Built and installed in {fmt_time(el)}. Have fun!', 'small', SUB)
        elif done:
            u.status(76, 142, 4 if self.cancelled else 3)
            u.text(100, 124, 'The build was cancelled' if self.cancelled else 'The build stopped', 'h1')
            u.text(100, 162, 'Nothing was finished. You can start it again.' if self.cancelled else
                   (self.error or 'See the log for the reason.'), 'small', SUB if self.cancelled else BAD, width=780)
        else:
            u.text(64, 124, f'Building Speed Force {VERSION}', 'h1')
            u.text(64, 162, 'You can keep using your PC. Closing this window stops the build.', 'small', SUB)
            u.text(916, 112, f'{int(self.frac * 100)}%', 'huge', TEXT, anchor='ne')
            u.text(916, 164, f'About {fmt_time(self.eta())} left' if self.frac > 0.02 else 'Estimating...', 'small',
                   SUB, anchor='ne')
        u.progress(64, 196, 852, 8, 1.0 if done and not self.failed and not self.cancelled else self.frac)
        if self.details:
            u.round_rect(64, 222, 852, 316, 10, BG2, BORDER)
            u.c.create_window(u.px(72), u.px(228), window=self.details, anchor='nw', width=u.px(836), height=u.px(304))
        else:
            u.round_rect(64, 222, 852, 316, 10, BG2, BORDER)
            for i, name in enumerate(STEPS):
                y = 226 + i * 34
                if i < self.step:
                    s = 1
                elif i == self.step and not done:
                    s = 2
                elif i == self.step and done:
                    s = 4 if self.cancelled else (3 if self.failed else 1)
                else:
                    s = 0
                if i:
                    u.line(80, y, 900, y, '#1e2740')
                u.status(90, y + 17, s)
                u.text(112, y + 17, name, 'bold' if s == 2 else 'body', SUB if s == 0 else TEXT, anchor='w')
                detail = {1: 'Done', 2: self.detail, 3: 'Stopped', 4: 'Cancelled'}.get(s, '')
                u.text(400, y + 17, detail[:60], 'small', BAD if s == 3 else SUB, anchor='w')
                if s:
                    d = self.dur[i] if s == 1 else ((self.t_end if done else time.time()) - self.t_step[i])
                    u.text(900, y + 17, fmt_time(d), 'small', TEXT if s == 2 else SUB, anchor='e')
        u.link(44, 590, 'Hide details' if self.details else 'Show details', self.toggle_details)
        if not done:
            u.button(800, 576, 140, 44, 'Cancel', self.cancel, 0)
        elif not self.failed and not self.cancelled:
            u.button(420, 576, 150, 44, 'Open folder', lambda: open_path(self.install), 2)
            u.button(580, 576, 170, 44, 'Open launcher', self.open_launcher, 0)
            u.button(760, 576, 180, 44, 'Play', self.play, 1)
        else:
            u.button(480, 576, 140, 44, 'Open log', lambda: open_path(os.path.join(self.install, 'install.log')), 0)
            u.button(630, 576, 150, 44, 'Try again', self.start, 0)
            u.button(790, 576, 150, 44, 'Close', self.close, 1)

    def render(self):
        self.ui.clear()
        if not hasattr(self, 'failed'):
            self.failed = self.cancelled = False
        self.header()
        [self.page_files, self.page_options, self.page_build, self.page_build][self.page]()

    def redraw(self):
        focus = self.root.focus_get()
        self.render()
        if focus:
            try:
                focus.focus_set()
            except tk.TclError:
                pass

    def go(self, page):
        self.page = page
        self.render()

    def browse(self, e, folder, title):
        cur = os.path.expanduser(e.get().strip())
        p = pick_file(title, folder, cur if folder else os.path.dirname(cur))
        if p:
            if e is self.e_dir and os.path.basename(p.rstrip('/')) != 'Speed Force':
                p = os.path.join(p, 'Speed Force')
            e.delete(0, 'end')
            e.insert(0, p)
        self.render()

    def toggle_saves(self):
        self.saves_on = not self.saves_on
        self.render()

    def toggle_desktop(self):
        self.desktop = not self.desktop
        self.render()

    def toggle_details(self):
        if self.details:
            self.details.destroy()
            self.details = None
        else:
            self.details = tk.Text(self.root, bg=BG2, fg=SUB, insertbackground=TEXT, relief='flat', bd=0,
                                   highlightthickness=0, font=self.ui.monofont, wrap='none')
            self.details.insert('end', '\n'.join(self.log[-4000:]))
            self.details.see('end')
        self.render()

    # -- the build
    def start(self):
        self.install = os.path.abspath(os.path.expanduser(self.e_dir.get().strip()))
        self.args = (os.path.expanduser(self.e_xbox.get().strip()), os.path.expanduser(self.e_psp.get().strip()),
                     os.path.expanduser(self.e_saves.get().strip()) if self.saves_on else '')
        self.page = 2
        self.building, self.failed, self.cancelled, self.stop = True, False, False, False
        self.error, self.detail = '', 'Copying the compiler and the Speed Force sources'
        self.step, self.frac = 0, 0.0
        self.t0 = time.time()
        self.t_step = [self.t0] + [0] * len(STEPS)
        self.dur = [0.0] * len(STEPS)
        self.t_end = 0
        threading.Thread(target=self.work, daemon=True).start()
        self.tick()

    def set_step(self, n):
        t = time.time()
        while self.step < n and self.step < len(STEPS):
            self.dur[self.step] = t - self.t_step[self.step]
            self.step += 1
            if self.step < len(STEPS):
                self.t_step[self.step] = t
        self.detail = ''

    def work(self):
        try:
            b = os.path.join(self.install, '_build')
            os.makedirs(self.install, exist_ok=True)
            shutil.rmtree(b, ignore_errors=True)
            files = [os.path.join(dp, f) for dp, _, fs in os.walk(KIT) for f in fs]
            for i, src in enumerate(files):
                if self.stop:
                    self.q.put(('done', 2))
                    return
                dst = os.path.join(b, os.path.relpath(src, KIT))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                if i % 50 == 0:
                    self.q.put(('copy', i / max(1, len(files))))
            self.q.put(('step', 1))
            xbox, psp, saves = self.args
            cmd = [sys.executable, '-u', os.path.join(b, 'setup', 'sf_install.py'), '--xbox', xbox, '--psp', psp,
                   '--app', self.install, '--tools', TOOLS]
            if saves:
                cmd += ['--saves', saves]
            self.proc = subprocess.Popen(cmd, cwd=self.install, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, errors='replace', start_new_session=True)
            for line in self.proc.stdout:
                self.q.put(('line', line.rstrip('\n')))
            code = self.proc.wait()
            if code == 0 and not self.stop:
                st = load_state()
                st.update(install=self.install, desktop=self.desktop)
                save_state(st)
                write_desktop_entries(self.desktop)
            self.q.put(('done', 2 if self.stop else (0 if code == 0 else 1)))
        except Exception as e:      # noqa: BLE001 - shown to the player
            self.error = str(e)
            self.q.put(('done', 1))

    def tick(self):
        try:
            while True:
                kind, v = self.q.get_nowait()
                if kind == 'copy':
                    self.frac = 0.05 * v
                    self.detail = f'{int(v * 100)}%'
                elif kind == 'step':
                    self.set_step(v)
                elif kind == 'line':
                    self.on_line(v)
                elif kind == 'done':
                    self.finish(v)
        except queue.Empty:
            pass
        if self.page in (2, 3):
            self.redraw()
        if self.building:
            self.root.after(120, self.tick)

    def on_line(self, line):
        if line.startswith('@@'):
            pm, _, t = line[2:].partition('|')
            try:
                self.frac = 0.05 + 0.95 * int(pm) / 1000
            except ValueError:
                pass
            if t.startswith('Step '):
                try:
                    self.set_step(int(t[5:].split()[0]))
                except ValueError:
                    pass
            elif t and t != 'Done':
                self.detail = t
            return
        t = line[9:] if len(line) > 9 and line[2] == ':' and line[5] == ':' else line
        if t.strip().startswith('ERROR:'):
            self.error = t.strip()[6:].strip()
        if not t.strip().startswith('>'):
            self.log.append(line)
            if self.details:
                self.details.insert('end', line + '\n')
                self.details.see('end')

    def finish(self, code):
        self.building = False
        self.failed, self.cancelled = code == 1, code == 2
        self.t_end = time.time()
        if code == 0:
            self.set_step(len(STEPS))
            self.frac = 1.0
        elif self.step < len(STEPS):
            self.dur[self.step] = self.t_end - self.t_step[self.step]
        if code == 1 and self.error:
            self.log.append('ERROR: ' + self.error)
        self.page = 3
        self.render()
        try:
            self.root.bell()
        except tk.TclError:
            pass

    def cancel(self):
        if messagebox.askyesno('Speed Force', 'Stop the build? You can start it again later.', parent=self.root):
            self.stop = True
            if self.proc and self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except OSError:
                    pass

    def play(self):
        self.root.destroy()
        try:
            launch_game(self.install, load_state().get('runner', 'auto'))
        except RuntimeError as e:
            print(e, file=sys.stderr)

    def open_launcher(self):
        for w in self.root.winfo_children():
            w.destroy()
        Launcher(self.root)

    def close(self):
        if self.building:
            if not messagebox.askyesno('Speed Force', 'The build is still running. Stop it and close?', parent=self.root):
                return
            self.stop = True
            if self.proc and self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except OSError:
                    pass
        self.root.destroy()


# ---------------------------------------------------------------- the launcher
class Launcher:
    def __init__(self, root):
        self.root = root
        self.ui = UI(root, 980, 640)
        root.title('Speed Force')
        self.st = load_state()
        self.install = self.st.get('install', '')
        self.cfg = Config(os.path.join(self.install, 'config', 'config.toml'))
        self.nav = 'play'
        self.hint = None
        self.toast_until = 0
        self.status = ''
        self.update = ('checking', '', '')
        self.importing = False
        self.sel = []
        self.load_settings()
        threading.Thread(target=self.check_updates, daemon=True).start()
        self.render()
        self.poll()

    def load_settings(self):
        self.cfg.load()
        self.sel = []
        for key, vals, labels, quoted, default, *_ in CHOICES:
            v = self.cfg.get(key) or default
            self.sel.append(vals.index(v) if v in vals else vals.index(default))
        try:
            self.volume = int(self.cfg.get('audio.volume') or 100)
        except ValueError:
            self.volume = 100

    def save_settings(self):
        self.cfg.load()
        for i, (key, vals, labels, quoted, *_rest) in enumerate(CHOICES):
            self.cfg.set(key, vals[self.sel[i]], quoted)
        self.cfg.set('audio.volume', str(self.volume), False)
        try:
            self.cfg.save()
            self.toast_until = time.time() + 2
        except OSError:
            pass

    def check_updates(self):
        try:
            req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases/latest',
                                         headers={'User-Agent': f'SpeedForce/{VERSION}',
                                                  'Accept': 'application/vnd.github+json'})
            with urllib.request.urlopen(req, timeout=8) as r:
                rel = json.load(r)
            tag = rel.get('tag_name', '')

            def num(v):
                p = [int(x) for x in ''.join(c if c.isdigit() else ' ' for c in v).split()[:3]]
                return tuple(p + [0] * (3 - len(p)))
            url = rel.get('html_url') or f'https://github.com/{REPO}/releases/latest'
            self.update = ('newer', tag, url) if num(tag) > num(VERSION) else ('latest', tag, url)
        except Exception:
            self.update = ('offline', '', '')

    def poll(self):
        sig = (self.update, self.status, self.importing, time.time() < self.toast_until)
        if sig != getattr(self, '_sig', None):
            self._sig = sig
            self.render()
        self.root.after(300, self.poll)

    # -- pages
    def sidebar(self):
        u = self.ui
        u.c.create_rectangle(0, 0, u.px(220), u.px(640), fill=BG2, outline='')
        u.draw_image('icon', os.path.join(HERE, 'icon.png'), 22, 22, 36, 36)
        u.text(68, 40, 'Speed Force', 'h2', anchor='w')
        for i, (key, name) in enumerate((('play', 'Play'), ('settings', 'Settings'), ('saves', 'Saves'),
                                         ('about', 'About'))):
            y = 84 + i * 44
            tag = u._tag()
            on = self.nav == key
            bg = u.round_rect(12, y, 196, 40, 8, CARD2 if on else BG2, tags=(tag,))
            if on:
                u.round_rect(12, y + 10, 3, 20, 1.5, ACCENT, tags=(tag,))
            u.text(30, y + 20, name, 'bold' if on else 'body', TEXT if on else SUB, anchor='w', tags=(tag,))
            u.clickable(tag, lambda k=key: self.go(k),
                        None if on else (lambda o, b=bg: u.c.itemconfigure(b, fill=HOVER if o else BG2)))
        if self.update[0] == 'newer':
            u.round_rect(16, 540, 188, 48, 8, '#2a2412', ACCENT)
            u.text(28, 546, 'Update available', 'bold', ACCENT)
            u.link(28, 566, self.update[1], lambda: open_path(self.update[2]), 'small')
        u.text(24, 610, f'Version {VERSION}', 'small', DIM)

    def label(self, i):
        return CHOICES[i][2][self.sel[i]]

    def page_play(self):
        u = self.ui
        u.round_rect(248, 28, 708, 300, 14, CARD, BORDER)
        u.draw_image('banner', os.path.join(HERE, 'banner.png'), 249, 29, 706, 298)
        u.text(280, 170, 'Justice League Heroes', 'title')
        u.text(282, 212, f'Native recompilation  -  Speed Force {VERSION}', 'body', SUB)
        u.button(280, 246, 200, 52, 'Play', self.play, 1, not self.status.startswith('!'))
        if self.status:
            u.text(500, 272, self.status.lstrip('!'), 'small', BAD if self.status.startswith('!') else SUB,
                   anchor='w', width=430)
        u.round_rect(248, 346, 708, 150, 12, CARD, BORDER)
        u.text(272, 362, 'Current settings', 'h2')
        u.text(272, 396, f'{self.label(0)}  -  output {self.label(1)}  -  {self.label(2)}', 'body', SUB)
        u.text(272, 420, f'Speed Force {self.label(3)}  -  upscaler {self.label(4)}  -  anti-aliasing {self.label(5)}',
               'body', SUB)
        u.link(272, 452, 'Change settings  >', lambda: self.go('settings'))
        r = pick_runner(self.st.get('runner', 'auto'))
        how = (r[3] if r[0] == 'proton' else r[-1]) if r[0] else r[1]
        u.text(250, 512, f'Runs with: {how}.  "Speed Force (game only)" in your app menu starts the game without '
                         'the launcher. Press F10 in game for every setting.', 'small', DIM, width=700)

    def selector(self, x, y, i):
        u = self.ui
        key, vals, labels, quoted, default, name, desc = CHOICES[i]
        u.round_rect(x, y, 348, 54, 10, CARD, BORDER)
        u.text(x + 16, y + 27, name, 'bold', anchor='w')
        u.round_rect(x + 176, y + 10, 160, 34, 8, INPUT, BORDER)
        tp, tn = u._tag(), u._tag()
        u.c.create_rectangle(u.px(x + 176), u.px(y + 10), u.px(x + 208), u.px(y + 44), fill='', outline='', tags=(tp,))
        ap = u.text(x + 191, y + 26, '‹', 'arrow', SUB, anchor='center', tags=(tp,))
        u.c.create_rectangle(u.px(x + 208), u.px(y + 10), u.px(x + 336), u.px(y + 44), fill='', outline='', tags=(tn,))
        an = u.text(x + 321, y + 26, '›', 'arrow', SUB, anchor='center', tags=(tn,))
        u.text(x + 256, y + 27, labels[self.sel[i]], 'bold', anchor='center', tags=(tn,))

        def hov(on, item):
            u.recolor(item, ACCENT if on else SUB)
            self.hint = desc if on else None
            self.draw_hint()
        u.clickable(tp, lambda: self.cycle(i, -1), lambda on: hov(on, ap))
        u.clickable(tn, lambda: self.cycle(i, 1), lambda on: hov(on, an))

    def draw_hint(self):
        u = self.ui
        u.c.delete('hint')
        u.text(268, 444, self.hint or 'Click a value to change it (the arrow on the left goes back).', 'body', SUB,
               anchor='w', width=670, tags=('hint',))

    def cycle(self, i, d):
        self.sel[i] = (self.sel[i] + d) % len(CHOICES[i][1])
        self.save_settings()
        self.render()

    def page_settings(self):
        u = self.ui
        u.text(248, 22, 'Settings', 'h1')
        u.text(250, 58, 'The same settings as the in-game F10 menu, which has the rest. Changes are saved at once.',
               'small', SUB)
        for i in range(len(CHOICES)):
            self.selector(248 + (i % 2) * 360, 88 + (i // 2) * 62, i)
        x, y = 608, 88 + 4 * 62
        u.round_rect(x, y, 348, 54, 10, CARD, BORDER)
        u.text(x + 16, y + 27, 'Master volume', 'bold', anchor='w')
        tag = u._tag()
        u.c.create_rectangle(u.px(x + 160), u.px(y + 8), u.px(x + 296), u.px(y + 46), fill='', outline='', tags=(tag,))
        u.progress(x + 168, y + 24, 120, 6, self.volume / 100)
        kx = u.px(x + 168 + 120 * self.volume / 100)
        ky, r = u.px(y + 27), u.px(8)
        u.c.create_oval(kx - r, ky - r, kx + r, ky + r, fill=TEXT, outline='', tags=(tag,))
        u.text(x + 336, y + 27, f'{self.volume}%', 'bold', anchor='e')

        def drag(e):
            self.volume = max(0, min(100, int((e.x - u.px(x + 168)) * 100 / u.px(120))))
            self.render()
        u.c.tag_bind(tag, '<B1-Motion>', drag)
        u.c.tag_bind(tag, '<Button-1>', drag)
        u.c.tag_bind(tag, '<ButtonRelease-1>', lambda e: self.save_settings())
        u.round_rect(248, 412, 708, 64, 10, BG2, BORDER)
        self.draw_hint()
        u.link(250, 492, 'Restore defaults', self.defaults)
        if time.time() < self.toast_until:
            u.text(956, 40, 'Saved', 'bold', OK, anchor='e')

    def defaults(self):
        self.sel = [c[1].index(c[4]) for c in CHOICES]
        self.volume = 100
        self.save_settings()
        self.render()

    def slots(self):
        out = []
        for n in range(5):
            folder = '%012X' % (0xACCD073B22C1 + 0x3B * n)
            p = os.path.join(self.install, 'saves', 'UDATA', '57520001', folder, 'slot.bin')
            try:
                with open(p, 'rb') as f:
                    lvl = f.read(16).split(b'\0')[0].decode('latin-1')
                t = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))
                out.append(f'{lvl}{" (final mission / completed)" if lvl == "e11l5" else ""}  -  saved {t}')
            except OSError:
                out.append('Empty')
        return out

    def page_saves(self):
        u = self.ui
        u.text(248, 22, 'Saves', 'h1')
        u.text(250, 58, 'Your five save slots, kept in the saves folder inside the install folder.', 'small', SUB)
        for n, s in enumerate(self.slots()):
            y = 88 + n * 56
            u.round_rect(248, y, 708, 48, 10, CARD, BORDER)
            u.text(268, y + 24, f'Slot {n + 1}', 'bold', anchor='w')
            u.text(350, y + 24, s, 'body', DIM if s == 'Empty' else TEXT, anchor='w')
        u.round_rect(248, 378, 708, 120, 12, CARD, BORDER)
        u.text(272, 394, 'Bring saves from a real Xbox', 'h2')
        u.text(272, 420, 'Choose the folder you copied from your Xbox (UDATA/57520001). Saves go into free slots; '
                         'completed saves start Episode 1 the Chapter Select way.', 'small', SUB, width=660)
        u.button(272, 456, 180, 34, 'Importing...' if self.importing else 'Import Xbox saves', self.import_saves, 1,
                 not self.importing)
        u.button(462, 456, 180, 34, 'Open saves folder', self.open_saves, 0)

    def page_about(self):
        u = self.ui
        u.text(248, 22, 'About', 'h1')
        u.round_rect(248, 72, 708, 150, 12, CARD, BORDER)
        u.draw_image('icon', os.path.join(HERE, 'icon.png'), 272, 96, 56, 56)
        u.text(344, 92, f'Speed Force {VERSION} for Linux', 'h2')
        u.text(344, 120, 'An unofficial Justice League Heroes native Windows recompilation, run here with Proton or '
                         'Wine. Fan project, not affiliated with Warner Bros. Games, DC, Snowblind Studios or Eidos.',
               'small', SUB, width=580)
        k = self.update[0]
        msg = {'checking': 'Checking for updates...', 'latest': 'You have the latest version.',
               'newer': f'A new version is available: {self.update[1]}',
               'offline': "Couldn't check for updates (offline?)."}[k]
        u.text(344, 187, msg, 'body', ACCENT if k == 'newer' else SUB, anchor='w')
        if k == 'newer':
            u.button(740, 170, 196, 34, 'Get the update', lambda: open_path(self.update[2]), 1)
        else:
            u.button(740, 170, 196, 34, 'Check again', self.recheck, 0, k != 'checking')
        # how the game runs
        u.round_rect(248, 236, 708, 112, 12, CARD, BORDER)
        u.text(272, 250, 'Run the game with', 'h2')
        choice = self.st.get('runner', 'auto')
        r = pick_runner(choice)
        how = (f'Using {r[3]}.' if r[0] == 'proton' else f'Using {r[-1]} with DXVK.') if r[0] else r[1]
        u.text(272, 280, how, 'small', SUB if r[0] else BAD, width=420)
        u.text(272, 300, 'Proton or your own Wine is used when installed; the Wine inside this AppImage otherwise.',
               'small', DIM, width=440)
        x = 720
        u.round_rect(x, 262, 216, 34, 8, INPUT, BORDER)
        tag = u._tag()
        u.c.create_rectangle(u.px(x), u.px(262), u.px(x + 216), u.px(296), fill='', outline='', tags=(tag,))
        a = u.text(x + 200, 278, '›', 'arrow', SUB, anchor='center', tags=(tag,))
        u.text(x + 100, 279, RUNNER_LABELS[choice], 'bold', anchor='center', tags=(tag,))
        u.clickable(tag, self.next_runner, lambda on: u.recolor(a, ACCENT if on else SUB))
        # files
        u.round_rect(248, 362, 708, 112, 12, CARD, BORDER)
        u.text(272, 376, 'Files', 'h2')
        u.text(272, 404, self.install, 'small', SUB)
        u.button(272, 426, 140, 34, 'Open folder', lambda: open_path(self.install), 0)
        u.button(420, 426, 150, 34, 'Open game log', self.open_log, 0)
        u.button(578, 426, 130, 34, 'GitHub page', lambda: open_path(f'https://github.com/{REPO}'), 0)
        u.button(716, 426, 220, 34, 'Rebuild (builder)', self.rebuild, 0)
        # uninstall
        u.round_rect(248, 488, 708, 76, 12, CARD, BORDER)
        u.text(272, 502, 'Uninstall', 'h2')
        u.text(272, 530, 'Removes Speed Force from this PC. You can keep your saves and settings.', 'small', SUB)
        u.button(776, 508, 160, 36, 'Uninstall', self.uninstall, 3)

    def render(self):
        self.ui.clear()
        self.sidebar()
        {'play': self.page_play, 'settings': self.page_settings, 'saves': self.page_saves,
         'about': self.page_about}[self.nav]()

    def go(self, key):
        self.nav = key
        self.hint = None
        self.render()

    # -- actions
    def play(self):
        self.status = 'Starting...'
        self.render()

        def run():
            try:
                launch_game(self.install, self.st.get('runner', 'auto'),
                            lambda m: setattr(self, 'status', m))
                self.root.after(0, self.root.destroy)
            except Exception as e:      # noqa: BLE001 - shown to the player
                self.status = '!' + str(e)
        threading.Thread(target=run, daemon=True).start()

    def next_runner(self):
        cur = self.st.get('runner', 'auto')
        self.st['runner'] = RUNNERS[(RUNNERS.index(cur) + 1) % len(RUNNERS)]
        save_state(self.st)
        self.render()

    def recheck(self):
        self.update = ('checking', '', '')
        threading.Thread(target=self.check_updates, daemon=True).start()
        self.render()

    def open_saves(self):
        p = os.path.join(self.install, 'saves')
        os.makedirs(p, exist_ok=True)
        open_path(p)

    def open_log(self):
        for n in ('SpeedForce.log', 'SpeedForce-linux.log'):
            p = os.path.join(self.install, n)
            if os.path.exists(p):
                open_path(p)
                return

    def import_saves(self):
        s = pick_file('The folder with your Xbox saves (UDATA/57520001)', True)
        if not s:
            return
        self.importing = True
        self.render()

        def run():
            r = subprocess.run([sys.executable, os.path.join(self.install, '_build', 'setup', 'sf_saves.py'),
                                '--in', s, '--out', os.path.join(self.install, 'saves')],
                               capture_output=True, text=True)
            self.importing = False
            self.root.after(0, lambda: messagebox.showinfo(
                'Speed Force', 'Your saves were imported.' if r.returncode == 0 else
                'Some saves could not be imported; see import.log in the saves folder.', parent=self.root))
        threading.Thread(target=run, daemon=True).start()

    def rebuild(self):
        for w in self.root.winfo_children():
            w.destroy()
        Builder(self.root, {'dir': self.install})

    def uninstall(self):
        r = messagebox.askyesnocancel(
            'Uninstall Speed Force', 'Uninstall Speed Force?\n\nYes: uninstall and keep your saves and settings.\n'
            'No: uninstall and delete your saves and settings too.\nCancel: keep Speed Force.', parent=self.root)
        if r is None:
            return
        keep = r
        for n in os.listdir(self.install):
            if keep and n in ('saves', 'config'):
                continue
            p = os.path.join(self.install, n)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        if not keep:
            shutil.rmtree(self.install, ignore_errors=True)
        shutil.rmtree(DATA_DIR, ignore_errors=True)            # the Wine / Proton prefix
        remove_desktop_entries()
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass
        messagebox.showinfo('Speed Force', 'Speed Force was uninstalled.' + (
            ' Your saves and settings are still in its folder.' if keep else '') +
            ' You can delete the AppImage file too.', parent=self.root)
        self.root.destroy()


# ---------------------------------------------------------------- main
def main():
    args, i, argv = {}, 1, sys.argv
    while i < len(argv):
        a = argv[i]
        if a in ('--xbox', '--psp', '--dir', '--saves') and i + 1 < len(argv):
            args[a[2:]] = argv[i + 1]
            i += 2
            continue
        args[a.lstrip('-')] = True
        i += 1
    st = load_state()
    built = st.get('install') and os.path.exists(os.path.join(st['install'], 'SpeedForce.exe'))
    if args.get('play'):
        if not built:
            print('Speed Force is not built yet: start the AppImage without --play to build it.', file=sys.stderr)
            return 1
        try:
            p, how = launch_game(st['install'], st.get('runner', 'auto'), print)
            print(f'Speed Force started with {how}.')
            return 0
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 1
    root = tk.Tk(className='speedforce')
    try:
        root.iconphoto(True, tk.PhotoImage(file=os.path.join(HERE, 'icon.png')))
    except tk.TclError:
        pass
    if built and not args.get('setup') and not ('xbox' in args or 'psp' in args):
        Launcher(root)
    else:
        Builder(root, args)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
