"""Regenerate the Campus app icons from the source PNG.

    python deploy/assets/make_icons.py        # run from the repo root

Source: deploy/assets/campus-icon-source.png (a wide app-icon-style render
with the rounded-square badge centred). We crop to the largest centred
square and emit:

  deploy/campus.ico                  - installer (SetupIconFile) + campus-app.exe
  frontend/app/icon.png      (512)   - Next App Router <link rel=icon>
  frontend/app/apple-icon.png (180)  - iOS home screen
  frontend/app/favicon.ico           - /favicon.ico  (16/32/48)

Needs Pillow (backend/.venv has it):
  backend/.venv/Scripts/python deploy/assets/make_icons.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
SRC = os.path.join(HERE, "campus-icon-source.png")

im = Image.open(SRC).convert("RGBA")
w, h = im.size
side = min(w, h)
left, top = (w - side) // 2, (h - side) // 2
sq = im.crop((left, top, left + side, top + side))
print(f"source {w}x{h} -> centred square {sq.size}")


def r(px):
    return sq.resize((px, px), Image.LANCZOS)


ico_sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
r(256).save(os.path.join(REPO, "deploy", "campus.ico"), format="ICO", sizes=ico_sizes)

app = os.path.join(REPO, "frontend", "app")
r(512).save(os.path.join(app, "icon.png"), format="PNG")
r(180).save(os.path.join(app, "apple-icon.png"), format="PNG")
r(256).save(
    os.path.join(app, "favicon.ico"),
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48)],
)
print("regenerated deploy/campus.ico and frontend/app/{icon.png,apple-icon.png,favicon.ico}")
