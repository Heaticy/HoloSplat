"""Regenerate the page's images and videos from the arXiv PDF, the supplementary video and the PV renders.

    <root>/methods/pointsplat/.venv/bin/python web/tools/update_assets.py [--root <RealTime-4DGS>] [--stage ...]

<root> defaults to the parent of this repository (it is the `web/` submodule of RealTime-4DGS).
Needs pdftoppm, pdftotext and ffmpeg. Re-run after `make -C paper arxiv` or a new PV cut, then look at
the images and clips before committing.

Stages:
  figures   paper figures cropped from the arXiv build above their captions
  video     the narrated video and its poster
  clips     looping clips cut from the narrated video; segments are found at its white fades and each clip is
            matched to the segment that looks like its current poster, so a re-cut PV needs no index changes
  orbits    Lite / Pro / Ultra free-viewpoint orbits of the live 0013_08 session
  compare   before/after session calibration on held-out DNA-Rendering views, for the page's sliders
  hero      0678_02 showcase (dynamic orbit and bullet time) from the newest Showcase_0678_02 run
  teaser    animated Fig. 1 (labelled, 1920 x 960) from the newest TeaserLive*_0678_02 run
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

WEB = Path(__file__).resolve().parents[1]
IMAGES = WEB / "static" / "images"
VIDEOS = WEB / "static" / "videos"
PDF = "paper/arxiv/HoloSplat_arxiv.pdf"
PV_VIDEO = "pv/final/out/holosplat_pv_web.mp4"
LIVE = "pv/runs/20261119_0440_SGT_Live0013_4GPU_Laptop/smooth"
ORBIT = LIVE + "/{arm}/tiers/{tier}/orbit360"
ORBIT_CROP = "crop=360:600:382:238"  # the performer's extent over the whole orbit, centred
SHOWCASE_GLOB = "pv/runs/*_SGT_Showcase_0678_02"
TEASER_GLOB = "pv/runs/*_SGT_TeaserLive*_0678_02"  # made by pv/teaser_live (animated paper Fig. 1); newest by date
TEASER_POSTER_S = 1.5  # source frame 90, the paper's Fig. 1 frame
HERO_CROP = "crop=540:720:240:200"  # 3:4 window holding the performer over both 0678_02 sequences
NSC_GLOB = "pv/runs/*_SGT_NSC_Slider_Candidates"  # made by pv/offline/render_nsc_slider.py
NSC_SLIDES = ("0379_09_cam25", "0536_06_cam23", "0657_05_cam22")  # visually clearest of its eight candidates
LOOP_FADE = 5  # frames of fade-out at the end and fade-in at the start of the dynamic orbit (2 x 5 frames at 30 fps)
X264 = ["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]

# name: (page, caption label, left, top, right in PDF points, render dpi, max output width)
FIGURES = {
    "teaser": (1, "1.", 58.5, 268.0, 365.4, 500, 2200),
    "teaser_plot": (1, "1.", 368.8, 282.0, 553.5, 400, 1200),  # below the plot's own title
    "method": (5, "3.", 50.0, 30.0, 562.0, 300, 2000),
    "qualitative": (8, "6.", 50.0, 28.0, 562.0, 300, 2000),
}

# The narrated video is title, problem, live card, warm-up, live, method card, overview, M0-M7 with the
# compression and recovery shots, comparison cards and shots, summary, ending, joined by white fades.
# name: (segment index, crop x, y, w, h in the 1920x1080 frame); crops drop the slide title and subtitle.
# The index (in the 2026-11-19 cut) is used only for a clip that has no poster yet; otherwise the clip is matched.
CLIPS = {
    "live": (4, 0, 70, 1920, 890),
    "split": (7, 0, 150, 1920, 800),
    "prune": (8, 0, 150, 1920, 800),
    "pca": (9, 0, 150, 1920, 800),
    "anchors": (10, 0, 150, 1920, 800),
    "restore": (13, 0, 150, 1920, 800),
    "nsc": (15, 0, 56, 1920, 1004),
    "tiers": (16, 0, 150, 1920, 800),
    "cmp_stream_a": (19, 0, 130, 1920, 868),
    "cmp_stream_b": (20, 0, 130, 1920, 868),
    "cmp_ff_a": (22, 0, 130, 1920, 868),
    "cmp_ff_b": (23, 0, 130, 1920, 868),
}
TRIM_S = 0.1  # skip the fade frames at both ends of a segment
MATCH_W, MATCH_RATIO = 160, 0.6  # thumbnail width; the best segment must differ < 0.6 x as much as the runner-up
# Comparison shots are 60 source frames at 4 ticks (8 s); the PV may hold a static data card after the footage
# until the narration ends, which the page's looping clip leaves out.
CMP_SHOT_S = 8.0


def clip_span(name, start, end):
    return start, min(end, start + CMP_SHOT_S) if name.startswith("cmp_") else end


def ffmpeg(*args):
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", *args])


def caption_top(pdf, page, label):
    """yMin (points) of the 'Figure <label>' caption on the page."""
    xml = subprocess.check_output(["pdftotext", "-f", str(page), "-l", str(page), "-bbox", pdf, "-"]).decode()
    words = re.findall(r'<word xMin="[\d.]+" yMin="([\d.]+)"[^>]*>([^<]*)</word>', xml)
    for (y, word), (_, nxt) in zip(words, words[1:]):
        if word == "Figure" and nxt == label:
            return float(y)
    raise SystemExit(f"Figure {label} caption not found on page {page}")


def crop_figure(pdf, tmp, name, page, label, left, top, right, dpi, maxw):
    stem = Path(tmp) / name
    subprocess.check_call(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-singlefile", "-png", pdf, str(stem)])
    im = Image.open(f"{stem}.png").convert("RGB")
    s = dpi / 72
    bottom = caption_top(pdf, page, label) - 3
    im = im.crop((round(left * s), round(top * s), round(right * s), round(bottom * s)))
    ink = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L").point(lambda v: 255 if v > 12 else 0)
    x0, y0, x1, y1 = ink.getbbox()
    pad = round(2 * s)  # 2 pt of white around the trimmed figure
    im = im.crop((max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, im.width), min(y1 + pad, im.height)))
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(IMAGES / f"{name}.jpg", quality=88, optimize=True, progressive=True)
    print(f"{name}.jpg {im.size[0]}x{im.size[1]}")


def figures(root):
    with tempfile.TemporaryDirectory(prefix="lichf_holosplat_") as tmp:
        for name, spec in FIGURES.items():
            crop_figure(str(root / PDF), tmp, name, *spec)


def video(root):
    shutil.copy2(root / PV_VIDEO, VIDEOS / "holosplat.mp4")
    start, end = segments(root)[0]  # title card; the live shot already has its own clip on the page
    ffmpeg("-ss", f"{(start + end) / 2:.2f}", "-i", str(VIDEOS / "holosplat.mp4"), "-frames:v", "1", "-vf", "scale=1280:-2",
           "-q:v", "3", str(IMAGES / "video_poster.jpg"))
    print("holosplat.mp4, video_poster.jpg")


def segments(root):
    """(start, end) seconds of each segment between the white fades of the narrated video."""
    with tempfile.TemporaryDirectory(prefix="lichf_holosplat_") as tmp:
        stats = Path(tmp) / "ymin.txt"
        ffmpeg("-i", str(root / PV_VIDEO), "-vf",
               f"scale=64:36,signalstats,metadata=print:key=lavfi.signalstats.YMIN:file={stats}", "-f", "null", "-")
        times, white = [], []
        for line in stats.read_text().splitlines():
            if m := re.search(r"pts_time:([\d.]+)", line):
                times.append(float(m.group(1)))
            elif m := re.search(r"YMIN=([\d.]+)", line):
                white.append(float(m.group(1)) >= 230)
    runs, start = [], None
    for t, w in zip(times, white):
        if w and start is None:
            start = t
        elif not w and start is not None:
            runs.append((start, prev))
            start = None
        prev = t
    if start is not None:
        runs.append((start, prev))
    if not runs or runs[-1][1] < times[-1]:
        runs.append((times[-1], times[-1]))
    found = [(a[1], b[0]) for a, b in zip(runs, runs[1:])]
    return found


def pv_frame(root, t):
    """Grey 480x270 frame of the narrated video at t seconds."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(root / PV_VIDEO), "-frames:v", "1",
                                   "-vf", "scale=480:270", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    return Image.frombytes("L", (480, 270), raw)


def thumb(im, w, h):
    return np.asarray(im.convert("L").resize((MATCH_W, round(MATCH_W * h / w)), Image.BILINEAR), dtype=np.float32)


def assign(root, spans):
    """Segment index of each clip: the segment whose frame 1 s before the clip's end (where the poster is taken)
    best matches the clip's current poster under the clip's crop."""
    cache = {}

    def frame(t):
        if t not in cache:
            cache[t] = pv_frame(root, t)
        return cache[t]

    picks = {}
    for name, (index, x, y, w, h) in CLIPS.items():
        poster = IMAGES / f"clip_{name}.jpg"
        if not poster.exists():
            picks[name] = index
            continue
        frames = [frame(max(start, end - TRIM_S - 1)) for start, end in (clip_span(name, *s) for s in spans)]
        ref = thumb(Image.open(poster), w, h)
        box = (x // 4, y // 4, (x + w) // 4, (y + h) // 4)
        scores = sorted((float(np.abs(thumb(f.crop(box), w, h) - ref).mean()), i) for i, f in enumerate(frames))
        (best, i), (second, _) = scores[0], scores[1]
        print(f"clip_{name}: segment {i} ({spans[i][0]:.1f}-{spans[i][1]:.1f} s), difference {best:.1f}, next {second:.1f}")
        if best > MATCH_RATIO * second:
            raise SystemExit(f"clip_{name}: no segment of {PV_VIDEO} clearly matches its poster; set its index in CLIPS "
                             "and delete the poster")
        picks[name] = i
    if len(set(picks.values())) != len(picks):
        raise SystemExit(f"two clips matched the same segment: {picks}")
    return picks


def clips(root):
    spans = segments(root)
    picks = assign(root, spans)
    for name, (_, x, y, w, h) in CLIPS.items():
        start, end = clip_span(name, *spans[picks[name]])
        out = VIDEOS / f"clip_{name}.mp4"
        ffmpeg("-ss", f"{start + TRIM_S:.2f}", "-to", f"{end - TRIM_S:.2f}", "-i", str(root / PV_VIDEO),
               "-vf", f"crop={w}:{h}:{x}:{y},scale=1280:-2", *X264, "-crf", "26", str(out))
        # animations build up from a blank slide, so the poster is taken near the end
        ffmpeg("-sseof", "-1", "-i", str(out), "-frames:v", "1", "-q:v", "4", str(IMAGES / f"clip_{name}.jpg"))
        print(f"clip_{name}.mp4 {end - start - 2 * TRIM_S:.1f}s")


def encode_frames(pattern, out, vf, crf=21, poster_s=0):
    ffmpeg("-framerate", "30", "-i", str(pattern), "-vf", vf, *X264, "-crf", str(crf), str(out))
    ffmpeg("-ss", str(poster_s), "-i", str(out), "-frames:v", "1", "-q:v", "3", str(IMAGES / f"{out.stem}.jpg"))


def orbits(root):
    for tier in ("lite", "pro", "ultra"):
        encode_frames(root / ORBIT.format(arm="calibrated", tier=tier) / "%06d.png", VIDEOS / f"orbit_{tier}.mp4", ORBIT_CROP)
        print(f"orbit_{tier}.mp4")


def compare(root):
    """Before | after session calibration on held-out DNA-Rendering views (Pro); the page splits each with a slider.
    The source clips are 60 frames, so they are slowed down 2x to give the eye time to compare."""
    runs = sorted(root.glob(NSC_GLOB))
    if not runs:
        raise SystemExit(f"no {NSC_GLOB} run")
    for name in NSC_SLIDES:
        source = runs[-1] / name / "before_after.mp4"
        out = VIDEOS / f"compare_{name}.mp4"
        ffmpeg("-i", str(source), "-vf", "setpts=2*PTS", "-r", "30", *X264, "-crf", "18", str(out))
        ffmpeg("-ss", "1", "-i", str(out), "-frames:v", "1", "-q:v", "3", str(IMAGES / f"compare_{name}.jpg"))
        print(f"compare_{name}.mp4 from {runs[-1].name}")


def hero(root):
    runs = sorted(root.glob(SHOWCASE_GLOB))
    if not runs:
        raise SystemExit(f"no {SHOWCASE_GLOB} run")
    run = runs[-1]
    for name in ("dynamic_orbit", "bullet_time"):
        n = len(json.loads((run / name / "meta.json").read_text())["frames"])
        vf, poster_s = HERO_CROP, 0
        if name == "dynamic_orbit":
            # the dance runs once, so the loop point jumps in time: dip through black over 0.3 s to hide it
            vf += f",fade=t=in:start_frame=0:nb_frames={LOOP_FADE},fade=t=out:start_frame={n - LOOP_FADE}:nb_frames={LOOP_FADE}"
            poster_s = 1
        encode_frames(run / name / "%06d.png", VIDEOS / f"hero_{name}.mp4", vf, crf=19, poster_s=poster_s)
        print(f"hero_{name}.mp4 from {run.name}/{name}: {n} frames")


def teaser(root):
    runs = sorted(root.glob(TEASER_GLOB))
    if not runs:
        raise SystemExit(f"no {TEASER_GLOB} run")
    out = VIDEOS / "teaser_live.mp4"
    # stream copy keeps the run's encode; faststart lets the page start playing before the whole file arrives
    ffmpeg("-i", str(runs[-1] / "teaser_live_web.mp4"), "-c", "copy", "-an", "-movflags", "+faststart", str(out))
    ffmpeg("-ss", str(TEASER_POSTER_S), "-i", str(out), "-frames:v", "1", "-q:v", "3", str(IMAGES / "teaser_live.jpg"))
    print(f"teaser_live.mp4 from {runs[-1].name}")


STAGES = {"figures": figures, "video": video, "clips": clips, "orbits": orbits, "compare": compare, "hero": hero,
          "teaser": teaser}


def check_no_venue():
    """The public page must never name the venue: no text file under web/ (outside .git and this script) may contain
    it, and the narrated video's title card must not carry the full cut's venue line (rows 610-630: the full cut's
    venue line spans 599-631, the web cut's centred title ends at 602)."""
    venue = re.compile(rb"c\s*v\s*p\s*r", re.I)
    text = {".html", ".css", ".js", ".md", ".json", ".svg", ".txt", ".bib"}
    hits = [str(p.relative_to(WEB)) for p in WEB.rglob("*")
            if p.suffix in text and ".git" not in p.parts and venue.search(p.read_bytes())]
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(VIDEOS / "holosplat.mp4"), "-frames:v", "1",
                                   "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    band = np.frombuffer(raw, np.uint8).reshape(1080, 1920)[610:630]
    if (band < 200).sum() > 50:
        hits.append("static/videos/holosplat.mp4 title card has a venue line; use the --web cut")
    if hits:
        raise SystemExit("venue named on the public page: " + ", ".join(hits))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=WEB.parent)
    parser.add_argument("--stage", nargs="+", choices=STAGES, default=list(STAGES))
    args = parser.parse_args()
    IMAGES.mkdir(parents=True, exist_ok=True)
    VIDEOS.mkdir(parents=True, exist_ok=True)
    for stage in args.stage:
        STAGES[stage](args.root)
    check_no_venue()


if __name__ == "__main__":
    main()
