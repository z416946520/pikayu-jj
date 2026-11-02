# -*- coding: utf-8 -*-
"""Recon only: what is the JJ window showing right now?"""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
from PIL import Image
from pikafishjj import w32

w32.set_dpi_aware()
hwnd, title = w32.find_window("JJ")
print("hwnd", hwnd, title)
a = w32.WindowGrabber().grab(hwnd)
print("frame", None if a is None else a.shape)
if a is not None:
    Image.fromarray(a).save(r"D:\BuildProject\pikayu-jj\logs\jj_recon.png")
    print("saved logs/jj_recon.png")
