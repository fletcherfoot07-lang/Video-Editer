"""Generate the FletchFMedia logo set (bold, black & white).

Needs: pip install fonttools brotli, and the Anton TTF (OFL, Google Fonts)
in ./fonts/anton-latin-400-normal.ttf (or set FONT_DIR).
"""
import os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

HERE = os.path.dirname(os.path.abspath(__file__))
FD = os.environ.get('FONT_DIR', os.path.join(HERE, 'fonts'))
OUT = HERE
font = TTFont(f'{FD}/anton-latin-400-normal.ttf')
gs = font.getGlyphSet(); cmap = font.getBestCmap()
CAP = 1760
S = 100 / CAP            # cap height -> 100 px
SKEW = 0.0               # upright (no italic)
BOLD = 5                 # extra stroke weight added to every letter (px)
TRACK = 12 + BOLD        # letter spacing (px), widened to absorb the stroke

BLACK, WHITE = '#0A0A0A', '#FFFFFF'

# signature F geometry (cap height = 100)
# Taken from Anton's own F (stem 352u, arm 339u at 798-1137u) so the F has
# exactly the same stroke weight as every other letter. All F parts get the
# same BOLD stroke as the letters.
STEM_W = 352 * S
BAR_H = 339 * S
GAP = 16 + BOLD
TOP = -100 - GAP - BAR_H           # top of overbar
ARM_W, ARM_Y0, ARM_Y1 = 332 * S, -1137 * S, -798 * S
STRIPES = [1.5, 3.5, 5.5]     # speed stripes, thin -> thick toward the F
STRIPE_GAP = 6 + BOLD


def glyph(ch, x):
    g = gs[cmap[ord(ch)]]
    pen = SVGPathPen(gs)
    g.draw(TransformPen(pen, (S, 0, 0, -S, x, 0)))   # flip y, baseline y=0
    b = BoundsPen(gs); g.draw(b)
    return pen.getCommands(), b.bounds


_b = {}
def b_left(ch):
    if ch not in _b:
        b = BoundsPen(gs); gs[cmap[ord(ch)]].draw(b); _b[ch] = b.bounds[0] * S
    return _b[ch]


def poly(pts):
    return 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in pts) + ' Z'


def stripes():
    out, x = [], 0.0
    for w in reversed(STRIPES):
        x -= STRIPE_GAP + w
        out.append(poly([(x, 0), (x + w, 0), (x + w, TOP), (x, TOP)]))
    return out, x


def stroked(fg, paths):
    return (f'<g fill="{fg}" stroke="{fg}" stroke-width="{BOLD}" stroke-linejoin="miter" '
            f'stroke-miterlimit="4">' + ''.join(f'<path d="{d}"/>' for d in paths) + '</g>')


def corners(fg, x0, y0, x1, y1, L, T):
    return ''.join(f'<path d="{poly(p)}" fill="{fg}"/>' for p in [
        [(x0,y0),(x0+L,y0),(x0+L,y0+T),(x0+T,y0+T),(x0+T,y0+L),(x0,y0+L)],
        [(x1,y0),(x1-L,y0),(x1-L,y0+T),(x1-T,y0+T),(x1-T,y0+L),(x1,y0+L)],
        [(x0,y1),(x0+L,y1),(x0+L,y1-T),(x0+T,y1-T),(x0+T,y1-L),(x0,y1-L)],
        [(x1,y1),(x1-L,y1),(x1-L,y1-T),(x1-T,y1-T),(x1-T,y1-L),(x1,y1-L)]])


def build(fg, brackets=True):
    """Return (svg body, viewbox). Baseline y=0, cap top y=-100."""
    shapes, letters = [], []
    # tall stem + mid arm of the signature F
    shapes.append(poly([(0, 0), (STEM_W, 0), (STEM_W, TOP), (0, TOP)]))
    shapes.append(poly([(STEM_W - 1, ARM_Y0), (STEM_W + ARM_W, ARM_Y0),
                        (STEM_W + ARM_W, ARM_Y1), (STEM_W - 1, ARM_Y1)]))
    x = STEM_W + ARM_W + TRACK
    for ch in 'LETCHF':
        d, b = glyph(ch, x - b_left(ch)); letters.append(d); x += (b[2] - b[0]) * S + TRACK
    split = x
    x += 8
    for ch in 'MEDIA':
        d, b = glyph(ch, x - b_left(ch)); letters.append(d); x += (b[2] - b[0]) * S + TRACK
    d, b = glyph('.', x - 4 - b_left('.')); letters.append(d)
    end = x - 4 + (b[2] - b[0]) * S + BOLD / 2
    # chunky square-ended overbar across LETCHF
    bar_end = split - TRACK + BOLD / 2
    shapes.append(poly([(0, TOP), (bar_end, TOP), (bar_end, TOP + BAR_H), (0, TOP + BAR_H)]))

    sp, left = stripes()
    body = stroked(fg, sp + shapes + letters)
    g = f'<g transform="matrix(1 0 {-SKEW} 1 0 0)">{body}</g>'
    left -= BOLD / 2; TOP_ = TOP - BOLD / 2
    minx, maxx = left, end - SKEW * TOP
    if not brackets:
        return g, (minx, TOP, maxx - minx, -TOP + BOLD / 2)
    x0, x1, y0, y1 = minx - 40, maxx + 40, TOP_ - 34, 34
    return g + corners(fg, x0, y0, x1, y1, 38, 14), (x0, y0, x1 - x0, y1 - y0)


def icon(fg):
    R = 72
    ps = [poly([(0, 0), (STEM_W, 0), (STEM_W, TOP), (0, TOP)]),
          poly([(0, TOP), (R, TOP), (R, TOP + BAR_H), (0, TOP + BAR_H)]),
          poly([(STEM_W - 1, ARM_Y0), (STEM_W + ARM_W, ARM_Y0),
                (STEM_W + ARM_W, ARM_Y1), (STEM_W - 1, ARM_Y1)])]
    sp, left = stripes()
    g = f'<g transform="matrix(1 0 {-SKEW} 1 0 0)">{stroked(fg, sp + ps)}</g>'
    cx = (left + R) / 2; cy = TOP / 2
    h = 122
    x0, x1, y0, y1 = cx - h, cx + h, cy - h, cy + h
    return g + corners(fg, x0, y0, x1, y1, 44, 16), (x0, y0, x1 - x0, y1 - y0)


def write(name, body, vb, bg=None, margin=60, square=False):
    x, y, w, h = vb
    x -= margin; y -= margin; w += 2 * margin; h += 2 * margin
    if square:
        s = max(w, h); x -= (s - w) / 2; y -= (s - h) / 2; w = h = s
    rect = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}">'
           f'{rect}{body}</svg>')
    open(f'{OUT}/{name}.svg', 'w').write(svg)


if __name__ == '__main__':
    write('fletchfmedia-primary', *build(BLACK), bg=WHITE)
    write('fletchfmedia-dark', *build(WHITE), bg=BLACK)
    write('fletchfmedia-wordmark-black', *build(BLACK, brackets=False))
    write('fletchfmedia-wordmark-white', *build(WHITE, brackets=False))
    write('fletchfmedia-icon-dark', *icon(WHITE), bg=BLACK, margin=40, square=True)
    write('fletchfmedia-icon-light', *icon(BLACK), bg=WHITE, margin=40, square=True)
    print('ok')
