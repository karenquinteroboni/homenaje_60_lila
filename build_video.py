#!/usr/bin/env python3
"""
Video homenaje a los 60 años de Lila.

Genera un MP4 1920x1080 / 30 fps con las fotografías originales, los mensajes
y la canción "Gira el amor" (archivo MP3 local incluido en esta carpeta).

Requisitos: Python 3.9+, Pillow, numpy y ffmpeg (con libx264).

    python3 build_video.py                       # render completo
    python3 build_video.py --preview 6,30,150    # solo guarda fotogramas de prueba
    python3 build_video.py --audio otra_cancion.mp3

Todo el guion (orden de fotos, mensajes, duraciones) está en la sección
"GUION" más abajo y se puede editar libremente.
"""
import argparse
import math
import re
import shutil
import subprocess
import sys
import wave
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
FONT_SERIF = ROOT / "fonts" / "CormorantGaramond-VariableFont_wght.ttf"
FONT_SCRIPT = ROOT / "fonts" / "GreatVibes-Regular.ttf"
DEFAULT_AUDIO = ROOT / "Gigliola Cinquetti - Gira El Amor - HQ - Con Letra.mp3"
DEFAULT_OUT = ROOT / "output" / "Homenaje_Lila_60_anos.mp4"
CACHE = ROOT / "cache"

W, H, FPS = 1920, 1080, 30
TOTAL = 166.0            # duración del video (s)

# --- Audio ---------------------------------------------------------------
# La canción tiene ~1,7 s de silencio al inicio y termina en seco a los
# ~165,5 s (seguida de silencio). Se recorta desde AUDIO_SS y se le añaden
# fundidos de entrada y salida.
AUDIO_SS = 1.0           # segundo del MP3 que corresponde a t=0 del video
FADE_IN = (0.8, 3.6)     # (inicio, duración) en tiempo de video
FADE_OUT = (160.3, 4.1)

# --- Paleta ----------------------------------------------------------------
CREAM = (248, 238, 218)
GOLD = (226, 188, 122)
BG_CENTER = np.array([66, 45, 30], np.float32)
BG_EDGE = np.array([17, 11, 8], np.float32)
WARM = np.array([1.035, 1.0, 0.955], np.float32)   # tinte cálido muy leve

# ---------------------------------------------------------------------------
# GUION
# ---------------------------------------------------------------------------
# Los *asteriscos* marcan palabras en letra cursiva dorada (lettering).
INTRO_LILA = (1.0, 2.7, 4.3, 5.0)          # in_start, in_end, out_start, out_end
INTRO_MSG1 = ("*60 años* de historias, de *amor,* de sueños cumplidos y de momentos "
              "que se convierten en recuerdos para toda la vida.", (4.9, 5.8, 8.5, 9.2))
INTRO_MSG2 = ("Hoy celebramos tu vida, tu esencia y la alegría de tenerte entre nosotros.",
              (9.0, 9.9, 11.2, 11.9))
FIRST_CUT = 12.0     # primera fotografía
FINAL_CUT = 141.0    # fotografía de cierre

P1, P2, P3 = "FOTOS HOMENAJE LILA/", "FOTOS LILA 2/", ""
IMG = {
    70: P2 + "858fdef9-6a76-4f53-b069-9a9a9c19eee9.jpg",
    82: P2 + "IMG-20161012-WA0009.jpg",
    81: P2 + "IMG-20161012-WA0007.jpg",
    61: P1 + "WhatsApp Image 2026-10-12 at 10.27.35 AM (2).jpeg",
    85: P2 + "IMG-20170620-WA0009.jpg",
    86: P2 + "IMG-20170620-WA0011.jpg",
    76: P2 + "IMG-20160916-WA0013.jpg",
    88: P2 + "IMG-20170703-WA0008.jpg",
    29: P1 + "IMG-20230115-WA0036.jpg",
    58: P1 + "WhatsApp Image 2026-10-12 at 10.27.34 AM (5).jpeg",
    13: P1 + "IMG-20221029-WA0012.jpg",
    55: P1 + "WhatsApp Image 2026-10-12 at 10.27.34 AM (2).jpeg",
    33: P1 + "IMG-20230115-WA0128.jpg",
    34: P1 + "IMG-20230115-WA0132.jpg",
    32: P1 + "IMG-20230115-WA0099.jpg",
    31: P1 + "IMG-20230115-WA0089.jpg",
    24: P1 + "IMG-20221225-WA0006.jpg",
    47: P1 + "WhatsApp Image 2026-10-12 at 10.27.32 AM (2).jpeg",
    12: P1 + "IMG-20221020-WA0072.jpg",
    52: P1 + "WhatsApp Image 2026-10-12 at 10.27.33 AM (4).jpeg",
    54: P1 + "WhatsApp Image 2026-10-12 at 10.27.34 AM (1).jpeg",
    22: P1 + "IMG-20221221-WA0019.jpg",
    19: P1 + "IMG-20221130-WA0044.jpg",
    14: P1 + "IMG-20221031-WA0086.jpg",
    10: P1 + "IMG-20221015-WA0106.jpg",
    9: P1 + "IMG-20221015-WA0104.jpg",
    129: P2 + "IMG-20220722-WA0136.jpg",
    116: P2 + "IMG-20211224-WA0043.jpg",
    118: P2 + "IMG-20220109-WA0104.jpg",
    59: P1 + "WhatsApp Image 2026-10-12 at 10.27.34 AM.jpeg",
    128: P2 + "IMG-20220722-WA0129.jpg",
    46: P1 + "WhatsApp Image 2026-10-12 at 10.27.32 AM (1).jpeg",
    48: P1 + "WhatsApp Image 2026-10-12 at 10.27.32 AM.jpeg",
    49: P1 + "WhatsApp Image 2026-10-12 at 10.27.33 AM (1).jpeg",
    106: P2 + "IMG-20210403-WA0110.jpg",
    0: "FOTO LILA FINAL.jpg",
}

# (id de foto, ritmo, mensaje)   ritmo: n = pausado/nostálgico, m = medio, j = alegre
# Escena 2: los recuerdos que nos construyen
# Escena 3: el amor que ha acompañado su camino
# Escena 4: sesenta años de historia
SEQUENCE = [
    (70, "n", "Hay recuerdos que el tiempo no borra, porque el corazón los guarda para siempre."),
    (82, "n", None),
    (81, "n", None),
    (61, "m", None),
    (85, "m", None),
    (86, "m", "Tu historia está hecha de pequeños momentos que se volvieron extraordinarios."),
    (76, "m", None),
    (88, "j", None),
    (29, "m", "En cada sonrisa vive una historia; en cada recuerdo, una razón para agradecer."),
    (58, "j", None),
    # --- Escena 3
    (13, "n", "Las personas que amamos convierten los momentos sencillos en recuerdos inolvidables."),
    (55, "m", None),
    (33, "m", None),
    (34, "n", "Los años pasan, pero el *amor* que compartimos permanece."),
    (32, "m", None),
    (31, "m", None),
    (24, "m", None),
    (47, "m", None),
    (12, "m", None),
    (52, "j", None),
    (54, "j", "Tu vida también vive en las historias, las sonrisas y los corazones de quienes te quieren."),
    (22, "j", None),
    # --- Escena 4
    (14, "m", "*60 años* de experiencias que te hicieron crecer, de sueños que te impulsaron y de *amor* que multiplicaste."),
    (10, "j", None),
    (9, "j", None),
    (129, "j", None),
    (116, "j", None),
    (118, "j", None),
    (59, "m", "No se trata solamente de contar los años, sino de celebrar todo lo hermoso que has vivido."),
    (128, "j", None),
    (46, "m", None),
    (48, "j", None),
    (49, "j", None),
    (106, "m", "Sesenta años después, todavía quedan abrazos por dar, sueños por cumplir y momentos maravillosos por vivir."),
]
FINAL_PHOTO = 0
CLOSING = [  # (texto, tamaño, in_start, in_end, out_start, out_end) — relativo a t absoluto
    ("*Lila,* hoy celebramos mucho más que tus *60 años.* Celebramos tu vida, tu historia, "
     "tu esencia y todos esos momentos que has convertido en algo especial para quienes "
     "tenemos la fortuna de compartir el camino contigo.", 52, (144.2, 145.2, 152.6, 153.4)),
    ("FELICES", 0, (153.4, 154.6, 159.9, 160.7)),          # composición especial
    ("Con todo nuestro *amor,* hoy y siempre.", 66, (160.5, 161.6, 999, 999)),
]
BLACK_FADE = (162.9, 165.4)    # fundido a negro (inicio, fin)

WORD_TIME = 0.26   # s por palabra de lectura
TRANS = 0.40       # semiduración del fundido encadenado entre fotos
BASE_DUR = {"n": 3.3, "m": 2.6, "j": 2.2}   # pesos relativos de duración

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ramp(t, a, b):
    """0 antes de a, 1 después de b, suave entre ambos."""
    if b <= a:
        return 1.0 if t >= a else 0.0
    return smooth((t - a) / (b - a))


def window(t, ins, ine, outs, oute):
    return ramp(t, ins, ine) * (1 - ramp(t, outs, oute))


def serif_font(size, weight=500):
    f = ImageFont.truetype(str(FONT_SERIF), size)
    f.set_variation_by_axes([weight])
    return f


def script_font(size):
    return ImageFont.truetype(str(FONT_SCRIPT), size)


def tokenize(markup):
    toks = []
    for part in re.split(r"(\*[^*]+\*)", markup):
        if not part:
            continue
        hi = part.startswith("*")
        for w in part.strip("*").split():
            toks.append((w, hi))
    return toks


def render_text(markup, size, maxw, line_gap=1.28, script_scale=1.42, align="center"):
    """Devuelve una imagen RGBA con el texto (y su sombra suave) lista para componer."""
    sf, cf = serif_font(size, 500), script_font(int(size * script_scale))
    toks = tokenize(markup)
    space = sf.getlength(" ")
    lines, cur, curw = [], [], 0.0
    for w, hi in toks:
        f = cf if hi else sf
        wl = f.getlength(w)
        if cur and curw + space + wl > maxw:
            lines.append((cur, curw))
            cur, curw = [], 0.0
        curw += (space if cur else 0) + wl
        cur.append((w, hi, wl))
    if cur:
        lines.append((cur, curw))
    asc_s, desc_s = sf.getmetrics()
    asc_c, desc_c = cf.getmetrics()
    pad = 50
    lh = int(size * line_gap)
    heights = []
    for ln, _ in lines:
        has_hi = any(h for _, h, _ in ln)
        heights.append(int(lh * (1.12 if has_hi else 1.0)))
    wmax = int(max(w for _, w in lines)) + 2 * pad
    hh = sum(heights) + 2 * pad + 20
    txt = Image.new("RGBA", (wmax, hh), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    y = pad
    for (ln, lw), lhgt in zip(lines, heights):
        x = pad + ((wmax - 2 * pad - lw) / 2 if align == "center" else 0)
        base = y + max(asc_s, asc_c * 0.93) + 4
        for w, hi, wl in ln:
            if hi:
                d.text((x, base), w, font=cf, fill=GOLD + (255,), anchor="ls")
            else:
                d.text((x, base), w, font=sf, fill=CREAM + (255,), anchor="ls")
            x += wl + space
        y += lhgt
    return add_shadow(txt)


def add_shadow(img, blur=9, strength=0.75, dy=3):
    a = img.getchannel("A")
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    mask = a.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * strength * 1.6)))
    sh.putalpha(mask)
    sh = ImageChops_offset(sh, 0, dy)
    out = Image.alpha_composite(sh, img)
    return out


def ImageChops_offset(img, dx, dy):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


def ornament(width=420, height=24):
    """Línea fina dorada con un pequeño rombo central."""
    im = Image.new("RGBA", (width + 40, height + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = im.width // 2, im.height // 2
    for i in range(width // 2 - 22):
        a = int(255 * (1 - i / (width / 2 - 22)) ** 0.8)
        d.point((cx + 20 + i, cy), fill=GOLD + (a,))
        d.point((cx - 20 - i, cy), fill=GOLD + (a,))
    s = 6
    d.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=GOLD + (255,))
    return add_shadow(im, blur=5, strength=0.4, dy=2)


def overlay(frame, img, cx, cy, alpha):
    """Compone una imagen RGBA centrada en (cx, cy) con opacidad global alpha."""
    if alpha <= 0.003:
        return
    x0, y0 = int(cx - img.width / 2), int(cy - img.height / 2)
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W, x0 + img.width), min(H, y0 + img.height)
    if xb <= xa or yb <= ya:
        return
    arr = np.asarray(img)[ya - y0:yb - y0, xa - x0:xb - x0]
    a = (arr[..., 3:4].astype(np.float32) / 255.0) * alpha
    reg = frame[ya:yb, xa:xb]
    reg *= (1 - a)
    reg += arr[..., :3].astype(np.float32) * a


# ---------------------------------------------------------------------------
# Fondos, partículas y rejilla de color
# ---------------------------------------------------------------------------
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H * 0.46) / (H / 2)) ** 2)
GRADE = (1.0 - 0.30 * np.clip(_r / 1.35, 0, 1) ** 2.2)[..., None] * WARM   # viñeta + calidez


def dark_backdrop():
    k = np.clip(_r / 1.25, 0, 1) ** 1.3
    bg = BG_CENTER[None, None] * (1 - k[..., None]) + BG_EDGE[None, None] * k[..., None]
    return bg.astype(np.float32)


_rng = np.random.default_rng(60)
_P = [dict(x=_rng.uniform(0, W), y=_rng.uniform(0, H + 80), v=_rng.uniform(5, 16),
           r=int(_rng.integers(2, 8)), ph=_rng.uniform(0, 6.28), ph2=_rng.uniform(0, 6.28),
           amp=_rng.uniform(10, 40), b=_rng.uniform(0.35, 1.0)) for _ in range(46)]
_SPR = {}


def sprite(r):
    if r not in _SPR:
        n = r * 6 + 1
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        d = np.sqrt((xx - n // 2) ** 2 + (yy - n // 2) ** 2) / (r * 3)
        _SPR[r] = np.exp(-4.0 * d * d)[..., None]
    return _SPR[r]


def particles(frame, t, strength):
    if strength <= 0.01:
        return
    col = np.array([255, 214, 150], np.float32)
    for p in _P:
        tw = 0.5 + 0.5 * math.sin(1.1 * t + p["ph2"])
        x = p["x"] + p["amp"] * math.sin(0.25 * t + p["ph"])
        y = (p["y"] - p["v"] * t) % (H + 80) - 40
        s = sprite(p["r"])
        n = s.shape[0]
        x0, y0 = int(x) - n // 2, int(y) - n // 2
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + n), min(H, y0 + n)
        if xb <= xa or yb <= ya:
            continue
        sp = s[ya - y0:yb - y0, xa - x0:xb - x0]
        frame[ya:yb, xa:xb] += sp * col * (0.55 * p["b"] * tw * strength)


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------
class PhotoClip:
    def __init__(self, pid, mood, message, start, end, idx):
        self.pid, self.mood, self.message = pid, mood, message
        self.start, self.end, self.idx = start, end, idx
        self.loaded = False

    # --- carga perezosa (cada proceso carga solo lo que necesita)
    def load(self):
        if self.loaded:
            return
        src = ImageOps.exif_transpose(Image.open(ROOT / IMG[self.pid])).convert("RGB")
        self.low_res = src.width < 800
        # fondo: la propia foto, ampliada, difuminada y oscurecida (sin deformar)
        s = max(W / src.width, H / src.height)
        bgi = src.resize((math.ceil(src.width * s), math.ceil(src.height * s)), Image.BICUBIC)
        l, t = (bgi.width - W) // 2, (bgi.height - H) // 2
        bgi = bgi.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(46))
        bg = np.asarray(bgi, np.float32) * 0.46
        self.bg = bg * (WARM[None, None])
        # foto con un finísimo marco crema; completa, sin recortes
        bw = 4
        framed = Image.new("RGB", (src.width + 2 * bw, src.height + 2 * bw), (238, 226, 200))
        framed.paste(src, (bw, bw))
        pad = 3
        rgba = Image.new("RGBA", (framed.width + 2 * pad, framed.height + 2 * pad), (238, 226, 200, 0))
        rgba.paste(framed.convert("RGBA"), (pad, pad))
        self.photo = rgba
        box_w, box_h = W * 0.92, H * 0.92
        self.fit = min(box_w / framed.width, box_h / framed.height)
        # composición lateral (foto a un lado, texto al otro) para los mensajes
        self.side_fit = min(0.47 * W / framed.width, 0.78 * H / framed.height)
        self.dw = rgba.width * self.side_fit
        self.sgn = 1 if self.idx % 2 == 0 else -1          # 1: foto a la izquierda
        self.side_cx = 100 + self.dw / 2 if self.sgn == 1 else W - 100 - self.dw / 2
        if self.sgn == 1:
            x0, x1 = 100 + self.dw + 100, W - 100
        else:
            x0, x1 = 100, W - 100 - self.dw - 100
        self.colw = int(min(x1 - x0, 780))
        self.colcx = (x0 + x1) / 2
        # movimiento muy sutil y distinto en cada foto
        mode = self.idx % 4
        zoom = 0.03 if self.low_res else 0.055
        self.z0, self.z1 = (1.0 + zoom, 1.0) if mode == 3 else (1.0, 1.0 + zoom)
        self.pan = [(-14, 0), (12, -4), (-10, 6), (8, 0)][mode]
        self.loaded = True
        if self.message:
            self.msg_img = render_text(self.message, 54, self.colw)

    def lay(self, t):
        """0 = foto centrada y grande; 1 = foto a un lado con el texto al otro."""
        if not self.message:
            return 0.0
        return ramp(t - self.start, 1.1, 2.1)

    def photo_layer(self, t):
        d = max(self.end - self.start, 0.01)
        u = min(1.0, max(0.0, (t - (self.start - TRANS)) / (d + 2 * TRANS)))
        z = self.z0 + (self.z1 - self.z0) * u
        L = self.lay(t)
        base_fit = self.fit + (self.side_fit - self.fit) * L
        sc = base_fit * z
        cx = W / 2 + (self.side_cx - W / 2) * L + self.pan[0] * u
        cy = H / 2 + self.pan[1] * u
        pw, ph = self.photo.size
        a = 1.0 / sc
        c = pw / 2 - cx * a
        f = ph / 2 - cy * a
        return self.photo.transform((W, H), Image.AFFINE, (a, 0, c, 0, a, f), Image.BICUBIC)

    def frame(self, t):
        self.load()
        base = Image.fromarray(np.clip(self.bg, 0, 255).astype(np.uint8)).convert("RGBA")
        base.alpha_composite(self.photo_layer(t))
        arr = np.asarray(base.convert("RGB"), np.float32) * GRADE
        if self.message:
            u = t - self.start
            end_u = self.end - self.start
            ta = window(u, 1.6, 2.4, end_u - 1.15, end_u - 0.45)
            overlay(arr, self.msg_img, self.colcx, H / 2, ta)
        return arr


class IntroClip:
    start, end = 0.0, FIRST_CUT

    def __init__(self):
        self.bg = dark_backdrop()
        self.lila = add_shadow(self._lila())
        self.orn = ornament()
        self.m1 = render_text(INTRO_MSG1[0], 58, 1360, script_scale=1.5)
        self.m2 = render_text(INTRO_MSG2[0], 60, 1300)
        self.noise = [np.random.default_rng(i).normal(0, 1.4, (H, W, 1)).astype(np.float32) for i in range(4)]

    def _lila(self):
        f = script_font(330)
        im = Image.new("RGBA", (900, 520), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((450, 330), "Lila", font=f, fill=GOLD + (255,), anchor="ms")
        return im

    def frame(self, t):
        arr = self.bg.copy()
        arr += self.noise[int(t * 8) % 4]
        particles(arr, t, ramp(t, 0.2, 2.5) * (1 - ramp(t, 11.0, 12.4)))
        a = window(t, *INTRO_LILA)
        overlay(arr, self.lila, W / 2, H / 2 - 40, a)
        overlay(arr, self.orn, W / 2, H / 2 + 175, a * 0.9)
        overlay(arr, self.m1, W / 2, H / 2 - 5, window(t, *INTRO_MSG1[1]))
        overlay(arr, self.m2, W / 2, H / 2 - 5, window(t, *INTRO_MSG2[1]))
        arr *= ramp(t, 0.0, 0.9)
        return arr


class FinalClip(PhotoClip):
    """Cierre: la fotografía especial con los mensajes finales."""

    def load(self):
        if self.loaded:
            return
        super().load()
        self.sgn = 1
        self.side_cx = 100 + self.dw / 2
        x0, x1 = 100 + self.dw + 100, W - 100
        self.colw, self.colcx = int(min(x1 - x0, 780)), (x0 + x1) / 2
        self.z0, self.z1 = 1.0, 1.08
        self.pan = (0, -4)
        self.cl = []
        for txt, size, tm in CLOSING:
            self.cl.append(self._felices() if txt == "FELICES" else render_text(txt, size, self.colw))

    def lay(self, t):
        return ramp(t, 143.2, 144.4)

    def _felices(self):
        t1 = render_text("*¡Felices 60 años, Lila!*", 84, self.colw, line_gap=1.12, script_scale=1.65)
        t2 = render_text("Que la vida te siga regalando motivos para sonreír, personas para abrazar, "
                         "sueños por cumplir y mucho *amor* para compartir.", 48, self.colw)
        out = Image.new("RGBA", (max(t1.width, t2.width), t1.height + t2.height + 10), (0, 0, 0, 0))
        out.alpha_composite(t1, ((out.width - t1.width) // 2, 0))
        out.alpha_composite(t2, ((out.width - t2.width) // 2, t1.height + 10))
        return out

    def frame(self, t):
        self.load()
        base = Image.fromarray(np.clip(self.bg, 0, 255).astype(np.uint8)).convert("RGBA")
        base.alpha_composite(self.photo_layer(t))
        arr = np.asarray(base.convert("RGB"), np.float32) * GRADE
        particles(arr, t, ramp(t, 148.0, 153.0) * 0.8)
        (_, _, w1), (_, _, w2), (_, _, w3) = CLOSING
        cx = self.colcx
        overlay(arr, self.cl[0], cx, H / 2, window(t, *w1))
        overlay(arr, self.cl[1], cx, H / 2, window(t, *w2))
        overlay(arr, self.cl[2], cx, H / 2, window(t, *w3))
        arr *= 1 - ramp(t, *BLACK_FADE)
        return arr


# ---------------------------------------------------------------------------
# Sincronía con la música
# ---------------------------------------------------------------------------
def detect_onsets(audio):
    """Detecta ataques fuertes (golpes de ritmo) de la canción con numpy."""
    CACHE.mkdir(exist_ok=True)
    wav = CACHE / "analysis.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-ac", "1", "-ar", "22050", str(wav)], check=True)
    w = wave.open(str(wav))
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop, N = 256, 1024
    win = np.hanning(N).astype(np.float32)
    n = (len(x) - N) // hop
    idx = np.arange(N)[None] + hop * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    flux = np.maximum(0, np.diff(np.log1p(spec * 50), axis=0)).sum(1)
    flux = np.maximum(flux - np.convolve(flux, np.ones(40) / 40, "same"), 0)
    fps = sr / hop
    k = 8
    peaks = [i for i in range(k, len(flux) - k) if flux[i] == flux[i - k:i + k + 1].max() and flux[i] > 0]
    thr = np.percentile(flux[peaks], 55)
    return np.array([(i + 1) * hop / sr for i in peaks if flux[i] >= thr])


def snap(t, onsets, tol=0.30):
    if len(onsets) == 0:
        return t
    j = int(np.argmin(np.abs(onsets - (t + AUDIO_SS))))
    p = onsets[j] - AUDIO_SS
    return p if abs(p - t) <= tol else t


# ---------------------------------------------------------------------------
# Construcción de la línea de tiempo
# ---------------------------------------------------------------------------
def build_timeline(onsets):
    msg_dur = {}
    for i, (_, _, m) in enumerate(SEQUENCE):
        if m:
            nw = len(m.replace("*", "").split())
            msg_dur[i] = 3.45 + WORD_TIME * nw
    avail = FINAL_CUT - FIRST_CUT - sum(msg_dur.values())
    wts = {i: BASE_DUR[mood] for i, (_, mood, m) in enumerate(SEQUENCE) if not m}
    k = avail / sum(wts.values())
    durs = [msg_dur[i] if i in msg_dur else wts[i] * k for i in range(len(SEQUENCE))]
    cuts, t = [], FIRST_CUT
    for d in durs:
        cuts.append(t)
        t += d
    cuts.append(FINAL_CUT)
    cuts = [snap(c, onsets) if 0 < i < len(cuts) else snap(c, onsets, 0.2) for i, c in enumerate(cuts)]
    clips = [PhotoClip(pid, mood, m, cuts[i], cuts[i + 1], i) for i, (pid, mood, m) in enumerate(SEQUENCE)]
    final = FinalClip(FINAL_PHOTO, "n", None, cuts[-1], TOTAL, len(SEQUENCE))
    return [IntroClip()] + clips + [final]


def compose(clips, t):
    """Fundido encadenado entre el clip actual y el anterior."""
    active = [c for c in clips if c.start - TRANS <= t <= (c.end if not isinstance(c, FinalClip) else TOTAL) + TRANS]
    if isinstance(clips[0], IntroClip) and t < FIRST_CUT + TRANS:
        active = [clips[0]] + [c for c in active if c is not clips[0]]
    active.sort(key=lambda c: c.start)
    # el intro siempre es la base mientras dure la transición
    out = None
    for c in active:
        if isinstance(c, IntroClip):
            a = 1.0
        else:
            a = ramp(t, c.start - TRANS, c.start + TRANS)
        f = c.frame(t)
        out = f if out is None else out * (1 - a) + f * a
    if out is None:
        out = np.zeros((H, W, 3), np.float32)
    return out


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def encoder(path):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-g", "60",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-an", str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def worker(args):
    part, f0, f1, audio = args
    onsets = detect_onsets_cached(audio)
    clips = build_timeline(onsets)
    p = encoder(CACHE / f"part_{part:02d}.mp4")
    for fr in range(f0, f1):
        t = fr / FPS
        a = np.clip(compose(clips, t), 0, 255).astype(np.uint8)
        p.stdin.write(a.tobytes())
        if part == 0 and fr % 150 == 0:
            print(f"  fotograma {fr}/{f1}", flush=True)
    p.stdin.close()
    p.wait()
    return part


_ONS = {}


def detect_onsets_cached(audio):
    npy = CACHE / "onsets.npy"
    if str(audio) not in _ONS:
        CACHE.mkdir(exist_ok=True)
        _ONS[str(audio)] = detect_onsets(audio) if not npy.exists() else np.load(npy)
    return _ONS[str(audio)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=str(DEFAULT_AUDIO))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--preview", default="", help="tiempos (s) separados por coma: guarda PNG en cache/preview")
    a = ap.parse_args()
    audio = Path(a.audio)
    if not audio.exists():
        sys.exit(f"No se encuentra el audio: {audio}\nColoca el MP3 de 'Gira el amor' en esa ruta o usa --audio.")
    CACHE.mkdir(exist_ok=True)
    onsets = detect_onsets(audio)
    np.save(CACHE / "onsets.npy", onsets)
    clips = build_timeline(onsets)
    print("Cortes (s):", ", ".join(f"{c.start:.1f}" for c in clips[1:]))
    if a.preview:
        out = CACHE / "preview"
        out.mkdir(exist_ok=True)
        for s in a.preview.split(","):
            t = float(s)
            Image.fromarray(np.clip(compose(clips, t), 0, 255).astype(np.uint8)).save(out / f"t{t:07.2f}.png")
        print("Fotogramas de prueba en", out)
        return
    nfr = int(TOTAL * FPS)
    n = a.workers
    bounds = [round(i * nfr / n) for i in range(n + 1)]
    jobs = [(i, bounds[i], bounds[i + 1], str(audio)) for i in range(n)]
    for old in CACHE.glob("part_*.mp4"):
        old.unlink()
    with Pool(n) as pool:
        pool.map(worker, jobs)
    lst = CACHE / "parts.txt"
    lst.write_text("".join(f"file '{CACHE / f'part_{i:02d}.mp4'}'\n" for i in range(n)))
    joined = CACHE / "video_sin_audio.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)
    af = (f"afade=t=in:st={FADE_IN[0]}:d={FADE_IN[1]},"
          f"afade=t=out:st={FADE_OUT[0]}:d={FADE_OUT[1]},apad")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-ss", str(AUDIO_SS), "-i", str(audio),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "256k",
                    "-t", str(TOTAL), "-movflags", "+faststart", str(out)], check=True)
    print("Listo:", out)


if __name__ == "__main__":
    main()
