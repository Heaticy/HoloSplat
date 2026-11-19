"""Regenerate the page's images and videos from the arXiv PDF and the supplementary-video outputs.

    <root>/methods/pointsplat/.venv/bin/python tools/update_assets.py [--root <RealTime-4DGS checkout>]

<root> defaults to the parent of this repository (it is the `web/` submodule of RealTime-4DGS).
Needs pdftoppm, pdftotext and ffmpeg. Figures are cropped from the arXiv build above their captions,
so re-run after `make -C paper arxiv` or a new PV cut, then look at the images before committing.
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

WEB = Path(__file__).resolve().parents[1]
IMAGES = WEB / "static" / "images"
VIDEOS = WEB / "static" / "videos"
PDF = "paper/arxiv/HoloSplat_arxiv.pdf"
PV_VIDEO = "pv/final/out/holosplat_pv_web.mp4"
PV_POSTER_S = 22  # live-demo shot of the Pro tier
ORBITS = "pv/runs/20261119_0440_SGT_Live0013_4GPU_Laptop/smooth/calibrated/tiers/{tier}/orbit360"
ORBIT_CROP = "crop=360:600:382:238"  # the performer's extent over the whole orbit, centred

# name: (page, caption label, left, top, right in PDF points, render dpi, max output width)
FIGURES = {
    "teaser": (1, "1.", 58.5, 268.0, 365.4, 500, 2200),
    "teaser_plot": (1, "1.", 368.8, 282.0, 553.5, 400, 1200),  # below the plot's own title
    "method": (5, "3.", 50.0, 30.0, 562.0, 300, 2000),
    "qualitative": (8, "6.", 50.0, 28.0, 562.0, 300, 2000),
}


def caption_top(pdf, page, label):
    """yMin (points) of the 'Figure <label>' caption on the page."""
    xml = subprocess.check_output(["pdftotext", "-f", str(page), "-l", str(page), "-bbox", pdf, "-"]).decode()
    words = re.findall(r'<word xMin="[\d.]+" yMin="([\d.]+)"[^>]*>([^<]*)</word>', xml)
    for (y, word), (_, nxt) in zip(words, words[1:]):
        if word == "Figure" and nxt == label:
            return float(y)
    raise SystemExit(f"Figure {label} caption not found on page {page}")


def crop_figure(pdf, tmp, name, page, label, left, top, right, dpi, maxw):
    stem = Path(tmp) / f"{name}"
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


def ffmpeg(*args):
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", *args])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=WEB.parent)
    root = parser.parse_args().root
    IMAGES.mkdir(parents=True, exist_ok=True)
    VIDEOS.mkdir(parents=True, exist_ok=True)

    pdf = str(root / PDF)
    with tempfile.TemporaryDirectory(prefix="lichf_holosplat_") as tmp:
        for name, spec in FIGURES.items():
            crop_figure(pdf, tmp, name, *spec)

    shutil.copy2(root / PV_VIDEO, VIDEOS / "holosplat.mp4")
    ffmpeg("-ss", str(PV_POSTER_S), "-i", str(VIDEOS / "holosplat.mp4"), "-frames:v", "1", "-vf", "scale=1280:-2",
           "-q:v", "3", str(IMAGES / "video_poster.jpg"))
    print("holosplat.mp4, video_poster.jpg")

    for tier in ("lite", "pro", "ultra"):
        frames = root / ORBITS.format(tier=tier) / "%06d.png"
        out = VIDEOS / f"orbit_{tier}.mp4"
        ffmpeg("-framerate", "30", "-i", str(frames), "-vf", ORBIT_CROP, "-c:v", "libx264", "-preset", "slow",
               "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out))
        ffmpeg("-i", str(out), "-frames:v", "1", "-q:v", "3", str(IMAGES / f"orbit_{tier}.jpg"))
        print(f"orbit_{tier}.mp4")


if __name__ == "__main__":
    main()
