# Design & Decisions

Living design summary and decision log for Retro Diamond: Optical Arcade.
Updated by the documentation cron (every 2h) as the build and test process
progresses.

## 1. System design (from `architecture.md`)

- **Tracking engine:** deterministic finite state machine, 7 states
  (`01_UNBOUND` → `02_CALIBRATE` → `03_MENU_SELECT` → `04_STANCE_READY` →
  `05_ACTION_WINDOW` → `06_PLAY_RESOLVE`, plus `07_SYSTEM_PAUSE`), evaluated
  every 16.6 ms. All motion vectors normalized against calibrated shoulder
  width (Ws), so physics is identical regardless of player height or
  camera distance.
- **Robustness:** occlusion recovery (≤3-frame velocity extrapolation below
  60% wrist confidence), false-input rejection (<1.5 Ws/s filtered as idle),
  emergency pause after >1.0 s out of frustum.
- **Batting:** exit velocity 65–115 mph from hand speed (2–8 Ws/s); spray
  angle from contact timing across a 90° cone; launch angle −15°…+45° from
  wrist-path slope; check swing if hands stop before the torso midline.
- **Pitching:** 4 pitch types keyed to pre-throw poses (fastball / curve /
  slider / changeup) with distinct velocity/break/drop; head/shoulder
  stability at release drives accuracy (nose shift >0.3 Ws scatters).
- **Pacing:** 3-inning standard (6/9 optional), 1-1 counts, two-foul courtesy
  rule (2nd consecutive two-strike foul = K), auto baserunning, role-swap
  half-innings, 10-run mercy rule.
- **Scoring:** hit outcomes from launch angle + exit velocity vs. fixed-zone
  AI fielders (single 100 → homer 1,000), plus run bonus (500), corner-paint
  K bonus (300), immaculate-inning 2x multiplier, billboard-smash jackpot
  (2,500).
- **Presentation:** 160x192 internal grid → 1080p/4K upscale, 16-color
  palette, CRT scanlines; dual-channel square-wave + noise synth.
- **Interfaces (built):** Python terminal client captures pose landmarks and
  sends events over newline-delimited JSON TCP (`127.0.0.1:8765`, `v:1`) to a
  deterministic stdlib-only server that owns the state machine, physics, and
  rules. No randomness in outcomes (`random` forbidden in server/evals,
  grep-verified).
- **Presentation (built):** ANSI renderer, 80 columns, auto-fits 24/48/96-row
  windows; first-person views (batter sees pitcher + incoming ball, pitcher
  sees catcher + zone); crisp cell-text overlay after screenshot review showed
  downsampled text was illegible; chip-synth audio via `afplay` with silent
  fallback.
- **Detection tuning on real footage (built ~07:15):** the user's 20 s front
  chest-up `batter.mov` (3360x1904@57.6fps) exposed two failures — calibration
  never locked (hips out of frame) and every 50+ Ws/s velocity spike rode on
  ~0.00 wrist confidence. Fixes: close-range calibration fallback (lock on
  shoulders ≥0.35 + (hips ≥0.35 OR nose ≥0.35), sets `close_range` flag when
  hips absent; 2.0 s median Ws with 0.7–1.4x outlier rejection), EMA-smoothed
  (alpha 0.4) wrist-midpoint swing tracker + smoothed throwing-wrist tracker,
  wrist-conf <0.3 treated as dropouts that hold position and stretch the
  velocity window (gap-aware dt). Measured: lock at ~2 s (Ws≈1179px),
  3 real swings tracked (peaks 8–14 Ws/s; server clamps ≥8 to 115 mph).
- **Camera-path stance handshake (built ~07:30, "pitcher never throws" fix):**
  client sends `stance` on the STANCE→ACTION edge so the server deals the AI
  pitch; server re-arms from MENU on `stance` without resetting the game.
  Live-wire proof: stance→ACTION→hit_result+score, timeout→rearm.

## 2. Build process design

- **Milestones (all DONE 2026-11-04):** M0 plan+scaffold+contract (~04:25) →
  M1 server (~04:45, `M1_PROBE_OK` + `FOUL_RULE_OK`) → M2 client (~05:00,
  `M2_PROBE_OK`: 9/9 keypoints on real photo, conf 0.67–0.88) → M3 evals+tests
  (~05:10, 100/100) → M4 integration (~05:20, live replay exit 0). Follow-ups:
  visual overhaul after human 10/100 look score (~05:40), first-person views +
  80×24 auto-fit (~06:10). Post-M4 hardening on real footage: detection tuning
  on `batter.mov` (~07:15, 97 pytest), "pitcher never throws" handshake fix
  (~07:30, 100 pytest).
- **Agent routing** (per `agentAssignment.md`): fast inline triage for atomic
  tasks; spawned subagents for multi-step work (≥3 steps, multi-tool chains,
  cross-role synthesis); triage layer commits and formats results. M0 used
  planner subagents (server/client/evals + synthesis) → `BUILD_CONTRACT.md`
  as the single source of truth; builders wrote only their own directories.
- **Build sizing:** brief totaled 1564 words → Standard build (no art
  director, one critic round).

## 3. Test process design and results

- **Eval rubric (100 pts, built):** state machine 20, batting 20, pitching
  15, inning pacing 15, hit resolution/scoring 15, terminal client 10,
  integration 5. Pass bar ≥90. `evals/run_evals.py --json out.json
  --threshold 90` exits 0 iff ≥90.
- **Test-data policy:** real spec-derived vectors only — no random or fake
  data; server math deterministic (no random outcomes, grep-verified).
- **Score trajectory:** first run 82 (test-side frame-count errors) → 98
  (one real server bug: billboard NameError) → **100/100** after also fixing
  a foul-reset gap. Pytest grew 92 → 95 → 97 (batter.mov tests) → 100
  (handshake tests) alongside; gates now take ~60–90 s (video streaming).
- **Real-footage fixtures:** `batter.mov` (167 MB, repo root, local-only —
  NOT pushed: exceeds GitHub's 100 MB limit and is personal footage) is
  streamed by `test_batter_mov_*` + `terminal_client` eval. Newer pose models
  0005/0007 + CLAHE tested worse than 0001 on it, so 0001 stays; 0005/0007
  binaries are committed under `models/` for reference.
- **Screenshot evals:** after the human scored the old look 10/100, evals
  capture 9 real screenshots per run (parsed ANSI → PNG, byte-exact terminal
  output) and assert legibility + pixel stats. Shots committed under
  `asd-ste100/shots/`.
- **Known gaps:** pose inference ~63 ms/frame CPU (~16 fps vs 60 fps spec;
  capture stays 60 Hz, pose extrapolates); `client/gestures.py` SwingTracker
  can spike vh on synthetic wrist-switch paths (feel only — server
  kinematics carry graded batting weight); live camera + audio still need a
  human run (macOS TCC blocks background capture, so agents verified via
  `--replay`).

## 4. Decision log

| Date (UTC) | Decision | Rationale | Status |
|---|---|---|---|
| 2026-11-04 | Shoulder-width-normalized kinematics (Ws) | Same physics for any body size / camera distance | Spec'd, unbuilt |
| 2026-11-04 | Condensed arcade rules (3 inn, 1-1 counts, auto-run) | Prevent physical fatigue from full-motion play | Spec'd, unbuilt |
| 2026-11-04 | Deterministic server, no random outcomes | Makes evals reproducible; honest scoring | Spec'd, unbuilt |
| 2026-11-04 | Standard build size (1564-word brief) | Under 2000-word threshold: no art director, 1 critic round | Decided |
| 2026-11-04 | Server ports 127.0.0.1:8765, evals local-only | Avoid conflicts; no network exposure needed | Built |
| 2026-11-04 | OpenVINO human-pose-estimation-0001 (local) INSTEAD of MediaPipe CDN | No MediaPipe/onnxruntime wheels exist for Python 3.14 (verified); fully offline | Built, smoke-tested on real photo |
| 2026-11-04 | Terminal client (ANSI) instead of browser client | Spec's webcam+terminal play; Python keeps pose+render+audio in one stack | Built |
| 2026-11-04 | Client `--replay` + keypress-sample modes | macOS TCC denies camera to background processes; live cam works in human's terminal | Built, M4 verified via replay |
| 2026-11-04 | "9 outs per side" for 3 innings read as typo → 9 total per side (3/inning) | Only self-consistent reading of the spec | Locked in contract |
| 2026-11-04 | Hit precedence HR > 3B > 2B > 1B > OUT; below-min velocity downgrades one class | Spec angle ranges overlap; needed a deterministic rule | Locked in contract |
| 2026-11-04 | First-person views + cell-text overlay + 80×24 auto-fit | Human scored old broadcast look 10/100; small text illegible after downsampling | Built, screenshot-eval'd |
| 2026-11-04 | Evals capture 9 screenshots/run and assert legibility | Byte-exact renders prevent visual regressions agents can't otherwise see | Built |
| 2026-11-04 | Close-range calibration (nose fallback, 0.35 gate, median-guarded Ws) | Real chest-up footage has no hips; shoulder peaks ~0.4 in dim light | Built, verified on batter.mov |
| 2026-11-04 | EMA-smoothed midpoint/dropout-gated trackers | Lead-wrist switching spiked vh; all 50+ Ws/s spikes rode on ~0 conf | Built, 3 real swings tracked |
| 2026-11-04 | Keep pose model 0001; 0005/0007 + CLAHE rejected | Tested worse on batter.mov; 0001 kept as active backend | Built, 0005/0007 kept as reference |
| 2026-11-04 | Edge-triggered stance + server re-arm from MENU | Camera path never told server batter was loaded → no AI pitch ever | Built, live-wire proven |
| 2026-11-04 | `batter.mov` stays local-only, excluded from push | 167 MB > GitHub 100 MB limit; personal footage on public repo | Decided (doc run) |

## 5. Open questions

1. ~~Webcam on playtest machine?~~ Answered: FaceTime HD present; agents use
   `--replay`, human runs live camera in their own terminal (awaiting run).
2. ~~CDN vs vendored pose model?~~ Answered: local OpenVINO model, no CDN.
3. ~~Port conflicts on 127.0.0.1:8765?~~ No conflict reported; in use.
4. Human re-score of first-person visuals (phone photo if still bad)?
5. Does ~16 fps pose (vs 60 fps spec) matter? Options: smaller model or
   Apple-silicon GPU delegate.
6. NEW: viewpoint — spec says batters stand *sideways*, but batter.mov is a
   *front* chest-up view and detection now follows the footage. Record 20 s
   sideways if spec-sideways is wanted.
7. NEW: `batter.mov` distribution — keep local-only, or set up Git LFS so
   fresh clones get the required fixture? (Also a privacy call: it's personal
   footage on a public repo.)

---
*Last doc update: 2026-11-04 ~07:45 UTC (M0–M4 + real-footage hardening done,
evals 100/100, pytest 100 green — verified this run). Next update on the
2-hour doc cadence or when the human live-run lands.*
