#!/usr/bin/env python3
"""
Beat-synced choir promo editor.

Takes a shot list (JSON), a music track and a white-on-black logo, and renders a
1920x1080 promo where every cut lands on a beat of the music.

  python3 choir_promo.py shots.json --clips proxy/ --audio promo_audio.wav \
      --beats beats.json --logo-full logo_full.png --logo-mark logo_mark.png \
      -o choir_promo.mp4

shots.json: list of {"clip": "C8414", "in": 1.0, "beats": 4, "zoom": "in"|"out"|"none",
                     "speed": 1.0}
beats.json: list of beat times (seconds) on the *output* timeline.
Each shot lasts `beats` beats; the shot list is laid end to end from t=0, and
the last shot is extended to the end of the audio.
"""
import argparse, json, os, subprocess, tempfile

W, H, FPS = 1920, 1080, 30


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", path]))


def shot_times(shots, beats, total):
    """Cut points: each shot consumes N beats from the beat grid."""
    times, k = [0.0], 0
    for s in shots[:-1]:
        k += s["beats"]
        times.append(beats[k])
    times.append(total)
    return times


def render_shot(src, t_in, dur, speed, zoom, out):
    nframes = round(dur * FPS)
    src_len = dur * speed
    # slow, continuous push-in / pull-out for a bit of life on every shot
    z0, z1 = {"in": (1.0, 1.08), "out": (1.08, 1.0), "none": (1.03, 1.03)}[zoom]
    z = f"({z0}+({z1}-{z0})*t/{dur:.3f})"
    vf = (f"setpts=PTS/{speed},fps={FPS},"
          f"crop=w=iw/{z}:h=ih/{z}:x=(iw-ow)/2:y=(ih-oh)/2,"
          f"scale={W}:{H}:flags=lanczos,setsar=1")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t_in:.3f}", "-t", f"{src_len + 0.5:.3f}",
         "-i", src, "-vf", vf, "-frames:v", str(nframes), "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shots")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--beats", required=True)
    ap.add_argument("--logo-full", required=True)
    ap.add_argument("--logo-mark", required=True)
    ap.add_argument("--intro-logo", type=float, nargs=2, default=(1.5, 6.5),
                    help="start/end of the big logo over the opening shot")
    ap.add_argument("--end-card", type=float, default=6.0,
                    help="seconds of logo end card at the close")
    ap.add_argument("--work", default=None)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    shots = json.load(open(a.shots))
    beats = json.load(open(a.beats))
    total = duration(a.audio)
    times = shot_times(shots, beats, total)
    work = a.work or tempfile.mkdtemp()
    os.makedirs(work, exist_ok=True)

    # 1. render each shot to exact frame length (cumulative rounding -> no drift)
    parts = []
    for i, s in enumerate(shots):
        f0, f1 = round(times[i] * FPS), round(times[i + 1] * FPS)
        out = os.path.join(work, f"shot{i:03d}.mp4")
        render_shot(os.path.join(a.clips, s["clip"] + ".mp4"), s["in"], (f1 - f0) / FPS,
                    s.get("speed", 1.0), s.get("zoom", "in"), out)
        parts.append(out)
        print(f"{i:3d} {times[i]:7.2f}-{times[i+1]:7.2f} {s['clip']} @{s['in']}", flush=True)
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{p}'\n" for p in parts)
    body = os.path.join(work, "body.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", body])

    # 2. grade, logos, fades, music
    li0, li1 = a.intro_logo
    ec0 = total - a.end_card
    fc = (
        # warm, punchy grade + soft vignette
        "[0:v]eq=contrast=1.07:saturation=1.12:gamma=0.98,"
        "colorbalance=rs=0.03:bs=-0.03:rm=0.02:bm=-0.02,vignette=PI/5,"
        f"fade=t=in:st=0:d=1.2,fade=t=out:st={ec0 - 1.0:.3f}:d=1.0[v];"
        # big logo over the opening (footage darkened under it)
        f"[1:v]format=rgba,fade=t=in:st={li0}:d=0.8:alpha=1,"
        f"fade=t=out:st={li1 - 0.8}:d=0.8:alpha=1[big];"
        f"[v]drawbox=c=black@0.35:t=fill:enable='between(t,{li0},{li1})'[vd];"
        "[vd][big]overlay=(W-w)/2:(H-h)/2:shortest=0[v1];"
        # corner watermark during the body
        f"[2:v]scale=230:-1,format=rgba,colorchannelmixer=aa=0.8,"
        f"fade=t=in:st={li1}:d=0.8:alpha=1,fade=t=out:st={ec0 - 1.5:.3f}:d=0.8:alpha=1[mk];"
        "[v1][mk]overlay=W-w-48:44[v2];"
        # end card: logo on black
        f"[3:v]format=rgba,fade=t=in:st={ec0 + 0.2:.3f}:d=1.2:alpha=1,"
        f"fade=t=out:st={total - 1.0:.3f}:d=0.9:alpha=1[ec];"
        f"[v2][ec]overlay=(W-w)/2:(H-h)/2:enable='gte(t,{ec0})',format=yuv420p[vo]"
    )
    run(["ffmpeg", "-v", "error", "-y", "-i", body,
         "-loop", "1", "-t", f"{total}", "-i", a.logo_full,
         "-loop", "1", "-t", f"{total}", "-i", a.logo_mark,
         "-loop", "1", "-t", f"{total}", "-i", a.logo_full,
         "-i", a.audio, "-filter_complex", fc, "-map", "[vo]", "-map", "4:a",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", a.out])
    print("wrote", a.out, duration(a.out))


if __name__ == "__main__":
    main()
