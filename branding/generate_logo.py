import os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

FD = os.path.join(os.path.dirname(__file__), 'fonts')  # put Anton (OFL, Google Fonts) TTF here
OUT = os.path.dirname(os.path.abspath(__file__))
font = TTFont(f'{FD}/anton-latin-400-normal.ttf')
gs = font.getGlyphSet(); cmap = font.getBestCmap()
CAP = 1760
S = 100 / CAP            # cap height -> 100 px
SKEW = 0.21              # ~12deg italic lean
TRACK = 14               # letter spacing (px)

def glyph(ch, x, sc=S):
    g = gs[cmap[ord(ch)]]
    pen = SVGPathPen(gs)
    # flip y; baseline at y=0; skew applied later on the group
    g.draw(TransformPen(pen, (sc, 0, 0, -sc, x, 0)))
    b = BoundsPen(gs); g.draw(b)
    return pen.getCommands(), g.width * sc, b.bounds

def poly(pts):
    return 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in pts) + ' Z'

def build(fg, accent, stripes, brackets=True, bg=None, dot=True):
    """Return (svg body, width, height). Baseline y=0, cap top y=-100."""
    parts = []
    x = 0.0
    # --- custom signature F: tall stem rising into a long overbar ---
    stem_w, bar_h, gap = 23, 16, 14
    top = -100 - gap - bar_h          # top of overbar
    fx = x
    f_parts = [
        poly([(fx, 0), (fx + stem_w, 0), (fx + stem_w, top), (fx, top)]),                 # stem
        poly([(fx + stem_w - 3, -58), (fx + stem_w + 26, -58), (fx + stem_w + 26, -40), (fx + stem_w - 3, -40)]),  # mid arm
    ]
    x = fx + stem_w + 26 + TRACK
    letters_start = x
    word = 'LETCHF'
    for ch in word:
        d, w, b = glyph(ch, x - b_left(ch))
        parts.append(('fg', d)); x += (b[2]-b[0]) * S + TRACK
    split = x
    x += 10
    for ch in 'MEDIA':
        d, w, b = glyph(ch, x - b_left(ch))
        parts.append(('ac2', d)); x += (b[2]-b[0]) * S + TRACK
    end = x - TRACK
    if dot:
        d, w, b = glyph('.', end + 8 - b_left('.'))
        parts.append(('accent', d)); end = end + 8 + (b[2]-b[0]) * S
    # overbar spans across LETCHF with sharp angled cut (cut is vertical pre-skew -> reads as slash after skew? make it diagonal)
    bar_end = split - TRACK
    f_parts.append(poly([(fx, top), (bar_end + 18, top), (bar_end, top + bar_h), (fx, top + bar_h)]))
    for p in f_parts: parts.insert(0, ('fg', p))
    # --- speed stripes trailing the F ---
    sp = []
    if stripes:
        sw, sg = 9, 6
        cols = stripes
        for i, c in enumerate(cols):
            x1 = fx - (len(cols) - i) * (sw + sg)
            sp.append((c, poly([(x1, 0), (x1 + sw, 0), (x1 + sw, top), (x1, top)])))
    left = fx - (len(stripes) * 15 if stripes else 0)
    # skew everything about baseline
    def col(k):
        return {'fg': fg, 'accent': accent, 'ac2': fg}.get(k, k)
    body = ''.join(f'<path d="{d}" fill="{col(k)}"/>' for k, d in sp + parts)
    skewed = f'<g transform="matrix(1 0 {-SKEW} 1 0 0)">{body}</g>'
    # bounding box after skew: x' = x - SKEW*y ; y in [top,0]
    minx = left; maxx = end - SKEW * top
    pad_x, pad_y = 40, 34
    br = ''
    if brackets:
        L = 30; T = 9
        x0, x1 = minx - pad_x, maxx + pad_x
        y0, y1 = top - pad_y, 0 + pad_y
        c = fg
        br = ''.join(f'<path d="{poly(p)}" fill="{c}"/>' for p in [
            [(x0,y0),(x0+L,y0),(x0+L,y0+T),(x0+T,y0+T),(x0+T,y0+L),(x0,y0+L)],
            [(x1,y0),(x1-L,y0),(x1-L,y0+T),(x1-T,y0+T),(x1-T,y0+L),(x1,y0+L)],
            [(x0,y1),(x0+L,y1),(x0+L,y1-T),(x0+T,y1-T),(x0+T,y1-L),(x0,y1-L)],
            [(x1,y1),(x1-L,y1),(x1-L,y1-T),(x1-T,y1-T),(x1-T,y1-L),(x1,y1-L)],
        ])
        minx, maxx, ytop, ybot = x0, x1, y0, y1
    else:
        ytop, ybot = top, 0
    return skewed + br, (minx, ytop, maxx - minx, ybot - ytop)

_b = {}
def b_left(ch):
    if ch not in _b:
        b = BoundsPen(gs); gs[cmap[ord(ch)]].draw(b); _b[ch] = b.bounds[0] * S
    return _b[ch]

def write(name, body, vb, bg=None, margin=60, square=False):
    x, y, w, h = vb
    x -= margin; y -= margin; w += 2*margin; h += 2*margin
    if square:
        s = max(w, h); x -= (s-w)/2; y -= (s-h)/2; w = h = s
    rect = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}">{rect}{body}</svg>'
    open(f'{OUT}/{name}.svg', 'w').write(svg)

ORANGE, PINK, VIOLET = '#FF7A2F', '#FF3D6E', '#7B3DFF'
GRAD = [ORANGE, PINK, VIOLET]

# 1 primary: black on white, colour stripes + accent dot
write('fletchfmedia-primary', *build('#0A0A0A', PINK, GRAD), bg='#FFFFFF')
# 2 reversed on black
write('fletchfmedia-dark', *build('#FFFFFF', PINK, GRAD), bg='#0A0A0A')
# 3 cream / mono
write('fletchfmedia-mono', *build('#0A0A0A', '#0A0A0A', ['#0A0A0A']*3), bg='#F6EEE3')
# 4 no-bracket wordmark (transparent) for overlays/watermarks
write('fletchfmedia-wordmark-white', *build('#FFFFFF', PINK, GRAD, brackets=False))
write('fletchfmedia-wordmark-black', *build('#0A0A0A', PINK, GRAD, brackets=False))

# 5 icon: signature F + stripes in viewfinder (square), for avatars/watermark bug
def icon(fg, bg, stripes):
    stem_w, bar_h, gap = 23, 16, 14
    top = -100 - gap - bar_h
    ps = [poly([(0,0),(stem_w,0),(stem_w,top),(0,top)]),
          poly([(0,top),(78,top),(64,top+bar_h),(0,top+bar_h)]),
          poly([(stem_w-3,-66),(60,-66),(50,-48),(stem_w-3,-48)])]
    body = ''.join(f'<path d="{p}" fill="{fg}"/>' for p in ps)
    sp = ''.join(f'<path d="{poly([(x1,0),(x1+9,0),(x1+9,top),(x1,top)])}" fill="{c}"/>'
                 for i, c in enumerate(stripes) for x1 in [-(3-i)*15])
    g = f'<g transform="matrix(1 0 {-SKEW} 1 0 0)">{sp}{body}</g>'
    cx = (-45 + 78 - SKEW*top)/2; cy = top/2
    half = 120; L, T = 40, 10
    x0, x1, y0, y1 = cx-half, cx+half, cy-half, cy+half
    br = ''.join(f'<path d="{poly(p)}" fill="{fg}"/>' for p in [
        [(x0,y0),(x0+L,y0),(x0+L,y0+T),(x0+T,y0+T),(x0+T,y0+L),(x0,y0+L)],
        [(x1,y0),(x1-L,y0),(x1-L,y0+T),(x1-T,y0+T),(x1-T,y0+L),(x1,y0+L)],
        [(x0,y1),(x0+L,y1),(x0+L,y1-T),(x0+T,y1-T),(x0+T,y1-L),(x0,y1-L)],
        [(x1,y1),(x1-L,y1),(x1-L,y1-T),(x1-T,y1-T),(x1-T,y1-L),(x1,y1-L)]])
    return g + br, (x0, y0, x1-x0, y1-y0)
write('fletchfmedia-icon-dark', *icon('#FFFFFF', None, GRAD), bg='#0A0A0A', margin=40, square=True)
write('fletchfmedia-icon-light', *icon('#0A0A0A', None, GRAD), bg='#FFFFFF', margin=40, square=True)
print('ok')
