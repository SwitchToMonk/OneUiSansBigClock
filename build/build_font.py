"""Rebuild the OPPO big-clock font slot using the OneUI Sans Clock outlines.

Keeps the original's layout footprint (advance widths, vertical ink band, line
metrics) so the clock stays the same size and position; only letterforms change.
"""
import os
import io
import sys
import zipfile
from fontTools.ttLib import TTFont
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.misc.transform import Transform

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

SRC_APK = os.path.join(PKG, "source-apk", "OPPOBigClockSansNoColon.apk")
SLOT_ENTRY = "assets/fonts/LOCKSCREENOPPOBigClockNoColon.ttf"
SRC = os.path.join(PKG, "fonts", "OneUISansClockHRd-wght100HEGT700.ttf")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "newclock.ttf")

with zipfile.ZipFile(SRC_APK) as _z:
    orig = TTFont(io.BytesIO(_z.read(SLOT_ENTRY)))
src = TTFont(SRC)
o_gs = orig.getGlyphSet()
s_gs = src.getGlyphSet()
o_cmap = orig.getBestCmap()
s_cmap = src.getBestCmap()
DIGITS = "0123456789"


def bounds(gs, name):
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    return bp.bounds


# --- footprint targets from the original font -----------------------------
o_tops = [bounds(o_gs, o_cmap[ord(d)])[3] for d in DIGITS]
o_bots = [bounds(o_gs, o_cmap[ord(d)])[1] for d in DIGITS]
o_center = (max(o_tops) + min(o_bots)) / 2.0
o_adv = orig["hmtx"]["zero"][0]

# --- uniform scale so the digit advance width matches exactly -------------
k = o_adv / float(src["hmtx"]["zero"][0])

# --- vertical offset so the new ink band is centred on the original's -----
s_tops = [bounds(s_gs, s_cmap[ord(d)])[3] * k for d in DIGITS]
s_bots = [bounds(s_gs, s_cmap[ord(d)])[1] * k for d in DIGITS]
dy = o_center - (max(s_tops) + min(s_bots)) / 2.0

xf = Transform(k, 0, 0, k, 0, dy)

# --- transform outlines, measuring each one as we go ----------------------
# (measure against the source glyph set *before* it is replaced, otherwise the
#  lazy glyph set would hand back the already-transformed outlines)
new_glyphs = {}
new_lsb = {}
for name in src.getGlyphOrder():
    pen = TTGlyphPen(s_gs)
    bpen = BoundsPen(s_gs)
    s_gs[name].draw(TransformPen(pen, xf))
    s_gs[name].draw(TransformPen(bpen, xf))
    gl = pen.glyph()
    gl.recalcBounds(None)
    new_glyphs[name] = gl
    new_lsb[name] = gl.xMin if gl.numberOfContours else 0

# colon stays invisible, like the original "NoColon" design
new_glyphs["colon"] = TTGlyphPen(None).glyph()
new_lsb["colon"] = 0

# .notdef: reuse the original box so any missing glyph renders as before
pen = TTGlyphPen(o_gs)
o_gs[".notdef"].draw(pen)
new_glyphs[".notdef"] = pen.glyph()

src["glyf"].glyphs = new_glyphs

# --- horizontal metrics: original advances, sidebearings matching outlines -
new_hmtx = {}
for name in src.getGlyphOrder():
    adv = orig["hmtx"][name][0]
    lsb = orig["hmtx"][name][1] if name == ".notdef" else new_lsb[name]
    new_hmtx[name] = (adv, lsb)
src["hmtx"].metrics = new_hmtx

# --- vertical metrics: copy the original's exactly ------------------------
src["hhea"].ascent = orig["hhea"].ascent          # 700
src["hhea"].descent = orig["hhea"].descent        # -3540
src["hhea"].lineGap = orig["hhea"].lineGap        # 0

o2, s2 = orig["OS/2"], src["OS/2"]
for attr in ("sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent",
             "usWinDescent", "sxHeight", "sCapHeight", "fsSelection"):
    setattr(s2, attr, getattr(o2, attr))
s2.usWeightClass = 400

# drop tables the original slot did not have
for tag in ("vhea", "vmtx", "DSIG"):
    if tag in src:
        del src[tag]

# --- name table -----------------------------------------------------------
family = "OneUiSansBigClock"
ps = "OneUiSansBigClock"
for nid, val in ((1, family), (2, "Regular"), (3, family + ";1.000"),
                 (4, family), (6, ps), (16, family), (17, "Regular")):
    for platform, enc, lang in ((3, 1, 0x409), (1, 0, 0)):
        src["name"].setName(val, nid, platform, enc, lang)

# keep the base font's head timestamp so rebuilds are byte-identical
src.recalcTimestamp = False
src.save(OUT)

# --- verify what was actually written ------------------------------------
chk = TTFont(OUT)
cg = chk.getGlyphSet()
c_cmap = chk.getBestCmap()
print("scale k = %.4f   dy = %.1f" % (k, dy))
print("%-5s %-34s %-34s" % ("char", "original  adv / ink", "new  adv / ink"))
for ch in DIGITS + ":":
    g, n = o_cmap[ord(ch)], c_cmap[ord(ch)]
    print("%-5s adv=%-4d %-24s adv=%-4d %s" % (
        ch, orig["hmtx"][g][0], bounds(o_gs, g),
        chk["hmtx"][n][0], bounds(cg, n)))

problems = []
for nm in chk.getGlyphOrder():
    gl = chk["glyf"][nm]
    if gl.numberOfContours == 0:
        continue
    gl.recalcBounds(chk["glyf"])
    adv, lsb = chk["hmtx"][nm]
    if gl.xMin != lsb or gl.xMax > adv or gl.yMin < -4000 or gl.yMax > 1000:
        problems.append((nm, gl.xMin, lsb, gl.xMax, adv, gl.yMin, gl.yMax))
print("upem %d  glyphs %d  asc/desc %d/%d" % (
    chk["head"].unitsPerEm, len(chk.getGlyphOrder()),
    chk["hhea"].ascent, chk["hhea"].descent))
print("metric problems:", problems if problems else "none")
print("tables", sorted(chk.keys()))
