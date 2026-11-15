"""Speed Force artwork (original): the launcher banner (banner.png), drawn around icon.png.
Dark navy, gold/orange speed streaks; Inter Display for lettering."""
import math, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

NAVY0, NAVY1 = (10, 14, 32), (22, 32, 70)
STREAKS = [(255, 196, 40), (255, 232, 160), (255, 140, 30), (90, 200, 255)]
BOLD = '/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf'
MED = '/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf'


def gradient(w, h, top=NAVY1, bottom=NAVY0):
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return im


def streaks(im, n, seed, angle=-14, alpha=200, region=(0, 1), unit=None):
    w, h = im.size
    rnd = random.Random(seed)
    layer = Image.new('RGBA', (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        c = rnd.choice(STREAKS)
        y = rnd.uniform(region[0], region[1]) * h * 2
        x0 = rnd.uniform(-0.3, 0.9) * w * 2
        ln = rnd.uniform(0.25, 0.9) * w * 2
        th = rnd.uniform(1.5, 7) * (unit or w / 160)
        a = int(alpha * rnd.uniform(0.35, 1))
        # tapered streak: thin tail -> thick head with a white dot
        steps = 40
        for k in range(steps):
            t0, t1 = k / steps, (k + 1) / steps
            d.line([(x0 + ln * t0, y), (x0 + ln * t1, y)], fill=c + (int(a * t1),), width=max(1, int(th * (0.3 + 0.7 * t1))))
        r = th * 0.9
        d.ellipse([x0 + ln - r, y - r, x0 + ln + r, y + r], fill=(255, 255, 255, a))
    layer = layer.rotate(angle, resample=Image.BICUBIC, center=(w, h))
    layer = layer.crop((w // 2, h // 2, w // 2 + w, h // 2 + h))
    glow = layer.filter(ImageFilter.GaussianBlur(w / 60))
    im = im.convert('RGBA')
    im.alpha_composite(glow)
    im.alpha_composite(layer)
    return im


def text_center(d, cx, y, s, font, fill):
    b = d.textbbox((0, 0), s, font=font)
    d.text((cx - (b[2] - b[0]) / 2 - b[0], y), s, font=font, fill=fill)


def wizard_image(w, h):
    s = w / 164
    im = streaks(gradient(w, h), 24, 7, region=(0.66, 1.08))
    icon = Image.open('icon.png').resize((int(76 * s), int(76 * s)), Image.LANCZOS)
    im.alpha_composite(icon, (int((w - icon.width) / 2), int(26 * s)))
    d = ImageDraw.Draw(im)
    text_center(d, w / 2, 112 * s, 'SPEED', ImageFont.truetype(BOLD, int(30 * s)), (255, 206, 60))
    text_center(d, w / 2, 142 * s, 'FORCE', ImageFont.truetype(BOLD, int(30 * s)), (255, 255, 255))
    text_center(d, w / 2, 182 * s, 'native PC recompilation', ImageFont.truetype(MED, int(10.5 * s)), (170, 190, 230))
    return im.convert('RGB')


def small_image(n):
    im = Image.open('icon.png').resize((n, n), Image.LANCZOS)
    return im


def back_image(w, h):
    im = gradient(w, h, (18, 24, 52), (8, 11, 26))
    im = streaks(im, 18, 3, alpha=120, region=(0.55, 1.1))
    return im.convert('RGB')


def banner(w, h):
    """The launcher's Play banner: streaks on the right, room for the title on the left."""
    im = gradient(w, h, (24, 34, 74), (10, 14, 32))
    im = streaks(im, 34, 11, angle=-10, alpha=230, region=(0.05, 0.8), unit=w / 520)
    shade = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for x in range(w):
        a = int(235 * max(0.0, 1 - x / (w * 0.62)))
        d.line([(x, 0), (x, h)], fill=(12, 17, 36, a))
    for y in range(h):
        a = int(150 * max(0.0, (y - h * 0.45) / (h * 0.55)))
        d.line([(0, y), (w, y)], fill=(12, 17, 36, a))
    im.alpha_composite(shade)
    return im.convert('RGB')


banner(1412, 596).save('banner.png')
