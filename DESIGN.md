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
- **Interfaces (planned):** browser client captures pose landmarks and sends
  them over WebSocket (`127.0.0.1:8765`) to a deterministic server that owns
  the state machine, physics, and rules. No randomness in outcomes.

## 2. Build process design

- **Milestones:** M0 plan+scaffold → M1 server prototype → M2 client prototype
  → M3 evals+tests (≥90/100) → M4 integration+final.
- **Agent routing** (per `agentAssignment.md`): fast inline triage for atomic
  tasks; spawned subagents for multi-step work (≥3 steps, multi-tool chains,
  cross-role synthesis); triage layer commits and formats results.
- **Build sizing:** brief totaled 1564 words → Standard build (no art
  director, one critic round).

## 3. Test process design

- **Eval rubric (100 pts, planned):** state machine 20, batting 20, pitching
  15, inning pacing 15, hit resolution/scoring 15, client render/audio/input
  10, integration 5. Pass bar ≥90.
- **Test-data policy:** real spec-derived vectors only — no random or fake
  data; server math must be deterministic (no random outcomes).

## 4. Decision log

| Date (UTC) | Decision | Rationale | Status |
|---|---|---|---|
| 2026-11-04 | Shoulder-width-normalized kinematics (Ws) | Same physics for any body size / camera distance | Spec'd, unbuilt |
| 2026-11-04 | Condensed arcade rules (3 inn, 1-1 counts, auto-run) | Prevent physical fatigue from full-motion play | Spec'd, unbuilt |
| 2026-11-04 | Deterministic server, no random outcomes | Makes evals reproducible; honest scoring | Spec'd, unbuilt |
| 2026-11-04 | Standard build size (1564-word brief) | Under 2000-word threshold: no art director, 1 critic round | Decided |
| 2026-11-04 | Server ports 127.0.0.1:8765, evals local-only | Avoid conflicts; no network exposure needed | Proposed |
| 2026-11-04 | MediaPipe Pose via CDN for 9 landmarks | Fastest path to 60fps upper-body tracking | Proposed, needs approval (offline alternative: vendored model) |
| 2026-11-04 | Headless fallback: recorded landmark trace for playtest | If no 720p60 webcam on test machine, still verify M2 honestly | Proposed, needs approval |

## 5. Open questions

1. Is a 720p60 webcam available on the playtest machine?
2. Is CDN access allowed, or must the pose model be vendored (offline-only)?
3. Are there port conflicts with `127.0.0.1:8765`?

---
*Last doc update: 2026-11-04 (M0 in progress, score 0/100, target ≥90). Next
update on the 2-hour doc cadence or when a milestone lands.*
