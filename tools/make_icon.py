# -*- coding: utf-8 -*-
"""Render the application icon (a red 帥 on a wooden disc)."""
import os
from PIL import Image, ImageDraw, ImageFont

SZ = 256
OUT = r"D:\BuildProject\pikayu-jj\assets\pikafishjj.ico"
PREVIEW = r"D:\BuildProject\pikayu-jj\assets\pikafishjj-icon.png"

img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([3, 3, SZ - 4, SZ - 4], radius=46, fill=(203, 162, 101, 255),
                    outline=(122, 83, 38, 255), width=7)
R = 94
c = SZ // 2
d.ellipse([c - R, c - R, c + R, c + R], fill=(243, 226, 166, 255),
          outline=(168, 116, 58, 255), width=6)
d.ellipse([c - R + 13, c - R + 13, c + R - 13, c + R - 13], outline=(176, 40, 40, 255), width=4)
fnt = None
for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf",
          r"C:\Windows\Fonts\simsun.ttc"):
    if os.path.exists(p):
        try:
            fnt = ImageFont.truetype(p, 118)
            break
        except Exception:
            pass
txt = "\u5e25"          # 帥
if fnt is not None:
    bb = d.textbbox((0, 0), txt, font=fnt)
    d.text(((SZ - (bb[2] - bb[0])) / 2.0 - bb[0], (SZ - (bb[3] - bb[1])) / 2.0 - bb[1]),
           txt, font=fnt, fill=(178, 30, 30, 255))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(PREVIEW)
img.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("ICON", OUT, os.path.getsize(OUT), "bytes;", "font", fnt)
