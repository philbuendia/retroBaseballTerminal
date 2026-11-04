"""Terminal renderer: 160x192 grid art + crisp cell-text overlay.

Art is drawn into a 160x192 palette grid and emitted as U+2580 half-block
cells (foreground = top pixels, background = bottom pixels). Text, bars and
other fine detail go through a per-cell overlay so they survive the 2x4 (80x48)
or 2x2 (80x96) downsample that majority-vote grid sampling would destroy.
Alternate terminal rows are dimmed (SGR 2) for CRT scanlines.
"""

GRID_W = 160
GRID_H = 192
BLOCK = "\u2580"
ESC = "\x1b"

# 16-color palette: representative RGB for screenshots.
PALETTE_RGB = [
    (0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0),
    (0, 0, 170), (170, 0, 170), (0, 170, 170), (170, 170, 170),
    (85, 85, 85), (255, 85, 85), (85, 255, 85), (255, 255, 85),
    (85, 85, 255), (255, 85, 255), (85, 255, 255), (255, 255, 255),
]

# Semantic color names -> palette indices (electric green turf etc.).
BLACK, RED, GREEN, BROWN, BLUE, MAGENTA, CYAN, GREY = range(8)
DKGREY, LRED, LGREEN, YELLOW, LBLUE, LMAGENTA, LCYAN, WHITE = range(8, 16)
TERRA = LRED      # terracotta dirt
TURF = GREEN      # electric green turf
CHALK = WHITE
SKIN = YELLOW
UNI_HOME = LCYAN
UNI_AWAY = LMAGENTA
BALL = WHITE
ZONE = LBLUE

FG_CODE = tuple([30 + i for i in range(8)] + [90 + i for i in range(8)])
BG_CODE = tuple([40 + i for i in range(8)] + [100 + i for i in range(8)])


MODES = {"80x24": 24, "80x48": 48, "80x96": 96}


class TerminalRenderer:
    def __init__(self, mode="80x48", bg=BLACK):
        if mode not in MODES:
            raise ValueError("mode must be one of %s" % sorted(MODES))
        self.mode = mode
        self.cols = 80
        self.rows = MODES[mode]
        self.dy = GRID_H // self.rows
        self.bg = bg
        self.fb = [[bg] * GRID_W for _ in range(GRID_H)]
        # Overlay cells: None | ("ch", char, fg, bg) | ("solid", color).
        self.ov = [[None] * self.cols for _ in range(self.rows)]
        self._last = None  # double-buffer: last emitted row strings

    # -- drawing primitives ------------------------------------------
    def clear(self, color=None):
        c = self.bg if color is None else color
        self.fb = [[c] * GRID_W for _ in range(GRID_H)]
        self.ov = [[None] * self.cols for _ in range(self.rows)]

    def set(self, x, y, color):
        if 0 <= x < GRID_W and 0 <= y < GRID_H:
            self.fb[y][x] = color

    def rect(self, x, y, w, h, color):
        for yy in range(max(y, 0), min(y + h, GRID_H)):
            row = self.fb[yy]
            for xx in range(max(x, 0), min(x + w, GRID_W)):
                row[xx] = color

    def blit(self, sprite, x, y, mapping=None, transparent="."):
        """Draw a text sprite: list of equal-length strings; each char is a
        palette key via mapping (default: char digit -> int, else skip)."""
        for dy, line in enumerate(sprite):
            for dx, ch in enumerate(line):
                if ch == transparent:
                    continue
                if mapping is not None and ch in mapping:
                    c = mapping[ch]
                elif ch.isdigit():
                    c = int(ch) % 16
                else:
                    continue
                self.set(x + dx, y + dy, c)

    def _to_cell(self, x, y):
        return x // 2, y // self.dy

    def text(self, s, x, y, fg=WHITE, bg=None, scale=1):
        """Crisp overlay text at grid coords (quantized to cells).

        scale=2 letter-spaces glyphs arcade-style ("BAT" -> "B A T").
        A solid backing box is painted into the grid first for contrast.
        """
        s = s.upper()
        c0, r0 = self._to_cell(x, y)
        glyphs = " ".join(s) if scale == 2 else s
        if bg is None:
            bg = BLACK
        # Backing box in the grid so text reads over any art.
        self.rect(c0 * 2 - 2, r0 * self.dy - 1,
                  len(glyphs) * 2 + 4, self.dy + 2, bg)
        for i, ch in enumerate(glyphs):
            c = c0 + i
            if 0 <= c < self.cols and 0 <= r0 < self.rows:
                self.ov[r0][c] = ("ch", ch, fg, bg)

    def solid_cells(self, c0, r0, w, h, color):
        """Paint solid-color overlay cells (bars, reticles, rules)."""
        for r in range(r0, r0 + h):
            if 0 <= r < self.rows:
                for c in range(c0, c0 + w):
                    if 0 <= c < self.cols:
                        self.ov[r][c] = ("solid", color)

    def dwell_bar(self, x, y, w, frac, fg=LGREEN, bg=DKGREY):
        frac = max(0.0, min(1.0, frac))
        c0, r0 = self._to_cell(x, y)
        n = max(1, w // 2)
        fill = int(n * frac)
        self.solid_cells(c0, r0, fill, 1, fg)
        self.solid_cells(c0 + fill, r0, n - fill, 1, bg)

    # -- overlays ------------------------------------------------------
    def render_menu(self, options=("BAT", "PITCH"), dwell_frac=0.0,
                    dwell_side=None, auto_pick_s=None):
        self.clear(BLUE)
        self.rect(0, 0, GRID_W, 20, BLACK)
        self.text("RETRO DIAMOND", 26, 6, YELLOW, scale=2)
        self.text("RAISE HAND + HOLD 2S", 42, 26, WHITE)
        if auto_pick_s is not None:
            self.text("AUTO-BAT %dS" % int(auto_pick_s + 0.5), 56, 158,
                      GREY)
        for i, opt in enumerate(options):
            tx = 24 + i * 64
            hi = (dwell_side == opt)
            tile = CYAN if hi else DKGREY
            self.rect(tx - 6, 60, 56, 40, tile)
            spaced = len(opt) * 2 - 1  # scale=2 cells per option char
            start_x = (tx - 6) + (56 - spaced * 2) // 2
            self.text(opt, start_x, 74, BLACK if hi else WHITE,
                      bg=tile, scale=2)
        self.text("BAT", 8, 110, WHITE)
        self.text("PITCH", 118, 110, WHITE)
        self.text("HOLD TO SELECT", 50, 130, GREY)
        self.dwell_bar(30, 142, 100, dwell_frac)

    def render_calibrate(self, frac):
        self.clear(BLACK)
        self.text("STEP INTO FRAME", 34, 60, WHITE, scale=2)
        self.rect(55, 80, 50, 80, DKGREY)  # silhouette outline box
        self.rect(60, 85, 40, 70, BLACK)
        self.text("CALIBRATING", 54, 168, YELLOW)
        self.dwell_bar(30, 178, 100, frac, fg=YELLOW)

    def render_stance(self, msg="HOLD STANCE", held_frac=0.0):
        self.text(msg, 48, 168, LGREEN)
        self.dwell_bar(30, 178, 100, held_frac, fg=LGREEN)

    def render_action(self, label="SWING!"):
        self.rect(40, 80, 80, 24, BLACK)
        spaced = (len(label) * 2 - 1) * 2  # scale=2 px width
        self.text(label, 40 + (80 - spaced) // 2, 88, LRED, scale=2)

    def render_pause(self):
        self.rect(30, 70, 100, 52, BLACK)
        self.rect(30, 70, 100, 3, YELLOW)
        self.rect(30, 119, 100, 3, YELLOW)
        self.text("PAUSED", 68, 84, YELLOW, scale=2)
        self.text("UNCROSS ARMS", 56, 106, WHITE)

    def render_field(self, game=None, view="bat"):
        """First-person view: "bat" from behind the plate, else the mound."""
        game = game or {}
        if view == "pitch":
            self._render_pitcher_view(game)
        else:
            self._render_batter_view(game)
        self._scoreboard(game)

    def _scoreboard(self, game):
        self.rect(0, GRID_H - 24, GRID_W, 24, BLACK)
        runs = game.get("runs", {}) or {}
        home = runs.get("HOME", runs.get("home", 0))
        away = runs.get("AWAY", runs.get("away", 0))
        arcade = game.get("arcade", 0)
        inning = game.get("inning", 1)
        half = game.get("half", "-")
        count = game.get("count", {}) or {}
        balls = count.get("balls", 1)
        strikes = count.get("strikes", 1)
        outs = game.get("outs", 0)
        half_ch = half[0].upper() if half else "-"
        self.text("H%d A%d I%d%s" % (home, away, inning, half_ch),
                  4, GRID_H - 20, WHITE)
        self.text("B%d S%d O%d" % (balls, strikes, outs),
                  4, GRID_H - 12, YELLOW)
        self.text("%d PTS" % arcade, 104, GRID_H - 16, LGREEN)

    def _render_batter_view(self, game):
        """From the plate: pitcher on the mound, ball flying at you."""
        self.clear(TURF)
        cx = GRID_W // 2
        # Sky, stands + billboard.
        self.rect(0, 0, GRID_W, 34, BLUE)
        self.rect(0, 30, GRID_W, 4, DKGREY)
        self.rect(48, 4, 64, 16, MAGENTA)
        self.text("RETRO", 66, 8, YELLOW)
        # Mound + pitcher sprite (away uniform).
        for i, w in enumerate((28, 24, 20)):
            self.rect(cx - w // 2, 84 + i * 3, w, 3, TERRA)
        px, py = cx - 7, 52  # pitcher top-left
        self.rect(px + 2, py, 10, 4, UNI_AWAY)      # cap
        self.rect(px + 2, py + 4, 10, 8, SKIN)      # head
        self.rect(px, py + 12, 14, 16, UNI_AWAY)    # torso
        self.rect(px - 5, py + 13, 5, 10, SKIN)     # glove arm
        self.rect(px + 14, py + 8, 5, 10, SKIN)     # throwing arm up
        self.rect(px + 1, py + 28, 5, 10, WHITE)    # legs
        self.rect(px + 8, py + 28, 5, 10, WHITE)
        # The pitch: white ball grows as it approaches the plate.
        prog = game.get("ball_progress")
        if prog is not None:
            prog = max(0.0, min(1.0, prog))
            by = int(92 + prog * 58)
            sz = 2 + int(prog * 5)
            self.rect(cx - sz // 2, by - sz // 2, sz, sz, BALL)
            self.rect(cx - sz // 2, by + sz // 2 - 1, sz, 1, GREY)
        # Contact flash star at the plate.
        if game.get("contact_flash"):
            self.rect(cx - 10, 148, 20, 4, YELLOW)
            self.rect(cx - 2, 140, 4, 20, YELLOW)
            self.rect(cx - 6, 144, 12, 12, WHITE)
        # Plate timing brackets (where contact happens).
        zc, zr = self._to_cell(cx - 12, 140)
        for dc, dr in ((0, 0), (11, 0), (0, 5), (11, 5)):
            self.solid_cells(zc + dc, zr + dr, 2, 1, CHALK)
        # Your own bat intrudes from the right edge, above the board.
        for i in range(24):
            self.set(158 - i, 166 - i * 2 // 3, BROWN)
            self.set(157 - i, 166 - i * 2 // 3, BROWN)
        self.rect(146, 157, 8, 4, BROWN)

    def _render_pitcher_view(self, game):
        """From the mound: catcher, glove target, zone frame, dirt."""
        self.clear(TURF)
        cx = GRID_W // 2
        # Stands + backstop net behind the catcher.
        self.rect(0, 0, GRID_W, 44, BLUE)
        self.rect(0, 40, GRID_W, 4, DKGREY)
        self.rect(cx - 34, 48, 68, 66, BLACK)
        for gx in range(cx - 34, cx + 34, 6):
            self.rect(gx, 48, 1, 66, DKGREY)
        for gy in range(48, 114, 6):
            self.rect(cx - 34, gy, 68, 1, DKGREY)
        # Catcher: mask with grill, body, glove at the aim point.
        self.rect(cx - 8, 66, 16, 14, UNI_AWAY)     # mask shell
        self.rect(cx - 7, 68, 14, 10, SKIN)         # face
        for gx in (cx - 6, cx - 1, cx + 4):
            self.rect(gx, 68, 3, 10, BLACK)         # grill bars (3px)
        self.rect(cx - 14, 80, 28, 22, UNI_AWAY)    # crouched body
        self.rect(cx - 14, 80, 28, 3, DKGREY)       # chest protector top
        # Zone frame over the catcher (no black fill: catcher shows through).
        zc, zr = self._to_cell(cx - 12, 88)
        zw, zh = 12, 40 // self.dy
        self.solid_cells(zc, zr, zw, 1, ZONE)
        self.solid_cells(zc, zr + zh - 1, zw, 1, ZONE)
        self.solid_cells(zc, zr, 1, zh, ZONE)
        self.solid_cells(zc + zw - 1, zr, 1, zh, ZONE)
        aim = game.get("aim", [0.0, 0.0])
        gx = int(cx + aim[0] * 22)
        gy = int(108 - aim[1] * 18)
        self.rect(gx - 4, gy - 4, 8, 8, BROWN)      # glove target
        self.rect(gx - 2, gy - 2, 4, 4, BLACK)
        prog = game.get("ball_progress")
        if prog is not None:
            prog = max(0.0, min(1.0, prog))
            by = int(150 - prog * 42)               # release -> plate
            sz = 7 - int(prog * 4)                  # shrinks with distance
            self.rect(cx - sz // 2, by - sz // 2, sz, sz, BALL)
            if prog < 0.2:                          # release streak
                self.rect(cx - 1, by + 4, 2, 14, GREY)
        # Mound dirt foreground.
        self.rect(0, 150, GRID_W, 18, TERRA)
        self.rect(0, 150, GRID_W, 2, BROWN)

    def render_message(self, line1, line2=""):
        self.rect(20, 150, 120, 26, BLACK)
        self.text(line1, 26, 154, WHITE)
        if line2:
            self.text(line2, 26, 164, YELLOW)

    # -- ANSI emission ---------------------------------------------------
    def _cell(self, x0, y0, dx, dy):
        """Majority vote of the dx*dy block -> (fg, bg) palette indices."""
        top = [0] * 16
        bot = [0] * 16
        for yy in range(y0, min(y0 + dy, GRID_H)):
            row = self.fb[yy]
            acc = top if yy < y0 + dy // 2 else bot
            for xx in range(x0, min(x0 + dx, GRID_W)):
                acc[row[xx]] += 1
        fg = max(range(16), key=lambda i: (top[i], -i))
        bg = max(range(16), key=lambda i: (bot[i], -i))
        return fg, bg

    def _row_string(self, r):
        y0 = r * self.dy
        parts = []
        last_fg = last_bg = -1
        dim = (r % 2 == 1)  # alternate-row scanlines
        if dim:
            parts.append(ESC + "[2m")
        for c in range(self.cols):
            fg, bg = self._cell(c * 2, y0, 2, self.dy)
            ch = BLOCK
            ov = self.ov[r][c]
            if ov is not None:
                if ov[0] == "ch":
                    _, ch, fg, bg = ov
                else:
                    fg = bg = ov[1]
            if fg != last_fg or bg != last_bg:
                parts.append(ESC + "[%d;%dm" % (FG_CODE[fg], BG_CODE[bg]))
                last_fg, last_bg = fg, bg
            parts.append(ch)
        parts.append(ESC + "[0m")
        return "".join(parts)

    def to_string(self, full=True):
        """Render the whole frame to an ANSI string (headless-friendly)."""
        return "\n".join(self._row_string(r) for r in range(self.rows)) + "\n"

    def enter(self, stream=None):
        """Take over the terminal: alternate screen, hidden cursor."""
        import sys
        out = stream or sys.stdout
        out.write(ESC + "[?1049h" + ESC + "[?25l")
        out.flush()
        self._last = None

    def exit(self, stream=None):
        """Restore the terminal after enter()."""
        import sys
        out = stream or sys.stdout
        out.write(ESC + "[?25h" + ESC + "[?1049l")
        out.flush()

    def present(self, stream=None):
        """Double-buffered emit: only changed rows, with cursor addressing."""
        import sys
        out = stream or sys.stdout
        rows = [self._row_string(r) for r in range(self.rows)]
        if self._last is None:
            out.write(ESC + "[2J" + ESC + "[H")
            for i, line in enumerate(rows):
                out.write(ESC + "[%d;1H" % (i + 1) + line)
        else:
            for i, line in enumerate(rows):
                if line != self._last[i]:
                    out.write(ESC + "[%d;1H" % (i + 1) + line)
        out.flush()
        self._last = rows
