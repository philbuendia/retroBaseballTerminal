# BUILD CONTRACT (single source of truth for builder subagents)

Synthesized from planner subagents (workflow run, all 4 results complete) +
parent-verified environment ground truth. Implements `description.md` +
`architecture.md` for a game played **inside the terminal**.

## Locked environment facts (verified by parent, do not re-litigate)

- Python 3.14.6, project env `.venv/` (use `.venv/bin/python`).
  Installed: numpy 2.3.5, opencv-python-headless 5.0.0, openvino 2025.4.1,
  certifi, pytest. **No mediapipe / onnxruntime wheels exist for 3.14.**
- Pose backend (proven 2026-11-04, `POSE_SMOKE_OK` on real COCO photo):
  OpenVINO `models/human-pose-estimation-0001.{xml,bin}` (18 heatmaps).
  9 required keypoints = heatmap idx nose 0, Lsho 5, Rsho 2, Lelb 6, Relb 3,
  Lwri 7, Rwri 4, Lhip 11, Rhip 8. First-run latency 63ms CPU.
- Camera: FaceTime HD present, but macOS TCC denies capture to background
  processes. Client MUST support `--replay <video/img>` and keypress-sample
  mode; live camera works when the human runs the client in their own terminal.
- Audio playback: `/usr/bin/afplay` present (verify at runtime, keep
  `--no-audio` silent fallback).
- `random` module is FORBIDDEN in server/ and evals/ (determinism; grep-checked).

## Locked spec interpretations

- "9 outs per side" for 3 innings = typo; use 9 total outs per side (3/inning).
- Hit precedence on angle overlap: HR > 3B > 2B > 1B > OUT; fielder intercept
  always OUT. Below-min velocity downgrades exactly one class.
- Terminal: default 80x48 downscale mode; 80x96 full mode when term is tall
  enough. Never require more than 80 columns.
- Keypoint order everywhere: `[nose, Lsho, Rsho, Lelb, Relb, Lwri, Rwri,
  Lhip, Rhip]` + `conf[9]`. Fixture frame: Ws=1.0 units, origin mid-shoulder,
  +x pull side, +y up, dt=1/60.

## Module layout (exact filenames)

- server/: `__init__ __main__ config state_machine kinematics pitching
  hitting game scoring protocol net ai` (.py each). Stdlib-only.
- client/: `requirements.txt capture pose calibration fsm gestures render
  audio net protocol main` (.py each).
- tests/: `conftest test_state_machine test_batting test_pitching test_innings
  test_hitscoring test_terminal_client test_integration` (.py each).
- evals/: `run_evals.py`, `scenarios/{state_machine,batting,pitching,innings,
  hitscoring,terminal_client,integration}.py`, `fixtures/landmarks.py`.

## Wire protocol (TCP localhost:8765, newline-delimited JSON, `v:1`)

- C→S: `hello{v}` `select{role,innings}` `stance{held_s}`
  `swing{vh_ws,dt_s,slope,crossed}` `aim{x,y}`
  `throw{pitch,arm_ws,nose_shift_ws}` `pause` `resume`
- S→C: `state{fsm,...}`@60Hz `pitch_result{call,count}` `hit_result{outcome,
  launch,exit,runs,arcade_delta}` `score{runs,arcade,inning,half}`
  `game_over{reason,...}`
- All `t`-tagged dicts; unknown `t` → `error{msg}` reply, never a crash.

## Key APIs (signatures builders must keep)

- `TrackingFSM.update(landmarks, dt) -> Transition | None`, `force_pause()`
- `exit_velocity_mph(vh)`, `spray_angle_deg(dt)`, `launch_angle_deg(y0,y1,Ws)`,
  `crossed_midline(path, mid)`, `stance_gate_ok(wrists, sh, held)`
- `resolve_pitch(spec, arm, target, nose, seq)`, `resolve_contact(pitch, swing)`,
  `resolve_hit(launch, exit, intercept, corner, billboard)`
- `GameState`: `apply_pitch_call/apply_foul/apply_hit/swap_half/check_mercy`,
  `Count(balls, strikes, consec_two_strike_fouls)`
- `award_hit/run/corner_paint_k/billboard`, `immaculate_multiplier(active)`
- `Camera.open/read_frame/fps`, `PoseEstimator.extract(frame)`,
  `SilhouetteCalibrator.update/Ws/norm`, `TerminalRenderer.blit/render_*`,
  `ChipSynth.square/noise/whistle/crack/swell/jingle` (return int16 buffers),
  `GameClient.connect/send_event/poll_frame`

## Numbers that must match architecture.md exactly

- Timeouts: CAL 2.0 / MENU 2.0 dwell / STANCE 10.0 / ACTION 3.5 / RESOLVE 4.0 /
  PAUSE-hold 1.5 / out-of-frustum 1.0 / stance-gate 0.5s @ 0.5Ws.
- Occlusion: conf<0.6 → extrapolate ≤3 frames; 4th consecutive missing = fail.
- Idle reject: <1.5 Ws/s in ACTION_WINDOW.
- Exit velo: 65 + (Vh−2.0)/6.0*50, Vh∈[2.0,8.0] → 65..115 mph.
- Launch ∈ [−15,+45] deg; spray ±45 deg (90° cone).
- Pitches: FB(1.00,0,2) CB(0.75,2,18) SL(0.85,16,6) CH(0.70,4,10);
  nose-shift >0.3Ws scatters.
- Count starts 1-1; foul#1@2K alive, foul#2 consecutive@2K = K.
- Hits: 1B(−5..15°,≥70,100pts) 2B(12..24°,≥88,250) 3B(18..28°corner,≥98,500)
  HR(25..38°,≥102,1000); run +500; corner-paint K +300; immaculate 2x next
  batting half; billboard HR +2500 + firework flag.
- Innings 3/6/9 menu; role-swap halves (top=pitch vs AI, bottom=bat);
  mercy ≥10 after completed inning.

## Eval weights (pass ≥90)

state_machine 20 / batting 20 / pitching 15 / innings 15 / hitscoring 15 /
terminal_client 10 / integration 5. `evals/run_evals.py --json out.json
--threshold 90` exits 0 iff ≥90.

## Build order

M1 server → M2 client → M3 fixtures+tests+evals → M4 integration.
Each builder: read this contract + description.md + architecture.md, write ONLY
its own directories, run its own checks, report files + how to run + gaps.

## Field updates (parent-verified on real footage)

- `batter.mov` (20 s, 3360x1904@57.6fps, front chest-up view) is the
  required camera-view fixture at repo root; tests + evals stream it.
- Calibration: 2.0 s median Ws; torso gate = shoulders ≥0.35 AND
  (hips ≥0.35 OR nose ≥0.35); hips-absent locks flag `close_range=True`.
  Ws samples outside 0.7–1.4x of the running median are skipped.
- Swing/throw trackers: EMA-smoothed (alpha 0.4) wrist midpoint (swing)
  or throwing wrist (throw); samples with wrist conf <0.3 are dropouts
  that hold position and stretch the velocity window (gap-aware dt).
- Measured on batter.mov: lock at ~2 s, Ws≈1179px close-range, 3 real
  swings tracked (peaks ~8–14 Ws/s, server clamps ≥8 to 115mph).
