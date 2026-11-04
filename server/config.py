"""Shared constants for the Retro Diamond deterministic game server.

Single source of truth for every number in BUILD_CONTRACT.md / architecture.md.
All physics uses shoulder-width-normalized units (Ws); the fixture frame is
Ws = 1.0, origin at mid-shoulder, +x pull side, +y up, dt = 1/60.
"""

PROTOCOL_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_INNINGS = 3
MENU_INNINGS = (3, 6, 9)
STATE_HZ = 60.0

# --- Tracking FSM timeouts (seconds) ---
CALIBRATE_TIMEOUT_S = 2.0
MENU_DWELL_S = 2.0
STANCE_TIMEOUT_S = 10.0
ACTION_TIMEOUT_S = 3.5
RESOLVE_TIMEOUT_S = 4.0
PAUSE_HOLD_S = 1.5
OUT_OF_FRUSTUM_S = 1.0
STANCE_GATE_HOLD_S = 0.5
STANCE_GATE_DIST_WS = 0.5

# --- Tracking robustness ---
CONF_MIN = 0.6
EXTRAPOLATE_MAX_FRAMES = 3  # 4th consecutive missing frame = fail
IDLE_SPEED_WS = 1.5  # below this in ACTION_WINDOW = idle posture shift

# --- Batting kinematics ---
VH_MIN_WS = 2.0
VH_MAX_WS = 8.0
EXIT_MIN_MPH = 65.0
EXIT_MAX_MPH = 115.0
LAUNCH_MIN_DEG = -15.0
LAUNCH_MAX_DEG = 45.0
SPRAY_MAX_DEG = 45.0  # 90-degree fair cone
FAIR_DT_S = 0.25  # |dt| <= this -> fair contact
FOUL_DT_S = 0.40  # fair < |dt| <= this -> foul; beyond -> whiff

# --- Pitching ---
# (velocity scale, horizontal break px, vertical drop px) on the 160x192 grid.
PITCH_TABLE = {
    "FB": {"vel_scale": 1.00, "break_px": 0, "drop_px": 2},
    "CB": {"vel_scale": 0.75, "break_px": 2, "drop_px": 18},
    "SL": {"vel_scale": 0.85, "break_px": 16, "drop_px": 6},
    "CH": {"vel_scale": 0.70, "break_px": 4, "drop_px": 10},
}
BASE_PITCH_MPH = 62.0
ARM_PITCH_GAIN = 3.5  # mph per Ws/s of arm speed, before velocity scale
NOSE_SCATTER_WS = 0.3  # nose shift above this scatters the pitch
ZONE_HALF = 0.5  # strike zone is x,y in [-0.5, 0.5] (normalized units)
CORNER_BAND = 0.05  # outer band of zone ~= 2px on the internal grid

# --- Arcade count ---
COUNT_START_BALLS = 1
COUNT_START_STRIKES = 1
MAX_BALLS = 4
MAX_STRIKES = 3

# --- Hit windows: (launch_lo, launch_hi, exit_min_mph, points) ---
HIT_WINDOWS = {
    "HR": (25.0, 38.0, 102.0, 1000),
    "3B": (18.0, 28.0, 98.0, 500),  # corners only
    "2B": (12.0, 24.0, 88.0, 250),
    "1B": (-5.0, 15.0, 70.0, 100),
}
HIT_PRECEDENCE = ("HR", "3B", "2B", "1B", "OUT")
CORNER_SPRAY_DEG = 28.0  # |spray| >= this counts as "corners" for triples

# --- Arcade scoring ---
RUN_POINTS = 500
CORNER_PAINT_K_POINTS = 300
BILLBOARD_POINTS = 2500
IMMACULATE_MULT = 2
MERCY_RUNS = 10

# --- Keypoints: canonical order everywhere ---
KP_ORDER = ("nose", "Lsho", "Rsho", "Lelb", "Relb",
            "Lwri", "Rwri", "Lhip", "Rhip")
KP = {name: i for i, name in enumerate(KP_ORDER)}

# --- Internal pixel grid ---
GRID_W = 160
GRID_H = 192
