#!/usr/bin/env python3
"""
Beat-synced speed-ramp editor, modelled on the reference car edit.

Reference style (measured from the reference video):
  * 9:16 vertical, 30 fps
  * ~0.5 s per shot (cuts land on the beat, ~113 BPM)
  * every shot follows a "V" speed curve: whips in fast (motion blurred),
    eases down to near-freeze slow-mo in the middle, then accelerates hard
    into the next cut
  * a small zoom punch on each cut
  * final "hero" shot is a long smooth slow-mo hold that fades to black

Usage:
  python3 speed_ramp_edit.py clips/*.mp4 -o out.mp4 [--audio song.mp3] [--bpm 113]
  python3 speed_ramp_edit.py clips/*.mp4 -o out.mp4 --cuts reference --audio audio/reference_audio.m4a
  Clips are used in the order given; the last clip becomes the hero shot.
"""
import argparse, json, subprocess, sys
import numpy as np

W, H, FPS = 1080, 1920, 30

# Cut points measured from the reference video (seconds). 15 quick shots,
# then the hero shot holds until REFERENCE_END (where the outro started).
REFERENCE_CUTS = [0.23, 0.63, 1.27, 1.80, 2.30, 2.73, 3.37, 3.87, 4.40,
                  4.80, 5.43, 5.97, 6.47, 6.87, 8.03]
REFERENCE_END = 12.47

# Colour grade: slightly lower exposure, more contrast and saturation.
GRADE = "eq=brightness=-0.04:contrast=1.12:saturation=1.25"


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate:format=duration", "-of", "json", path])
    j = json.loads(out)
    n, d = j["streams"][0]["r_frame_rate"].split("/")
    return float(n) / float(d), float(j["format"]["duration"])


def load_frames(path, start, length, w, h):
    """Decode [start, start+length] seconds as an (N,h,w,3) uint8 array, cropped to 9:16."""
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
          f"setsar=1")
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
        "-i", path, "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def v_curve(n_out, min_speed, max_speed):
    """Per-output-frame speed for one shot: fast -> slow -> fast (smooth)."""
    x = np.linspace(-1, 1, n_out)
    shape = np.abs(x) ** 2.2          # 0 in the middle, 1 at the edges
    return min_speed + (max_speed - min_speed) * shape


def hero_curve(n_out, max_speed, min_speed):
    """Fast whip in, then long ease-out into very slow motion."""
    x = np.linspace(0, 1, n_out)
    return min_speed + (max_speed - min_speed) * np.exp(-x * 4)


def render_shot(frames, src_fps, speeds, punch=0.0, fade_out=0, drift=0.0):
    """Resample frames along the speed curve. Fast sections blend all source
    frames covered by the output frame (motion blur); slow sections blend the
    two nearest frames (smooth slow-mo)."""
    n_src = len(frames)
    step = speeds * src_fps / FPS                 # source frames per output frame
    # scale the curve so it fits the available source footage
    if step.sum() > n_src - 2:
        step *= (n_src - 2) / step.sum()
    t = np.concatenate([[0], np.cumsum(step)])
    out = []
    n = len(speeds)
    for i in range(n):
        a, b = t[i], t[i + 1]
        if b - a > 1.5:                           # motion blur
            idx = np.arange(int(a), min(int(np.ceil(b)), n_src))
            f = frames[idx].astype(np.float32).mean(0)
        else:                                     # frame blend
            lo = min(int(a), n_src - 2); fr = a - lo
            f = frames[lo] * (1 - fr) + frames[lo + 1] * fr
        # zoom punch decaying over the first frames of the shot
        z = 1 + punch * np.exp(-i / 3.0)
        z += drift * (i / max(n - 1, 1)) ** 1.5   # slow push-in (hero shot)
        if z > 1.002:
            f = zoom(f, z)
        if fade_out and i >= n - fade_out:
            f = f * ((n - i) / fade_out)
        out.append(np.clip(f, 0, 255).astype(np.uint8))
    return out


def zoom(img, z):
    h, w = img.shape[:2]
    ch, cw = int(h / z), int(w / z)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    crop = img[y0:y0 + ch, x0:x0 + cw]
    yi = (np.arange(h) * ch / h).astype(int)
    xi = (np.arange(w) * cw / w).astype(int)
    return crop[yi][:, xi]


def trim_static_tail(frames, thresh=2.0):
    small = frames[:, ::16, ::16].astype(np.float32).mean(-1)
    d = np.abs(np.diff(small, axis=0)).mean((1, 2))
    end = len(frames)
    while end > 3 and d[end - 2] < thresh:
        end -= 1
    return frames[:end]


def best_window(path, length, src_fps, used=()):
    """Pick the most visually active window in the clip (the bit worth ramping),
    avoiding windows already used earlier in the edit."""
    _, dur = probe(path)
    if dur <= length:
        return 0.0, dur
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path, "-vf", "fps=10,scale=32:56,format=gray",
        "-f", "rawvideo", "-"])
    v = np.frombuffer(raw, np.uint8).reshape(-1, 56, 32).astype(float)
    m = np.abs(np.diff(v, axis=0)).mean((1, 2))
    win = max(1, int(length * 10))
    if len(m) <= win:
        return 0.0, dur
    score = np.convolve(m, np.ones(win), "valid")
    for u0, u1 in used:                       # penalise overlap with used windows
        lo = max(0, int((u0 - length) * 10)); hi = int(u1 * 10)
        score[lo:hi] -= 1e9
    if score.max() < -1e8:                    # everything used: allow repeats
        score += 1e9 * (score < -1e8)
    s = int(score.argmax()) / 10.0
    return s, length


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("-o", "--out", default="edit.mp4")
    ap.add_argument("--audio", help="music track (cuts are synced to --bpm)")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("--bpm", type=float, default=113.0)
    ap.add_argument("--beats-per-shot", type=int, default=1)
    ap.add_argument("--hero-seconds", type=float, default=4.2)
    ap.add_argument("--cuts", default=None,
                    help="comma-separated cut times in seconds (overrides --bpm grid); "
                         "use 'reference' for the reference edit's exact cut points")
    ap.add_argument("--min-speed", type=float, default=0.25)
    ap.add_argument("--max-speed", type=float, default=3.5)
    ap.add_argument("--punch", type=float, default=0.06)
    ap.add_argument("--width", type=int, default=W)
    ap.add_argument("--grade", action="store_true",
                    help="slightly darker exposure, more contrast and saturation")
    a = ap.parse_args()
    w = a.width; h = int(round(w * 16 / 9 / 2)) * 2

    shot_len = 60.0 / a.bpm * a.beats_per_shot
    cuts = None
    if a.cuts:
        cuts = REFERENCE_CUTS if a.cuts == "reference" else [float(c) for c in a.cuts.split(",")]
    enc = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
        *(["-vf", GRADE] if a.grade else []),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        a.out + ".video.mp4"], stdin=subprocess.PIPE)

    # Build the shot list. With reference cuts, cycle through the clips
    # (last clip reserved for the hero shot) until every cut slot is filled.
    seq = list(a.clips)
    if cuts and len(seq) > 1 and len(seq) - 1 < len(cuts):
        pool = seq[:-1]
        seq = [pool[i % len(pool)] for i in range(len(cuts))] + [seq[-1]]
    used = {}
    frame_pos = 0.0; total = 0
    for k, clip in enumerate(seq):
        hero = k == len(seq) - 1 and len(seq) > 1
        src_fps, _ = probe(clip)
        if hero:
            if cuts and k >= len(cuts):   # hero runs to the reference's end point
                n_out = max(int(round(REFERENCE_END * FPS)) - total, 30)
            else:
                n_out = int(round(a.hero_seconds * FPS))
            speeds = hero_curve(n_out, a.max_speed, 0.3)
        else:
            if cuts and k < len(cuts):
                n_out = int(round(cuts[k] * FPS)) - total
            else:
                frame_pos = max(frame_pos, total) + shot_len * FPS  # beat grid
                n_out = int(round(frame_pos)) - total
            n_out = max(n_out, 6)
            speeds = v_curve(n_out, a.min_speed, a.max_speed)
        need = speeds.sum() / FPS + 0.2
        prev = used.get(clip, [])
        s, l = best_window(clip, need, src_fps, prev)
        repeat = any(s < u1 and s + l > u0 for u0, u1 in prev)
        used.setdefault(clip, []).append((s, s + l))
        frames = load_frames(clip, s, l, w, h)
        if hero:                              # drop a motionless tail
            frames = trim_static_tail(frames)
        if repeat and not hero and sum(1 for _ in prev) % 2 == 1:
            frames = frames[::-1]             # reuse footage in reverse for variety
        if len(frames) < 3:
            print(f"skipping {clip}: too short", file=sys.stderr); continue
        out = render_shot(frames, src_fps, speeds, punch=0 if k == 0 else a.punch,
                          fade_out=int(0.4 * FPS) if hero else 0,
                          drift=0.08 if hero else 0.0)
        for f in out:
            enc.stdin.write(f.tobytes())
        total += len(out)
        print(f"[{k+1}/{len(seq)}] {clip}: {len(out)} frames from {s:.2f}s", file=sys.stderr)
    enc.stdin.close(); enc.wait()

    if a.audio:
        subprocess.check_call([
            "ffmpeg", "-v", "error", "-y", "-i", a.out + ".video.mp4",
            "-ss", str(a.audio_start), "-i", a.audio, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-af", f"afade=t=out:st={total/FPS-0.5:.2f}:d=0.5", a.out])
    else:
        subprocess.check_call(["mv", a.out + ".video.mp4", a.out])
    subprocess.call(["rm", "-f", a.out + ".video.mp4"])
    print(f"wrote {a.out} ({total/FPS:.2f}s)", file=sys.stderr)


if __name__ == "__main__":
    main()
