"""Erzeugt brand/icon.png, icon@2x.png, logo.png (Zapfsäule mit Fahrtenbuch-Seite und Smartphone-Kamera). python tests/make_icon.py"""
from PIL import Image, ImageDraw
import pathlib

K = 2            # Zeichnen in 2048 px, danach herunterrechnen
S = 1024 * K
out = pathlib.Path(__file__).parent.parent / "custom_components" / "drive_energy_doc" / "brand"
out.mkdir(parents=True, exist_ok=True)

def box(*v): return [x * K for x in v]

PDX = -70                                                  # Säule samt Handy und Blitz nach links schieben
def pbox(*v): return box(v[0] + PDX, v[1], v[2] + PDX, v[3])

# Hintergrund: Verlauf in abgerundetem Quadrat
grad = Image.new("RGB", (S, S))
gd = ImageDraw.Draw(grad)
top, bot = (8, 104, 198), (0, 84, 168)   # Verkehrsschild-Blau
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle(box(32, 32, 992, 992), radius=220 * K, fill=255)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)

WHITE, NAVY, PAPER, AMBER = (255, 255, 255), (30, 58, 138), (219, 234, 254), (245, 158, 11)
# Zapfsäule
d.rounded_rectangle(pbox(250, 190, 610, 820), radius=50 * K, fill=WHITE)
d.rounded_rectangle(pbox(205, 800, 655, 870), radius=30 * K, fill=WHITE)
# Display mit Zeilen
d.rounded_rectangle(pbox(292, 240, 568, 410), radius=26 * K, fill=NAVY)
for y, x2 in ((282, 530), (322, 490), (362, 440)):
    d.rounded_rectangle(pbox(322, y, x2, y + 16), radius=8 * K, fill=(147, 197, 253))
# Fahrtenbuch-Seite im Sockel der Säule
d.rounded_rectangle(pbox(292, 450, 568, 760), radius=24 * K, fill=PAPER)
for i, y in enumerate((492, 548, 604, 660, 716)):
    d.rounded_rectangle(pbox(322, y, 538 if i % 2 == 0 else 490, y + 14), radius=7 * K, fill=(96, 165, 250))
# Auto als Verkehrsschild-Piktogramm (Vorderansicht, nur der linke Teil ist sichtbar, rechts am Bildrand abgeschnitten)
# und schräg im Tankstutzen steckende Zapfpistole mit geschwungenem Schlauch
import math
from PIL import ImageChops

CLEAR = (0, 0, 0, 0)
XC = 1140                         # Mittelachse des Autos, liegt rechts außerhalb des Symbols
car = Image.new("RGBA", (S, S), CLEAR)
cd = ImageDraw.Draw(car)
def cbx(x0, y0, x1, y1): return box(XC + x0, y0, XC + x1, y1)          # Koordinaten relativ zur Mittelachse
def cpt(x, y): return ((XC + x) * K, y * K)

cd.polygon([cpt(-130, 430), cpt(130, 430), cpt(215, 560), cpt(-215, 560)], fill=WHITE)   # Dach / Fahrgastzelle
cd.ellipse(cbx(-152, 430, -108, 474), fill=WHITE)                                         # Dachecke abgerundet
cd.rounded_rectangle(cbx(-310, 578, 310, 740), radius=42 * K, fill=WHITE)                 # Karosserie (Spalt zum Dach bleibt frei)
for sx in (-1, 1):
    cd.ellipse(cbx(sx * 235 - 33, 640, sx * 235 + 33, 706), fill=CLEAR)                   # Scheinwerfer (blau)
    cd.rounded_rectangle(cbx(sx * 230 - 36, 728, sx * 230 + 36, 832), radius=8 * K, fill=WHITE)   # Räder
TX, TY = XC - 262, 604                                                                    # Tanköffnung links oben an der Karosserie
cd.ellipse(box(TX - 21, TY - 21, TX + 21, TY + 21), fill=CLEAR)
car.putalpha(ImageChops.multiply(car.getchannel("A"), mask))                              # am Rand des Symbols abschneiden
img = Image.alpha_composite(img, car)
d = ImageDraw.Draw(img)

ux, uy = -math.cos(math.radians(65)), -math.sin(math.radians(65))
HX, HY = TX + 190 * ux, TY + 190 * uy        # hinteres Ende des Griffs
MX, MY = TX + 82 * ux, TY + 82 * uy          # Übergang Griff / Rüssel
hw = 34 * K

# Schlauch wie beim Tankstellen-Piktogramm: kommt seitlich aus der Mitte der Säule, hängt als lange Schlaufe nach unten durch,
# läuft rechts wieder hoch, überkreuzt sich oben kurz und mündet im Griff der Pistole
def catmull(pts, per=60, alpha=0.5):
    """Zentripetaler Catmull-Rom-Spline durch die Punkte (glatt, ohne Überschwinger)."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + max(1e-6, math.dist(p0, p1)) ** alpha
        t2 = t1 + max(1e-6, math.dist(p1, p2)) ** alpha
        t3 = t2 + max(1e-6, math.dist(p2, p3)) ** alpha
        for k in range(per):
            t = t1 + (t2 - t1) * k / per
            def lerp(a_, b_, ta, tb):
                return tuple(((tb - t) * a_[j] + (t - ta) * b_[j]) / (tb - ta) for j in range(2))
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    out.append(pts[-1])
    return out

way = [
    (540, 455), (600, 458), (640, 478), (652, 550), (632, 640), (624, 720), (656, 775),   # aus der Säule, links hinunter
    (722, 792), (782, 752), (812, 690), (826, 640), (846, 612), (866, 604), (TX, TY),     # unten herum, rechts hoch und direkt in die Tanköffnung
]
hose = [(x * K, y * K) for x, y in catmull(way)]
for hx_, hy_ in hose:                         # dicht gestempelte Kreise: glatter Schlauch
    d.ellipse([hx_ - hw / 2, hy_ - hw / 2, hx_ + hw / 2, hy_ + hw / 2], fill=WHITE)


# Smartphone leicht schief vor der Anzeige der Zapfsäule, mit Blitz: Belege per Foto einreichen
import math
from PIL import ImageFilter

PCX, PCY, ANGLE = 478 + PDX, 378, 6  # Mittelpunkt (1024er Raster) und Drehung gegen den Uhrzeigersinn
layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ld = ImageDraw.Draw(layer)
def pb(x0, y0, x1, y1): return [(PCX + x0) * K, (PCY + y0) * K, (PCX + x1) * K, (PCY + y1) * K]
BODY, SCREEN, LIGHT = (11, 27, 68), (59, 130, 246), (219, 234, 254)
ld.rounded_rectangle(pb(-88, -158, 88, 158), radius=32 * K, fill=BODY)                 # Gehäuse
ld.rounded_rectangle(pb(-74, -132, 74, 132), radius=18 * K, fill=SCREEN)               # Display
ld.rounded_rectangle(pb(-22, -148, 22, -140), radius=4 * K, fill=(96, 165, 250))       # Lautsprecher
# „AI“ auf dem Display: die KI liest den Beleg (mit kleinem Funken)
from PIL import ImageFont

def _font(size):
    for f in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()

ld.text(((PCX - 4) * K, (PCY - 16) * K), "AI", font=_font(104 * K), fill=WHITE, anchor="mm")
sx0, sy0 = PCX + 50, PCY - 74
spark = []
for i in range(8):
    ang = math.radians(i * 45 - 90)
    rad = 24 if i % 2 == 0 else 8
    spark.append(((sx0 + rad * math.cos(ang)) * K, (sy0 + rad * math.sin(ang)) * K))
ld.polygon(spark, fill=AMBER)
for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):                                    # Sucher-Ecken
    cx_, cy_ = sx * 56, sy * 105 - 10
    ld.line([((PCX + cx_) * K, (PCY + cy_ - sy * 20) * K), ((PCX + cx_) * K, (PCY + cy_) * K), ((PCX + cx_ - sx * 20) * K, (PCY + cy_) * K)], fill=LIGHT, width=6 * K)
ld.ellipse(pb(-24, 74, 24, 122), fill=WHITE)                                           # Auslöser
ld.ellipse(pb(-17, 81, 17, 115), fill=SCREEN)
ld.ellipse(pb(-12, 86, 12, 110), fill=WHITE)
layer = layer.rotate(ANGLE, center=(PCX * K, PCY * K), resample=Image.BICUBIC)

shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
shadow.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.45)))
shadow = shadow.filter(ImageFilter.GaussianBlur(14 * K))
shadow = Image.merge("RGBA", (Image.new("L", (S, S), 0),) * 3 + (shadow.getchannel("A"),))
shifted = Image.new("RGBA", (S, S), (0, 0, 0, 0))
shifted.paste(shadow, (10 * K, 16 * K))
img = Image.alpha_composite(img, shifted)
img = Image.alpha_composite(img, layer)

# Blitz: Strahlenstern an der linken oberen Gehäuseecke
th = math.radians(ANGLE)
fx = PCX + (-88 * math.cos(th) + -158 * math.sin(th)) - 6
fy = PCY + (88 * math.sin(th) + -158 * math.cos(th)) + 2
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([(fx - 92) * K, (fy - 92) * K, (fx + 92) * K, (fy + 92) * K], fill=(255, 196, 0, 120))
img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(18 * K)))
d = ImageDraw.Draw(img)
pts = []
for i in range(16):
    ang = math.radians(i * 22.5 - 90)
    rad = 66 if i % 2 == 0 else 22
    pts.append(((fx + rad * math.cos(ang)) * K, (fy + rad * math.sin(ang)) * K))
d.polygon(pts, fill=(255, 196, 0))
d.ellipse([(fx - 17) * K, (fy - 17) * K, (fx + 17) * K, (fy + 17) * K], fill=WHITE)

for name, px in (("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 256)):
    img.resize((px, px), Image.LANCZOS).save(out / name)
import shutil
shutil.copy(out / "icon@2x.png", out.parent / "frontend" / "icon.png")  # Panel nutzt dasselbe Logo
print("ok")
