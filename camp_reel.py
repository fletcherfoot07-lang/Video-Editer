#!/usr/bin/env python3
"""
Branded 9:16 social reel for 1st Touch Football Kickz holiday camps.

Mixes photos and video clips into one beat-synced reel:
  intro (wordmark/logo + "HOLIDAY CAMP")  ->  one shot per media item
  (photos get a Ken Burns drift then a punch-in on the beat, videos play
  through)  with bold captions  ->  "BOOK NOW" outro.

Brand: #00FF00 green, heavy font (Filson Pro Heavy if you pass --font),
official logo if you pass --logo (transparent PNG). Without them it falls
back to Inter Black and a text wordmark.

Usage:
  python3 camp_reel.py clips/3.jpg clips/2.jpg clips/1.jpg clips/drill.mp4 \
      --captions "FUN EVERY|DAY" "BUILD|CONFIDENCE" "LEARN NEW|SKILLS" "GAME|TIME" \
      --focus 0.5,0.35 0.53,0.28 0.47,0.27 0.5,0.5 \
      --logo brand/logo.png --font brand/FilsonProHeavy.otf \
      --audio audio/reference_audio.m4a -o output/camp_reel.mp4

  Caption "A|B": A is white, B sits in a green box. --focus x,y (0-1) is the
  point each photo punches in on (faces). For videos, --starts gives the
  second to start each clip from (photos ignore it).
"""
import argparse, json, os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
GREEN = (0, 255, 0)
DARK = (8, 10, 8)
WHITE = (255, 255, 255)
FALLBACK_FONT = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def ease_out(x):
    x = clamp(x); return 1 - (1 - x) ** 3

def ease_in_out(x):
    x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2

def back_out(x, s=1.7):
    x = clamp(x) - 1; return 1 + (s + 1) * x ** 3 + s * x ** 2


# ---------------------------------------------------------------- text
class Type:
    def __init__(self, path):
        self.path = path
        self.cache = {}

    def __call__(self, size):
        size = max(8, int(size))
        if size not in self.cache:
            self.cache[size] = ImageFont.truetype(self.path, size)
        return self.cache[size]


def text_size(font, s):
    l, t, r, b = font.getbbox(s)
    return r - l, b - t, l, t


def draw_text(img, s, font, cx, cy, fill, shadow=True, anchor="mm", alpha=255):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((cx + 6, cy + 8), s, font=font, fill=(0, 0, 0, int(170 * alpha / 255)), anchor=anchor)
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d.text((cx, cy), s, font=font, fill=fill + (alpha,), anchor=anchor)
    img.alpha_composite(layer)


def boxed_text(img, s, font, cx, cy, reveal=1.0, box=GREEN, ink=DARK, pad=(34, 18), tilt=-3):
    """Text in a coloured box that wipes in from the left (reveal 0..1)."""
    if reveal <= 0:
        return
    tw, th, ox, oy = text_size(font, s)
    if tw + pad[0] * 2 > W - 140:          # keep long words inside the frame
        font = ImageFont.truetype(font.path, int(font.size * (W - 140 - pad[0] * 2) / tw))
        tw, th, ox, oy = text_size(font, s)
    bw, bh = tw + pad[0] * 2, th + pad[1] * 2
    tile = Image.new("RGBA", (bw, bh), box + (255,))
    ImageDraw.Draw(tile).text((pad[0] - ox, pad[1] - oy), s, font=font, fill=ink + (255,))
    cut = int(bw * ease_out(reveal))
    if cut <= 0:
        return
    tile = tile.crop((0, 0, cut, bh)).resize((cut, bh))
    full = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    full.paste(tile, (0, 0))
    full = full.rotate(tilt, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(full, (int(cx - full.width / 2), int(cy - full.height / 2)))


# ---------------------------------------------------------------- brand mark
def make_wordmark(T, logo_path, width):
    """Return an RGBA brand mark. Uses the official logo if given."""
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        bbox = logo.getbbox()
        if bbox:
            logo = logo.crop(bbox)
        h = int(logo.height * width / logo.width)
        return logo.resize((width, h), Image.LANCZOS)
    # text fallback: "1ST TOUCH" / "FOOTBALL" / "KICKZ" stacked
    lines = [("1ST TOUCH", WHITE, 1.0), ("FOOTBALL", WHITE, 1.0), ("KICKZ", GREEN, 1.45)]
    base = 200
    rendered = []
    for s, col, k in lines:
        f = T(base * k)
        tw, th, ox, oy = text_size(f, s)
        rendered.append((s, col, f, tw, th, ox, oy))
    mw = max(r[3] for r in rendered)
    gap = 28
    mh = sum(r[4] for r in rendered) + gap * (len(rendered) - 1)
    mark = Image.new("RGBA", (mw + 40, mh + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(mark)
    y = 20
    for s, col, f, tw, th, ox, oy in rendered:
        d.text((20 + (mw - tw) / 2 - ox, y - oy), s, font=f, fill=col + (255,))
        y += th + gap
    h = int(mark.height * width / mark.width)
    return mark.resize((width, h), Image.LANCZOS)


def paste_scaled(img, mark, cx, cy, scale, alpha=1.0, rot=0):
    if scale <= 0.01 or alpha <= 0:
        return
    m = mark.resize((max(1, int(mark.width * scale)), max(1, int(mark.height * scale))), Image.LANCZOS)
    if rot:
        m = m.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        a = m.getchannel("A").point(lambda v: int(v * alpha))
        m.putalpha(a)
    img.alpha_composite(m, (int(cx - m.width / 2), int(cy - m.height / 2)))


# ---------------------------------------------------------------- media
def probe(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                   "format=duration", "-of", "json", path])
    return float(json.loads(out)["format"]["duration"])


def load_video(path, start, length):
    """Decode a clip to 30fps 1080x1920 RGB frames (cover-cropped)."""
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length + .5:.3f}",
                                   "-i", path, "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
    if len(fr) == 0:
        raise SystemExit(f"could not decode {path}")
    return fr


def photo_frame(src, t, dur, focus):
    """Ken Burns: wide drift for the first half, then a punch-in on the focus point."""
    sw, sh = src.size
    # largest 9:16 window in the source
    if sw / sh > W / H:
        bh, bw = sh, sh * W / H
    else:
        bw, bh = sw, sw * H / W
    fx, fy = focus[0] * sw, focus[1] * sh
    half = dur / 2
    if t < half:                      # wide: 1.0 -> 1.12 zoom drifting toward focus
        p = t / half
        z = 1.0 + 0.12 * ease_in_out(p)
        k = 0.35 * ease_in_out(p)
    else:                             # tight: punch in to 1.45, slow creep to 1.55
        p = (t - half) / half
        z = 1.45 + 0.10 * p
        k = 1.0
    cw, ch = bw / z, bh / z
    cx = (sw / 2) * (1 - k) + fx * k
    cy = (sh / 2) * (1 - k) + fy * k
    cx = clamp(cx, cw / 2, sw - cw / 2)
    cy = clamp(cy, ch / 2, sh - ch / 2)
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return src.resize((W, H), Image.BICUBIC, box=box)


def punch(img, amount):
    """Zoom punch (scale >1 then settle) used on every cut."""
    if amount <= 0.001:
        return img
    z = 1 + amount
    cw, ch = W / z, H / z
    return img.resize((W, H), Image.BICUBIC, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))


def grade(img):
    """Slight contrast/saturation pop + bottom vignette so captions read."""
    a = np.asarray(img).astype(np.float32)
    g = a.mean(axis=2, keepdims=True)
    a = g + (a - g) * 1.12
    a = (a - 128) * 1.06 + 128
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    shade = 1 - 0.55 * np.clip((ramp - 0.55) / 0.45, 0, 1) ** 1.5
    top = 1 - 0.25 * np.clip((0.15 - ramp) / 0.15, 0, 1)
    a = a * shade * top
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------- scenes
def stripes(img, t, alpha=1.0, color=GREEN, speed=900):
    """Diagonal green speed stripes sweeping across."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    off = (t * speed) % 260
    for i in range(-8, 14):
        x = i * 260 + off
        d.polygon([(x, 0), (x + 70, 0), (x + 70 - 900, H), (x - 900, H)], fill=color + (int(38 * alpha),))
    img.alpha_composite(layer)


def intro(t, dur, T, mark, bg_photo):
    img = Image.new("RGBA", (W, H), DARK + (255,))
    if bg_photo is not None:
        z = 1.15 - 0.08 * t / dur
        cw, ch = W / z, H / z
        bg = bg_photo.resize((W, H), Image.BICUBIC, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
        bg = Image.blend(bg, Image.new("RGB", (W, H), DARK), 0.72).convert("RGBA")
        img.alpha_composite(bg)
    stripes(img, t)
    # green bars slamming in top & bottom
    bar = ease_out(t / 0.35)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, int(W * bar), 26], fill=GREEN)
    d.rectangle([W - int(W * bar), H - 26, W, H], fill=GREEN)
    # logo pop
    s = back_out((t - 0.05) / 0.45) if t > 0.05 else 0
    paste_scaled(img, mark, W / 2, H * 0.40, s)
    # HOLIDAY CAMP box
    boxed_text(img, "HOLIDAY CAMP", T(118), W / 2, H * 0.40 + mark.height / 2 + 150, reveal=(t - 0.55) / 0.35)
    if t > 0.95:
        a = int(255 * ease_out((t - 0.95) / 0.3))
        draw_text(img, "BOOK YOUR PLACE NOW", T(54), W / 2, H * 0.40 + mark.height / 2 + 300, WHITE, alpha=a)
    return img


def shot_overlay(img, t, dur, T, mark, caption, idx, n, total_t, total):
    # small brand bug top-left
    bug_a = ease_out(t / 0.25)
    paste_scaled(img, mark, 175, 290, 0.42, alpha=bug_a)
    # caption
    if caption:
        parts = caption.split("|")
        top, box = (parts[0], parts[1]) if len(parts) > 1 else ("", parts[0])
        base_y = H * 0.74
        if top:
            p = ease_out((t - 0.12) / 0.3)
            draw_text(img, top, T(104), W / 2, base_y - 60 + 70 * (1 - p), WHITE, alpha=int(255 * p))
        boxed_text(img, box, T(128), W / 2, base_y + 85, reveal=(t - 0.25) / 0.3)
    # progress bar
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 14, int(W * total_t / total), H], fill=GREEN)


def outro(t, dur, T, mark):
    img = Image.new("RGBA", (W, H), DARK + (255,))
    stripes(img, t, speed=500)
    # green wipe that clears to reveal the dark card
    wipe = ease_in_out(t / 0.4)
    d = ImageDraw.Draw(img)
    if wipe < 1:
        d.rectangle([0, int(H * wipe), W, H], fill=GREEN)
    s = back_out((t - 0.25) / 0.45) if t > 0.25 else 0
    paste_scaled(img, mark, W / 2, H * 0.33, s * 1.05)
    y = H * 0.33 + mark.height * 1.05 / 2
    if t > 0.6:
        p = ease_out((t - 0.6) / 0.3)
        draw_text(img, "HOLIDAY CAMPS", T(112), W / 2, y + 120 + 50 * (1 - p), WHITE, alpha=int(255 * p))
    if t > 0.75:
        p = ease_out((t - 0.75) / 0.3)
        draw_text(img, "FUN  •  SKILLS  •  FRIENDS", T(50), W / 2, y + 225, GREEN, shadow=False, alpha=int(255 * p))
    # pulsing BOOK NOW button
    if t > 1.0:
        pulse = 1 + 0.04 * np.sin((t - 1.0) * 2 * np.pi / 0.53) if t > 1.35 else 1
        f = T(140 * pulse)
        boxed_text(img, "BOOK NOW", f, W / 2, y + 420, reveal=(t - 1.0) / 0.3, tilt=-2)
    if t > 1.4:
        p = ease_out((t - 1.4) / 0.3)
        draw_text(img, "LINK IN BIO", T(58), W / 2, y + 590, WHITE, alpha=int(255 * p))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 26], fill=GREEN)
    d.rectangle([0, H - 26, W, H], fill=GREEN)
    # fade out last 0.4s
    fade = clamp((dur - t) / 0.4)
    if fade < 1:
        img = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), img, fade)
    return img


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media", nargs="+", help="photos and/or videos, in order")
    ap.add_argument("-o", "--out", default="output/camp_reel.mp4")
    ap.add_argument("--captions", nargs="*", default=[])
    ap.add_argument("--focus", nargs="*", default=[], help="x,y per item (0-1)")
    ap.add_argument("--starts", nargs="*", type=float, default=[], help="video start second per item")
    ap.add_argument("--logo", help="official logo, transparent PNG")
    ap.add_argument("--font", default=FALLBACK_FONT, help="Filson Pro Heavy .otf/.ttf")
    ap.add_argument("--audio")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("--bpm", type=float, default=113)
    ap.add_argument("--beats-per-shot", type=int, default=4)
    ap.add_argument("--intro-beats", type=int, default=4)
    ap.add_argument("--outro", type=float, default=4.0, help="outro seconds")
    a = ap.parse_args()

    if a.font == FALLBACK_FONT:
        print("note: no --font given, using Inter Black in place of Filson Pro Heavy")
    if not a.logo:
        print("note: no --logo given, using a text wordmark in place of the official logo")

    T = Type(a.font)
    mark = make_wordmark(T, a.logo, 640)
    beat = 60 / a.bpm
    intro_d = a.intro_beats * beat
    shot_d = a.beats_per_shot * beat
    n = len(a.media)
    total = intro_d + n * shot_d + a.outro
    nf = int(round(total * FPS))

    items = []
    for i, p in enumerate(a.media):
        focus = tuple(map(float, a.focus[i].split(","))) if i < len(a.focus) else (0.5, 0.4)
        cap = a.captions[i] if i < len(a.captions) else ""
        if os.path.splitext(p)[1].lower() in VIDEO_EXT:
            st = a.starts[i] if i < len(a.starts) else max(0.0, (probe(p) - shot_d) / 2)
            items.append(("video", load_video(p, st, shot_d), focus, cap))
        else:
            im = Image.open(p)
            try:
                from PIL import ImageOps
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            items.append(("photo", im.convert("RGB"), focus, cap))

    bg_photo = next((photo_frame(it[1], 0, 1, it[2]) for it in items if it[0] == "photo"), None)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    silent = a.out + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                            "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", silent],
                           stdin=subprocess.PIPE)
    for f in range(nf):
        t = f / FPS
        if t < intro_d:
            img = intro(t, intro_d, T, mark, bg_photo)
        elif t < intro_d + n * shot_d:
            k = int((t - intro_d) // shot_d)
            lt = t - intro_d - k * shot_d
            kind, src, focus, cap = items[k]
            if kind == "photo":
                base = photo_frame(src, lt, shot_d, focus)
            else:
                base = Image.fromarray(src[min(int(lt * FPS), len(src) - 1)])
            # zoom punch on the cut and on the mid-shot beat (photo punch-in)
            pa = 0.09 * (1 - ease_out(lt / 0.25))
            if kind == "photo" and lt >= shot_d / 2:
                pa = 0.07 * (1 - ease_out((lt - shot_d / 2) / 0.25))
            base = grade(punch(base, pa)).convert("RGBA")
            # flash on the cut
            fl = 1 - clamp(lt / 0.12)
            if fl > 0:
                base = Image.blend(base, Image.new("RGBA", (W, H), (255, 255, 255, 255)), 0.55 * fl)
            shot_overlay(base, lt, shot_d, T, mark, cap, k, n, t, total)
            img = base
        else:
            img = outro(t - intro_d - n * shot_d, a.outro, T, mark)
        enc.stdin.write(np.asarray(img.convert("RGB")).tobytes())
    enc.stdin.close()
    enc.wait()

    if a.audio:
        subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", silent, "-ss", str(a.audio_start),
                               "-i", a.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                               "-af", f"afade=t=out:st={total - 0.8:.2f}:d=0.8", "-c:a", "aac",
                               "-b:a", "192k", "-t", f"{total:.3f}", a.out])
        os.remove(silent)
    else:
        os.replace(silent, a.out)
    print(f"wrote {a.out}  ({total:.2f}s, {n} shots)")


if __name__ == "__main__":
    main()
