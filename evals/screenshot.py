"""Screenshot evals: exact ANSI stream -> parsed cells + PNG artifacts.

Parses TerminalRenderer.to_string() output (SGR colors + half-block/text
chars) into per-cell (fg, bg, dim, char) rows -- precisely what a terminal
displays -- and renders review PNGs. Saved under asd-ste100/shots/.
"""

import os
import re

import cv2
import numpy as np

from client.render import TerminalRenderer, PALETTE_RGB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(ROOT, "asd-ste100", "shots")
DIM = 0.62  # faint-row brightness, matches real terminals

_SGR = re.compile(r"\x1b\[([0-9;]+)m")


def _sgr_to_idx(code, bg):
    if 30 <= code <= 37 and not bg:
        return code - 30
    if 90 <= code <= 97 and not bg:
        return code - 90 + 8
    if 40 <= code <= 47 and bg:
        return code - 40
    if 100 <= code <= 107 and bg:
        return code - 100 + 8
    return None


def ansi_to_cells(s, cols=80):
    """Parse to_string() output -> rows of (fg, bg, dim, char)."""
    rows = []
    for line in s.split("\n"):
        if not line:
            continue
        cells = []
        fg = bg = 7
        dim = False
        i = 0
        while i < len(line):
            if line[i] == "\x1b":
                m = _SGR.match(line, i)
                assert m, line[i:i + 12]
                for code in [int(x) for x in m.group(1).split(";")]:
                    if code == 0:
                        fg, bg, dim = 7, 0, False
                    elif code == 2:
                        dim = True
                    else:
                        v = _sgr_to_idx(code, False)
                        if v is not None:
                            fg = v
                        v = _sgr_to_idx(code, True)
                        if v is not None:
                            bg = v
                i = m.end()
            else:
                cells.append((fg, bg, dim, line[i]))
                i += 1
        assert len(cells) == cols, "row has %d cells" % len(cells)
        rows.append(cells)
    return rows


def cells_to_png(rows, path, scale=10):
    """Draw cells to PNG: half-block halves + monospace glyphs for text.

    Text uses Menlo (macOS terminal font) so screenshots match a real
    terminal; falls back to Hershey glyphs when Menlo is unavailable.
    """
    from PIL import Image, ImageDraw, ImageFont
    h = len(rows)
    w = len(rows[0])
    img = np.zeros((h * 2 * scale, w * scale, 3), np.uint8)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",
                                  2 * scale - 4)
        pil_img = Image.new("RGB", (w * scale, h * 2 * scale))
        mask_img = Image.new("L", (w * scale, h * 2 * scale))
        draw = ImageDraw.Draw(pil_img)
        mask_draw = ImageDraw.Draw(mask_img)
        use_pil = True
    except Exception:
        font, pil_img, mask_img, draw, mask_draw, use_pil = (
            None, None, None, None, None, False)
    for r, cells in enumerate(rows):
        for c, (fg, bg, dim, ch) in enumerate(cells):
            k = DIM if dim else 1.0
            f = (np.array(PALETTE_RGB[fg], float) * k).astype(int)[::-1]
            b = (np.array(PALETTE_RGB[bg], float) * k).astype(int)[::-1]
            y0, x0 = r * 2 * scale, c * scale
            if ch == "\u2580":
                img[y0:y0 + scale, x0:x0 + scale] = f
                img[y0 + scale:y0 + 2 * scale, x0:x0 + scale] = b
            else:
                img[y0:y0 + 2 * scale, x0:x0 + scale] = b
                if use_pil:
                    draw.text((x0, y0 - 2), ch, font=font,
                              fill=tuple(int(v) for v in f[::-1]))
                    mask_draw.text((x0, y0 - 2), ch, font=font, fill=255)
                else:
                    cv2.putText(img, ch, (x0 + 1, y0 + 2 * scale - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                                tuple(int(v) for v in f), 1, cv2.LINE_AA)
    if use_pil:
        text_layer = np.asarray(pil_img)[:, :, ::-1]
        mask = np.asarray(mask_img) > 0
        img[mask] = text_layer[mask]
    cv2.imwrite(path, img)
    return img


SAMPLE_GAME = {"aim": [0.1, -0.2], "runs": {"HOME": 3, "AWAY": 1},
               "arcade": 1250, "inning": 2, "half": "bottom",
               "count": {"balls": 2, "strikes": 1}, "outs": 1}


NAMES_48 = ("menu", "calibrate", "field_bat", "field_pitch", "stance",
            "action", "pause", "nserver")


def _paint(name, mode="80x48"):
    r = TerminalRenderer(mode=mode)
    g = dict(SAMPLE_GAME)
    if name == "menu":
        r.render_menu(dwell_frac=0.5, dwell_side="BAT")
    elif name == "calibrate":
        r.render_calibrate(0.4)
    elif name == "field_bat":
        g["ball_progress"] = 0.55
        r.render_field(g, view="bat")
    elif name == "field_pitch":
        g["aim"] = [0.2, 0.1]
        g["ball_progress"] = 0.3
        r.render_field(g, view="pitch")
    elif name == "field24":
        g["ball_progress"] = 0.55
        r.render_field(g, view="bat")
    elif name == "stance":
        r.render_field(g, view="bat")
        r.render_stance("HOLD STANCE", 0.6)
    elif name == "action":
        g["contact_flash"] = True
        r.render_field(g, view="bat")
        r.render_action("SWING!")
    elif name == "pause":
        r.render_field(g, view="bat")
        r.render_pause()
    elif name == "nserver":
        r.clear()
        r.render_message("NO SERVER", "127.0.0.1:8765")
    else:
        raise ValueError(name)
    return r.to_string()


def capture_all(out_dir=SHOT_DIR):
    """Render every screen -> {name: {"ansi": str, "cells": rows, "png": path}}."""
    os.makedirs(out_dir, exist_ok=True)
    shots = {}
    for name in NAMES_48:
        ansi = _paint(name)
        cells = ansi_to_cells(ansi)
        path = os.path.join(out_dir, name + ".png")
        cells_to_png(cells, path)
        shots[name] = {"ansi": ansi, "cells": cells, "png": path}
    ansi = _paint("field24", mode="80x24")
    cells = ansi_to_cells(ansi)
    path = os.path.join(out_dir, "field24.png")
    cells_to_png(cells, path)
    shots["field24"] = {"ansi": ansi, "cells": cells, "png": path}
    return shots


def fg_histogram(cells):
    hist = {}
    for row in cells:
        for fg, _bg, _dim, _ch in row:
            hist[fg] = hist.get(fg, 0) + 1
    return hist
