# Retro Diamond: Optical Arcade

A touchless arcade baseball game. A standard webcam is the only controller —
no keyboard, mouse, or gamepad. Step in front of the camera, swing your arms
to bat, throw toward the lens to pitch.

## What it is

- **Genre:** touchless arcade sports sim, late-1970s home-console aesthetic
  (chunky 8-bit sprites, 160x192 internal grid upscaled with CRT scanlines,
  square-wave synth audio).
- **Input:** monocular RGB webcam at 720p60. Optical pose estimation tracks
  9 upper-body landmarks (nose, shoulders, elbows, wrists, hips) every frame.
- **Modes:** Batter mode (stance, swing timing/power, launch angle, check
  swings) and Pitcher mode (reticle aim, pose-selected pitch type, arm-speed
  velocity, follow-through break).
- **Rules:** condensed arcade baseball — 3-inning games, 1-1 starting counts,
  automated baserunning/fielding, role-swap half-innings, 10-run mercy rule,
  plus an arcade points layer (100–2,500 pt bonuses, multipliers).

## Repo layout

| Path | Contents |
|---|---|
| `description.md` | Original game concept brief |
| `architecture.md` | Technical spec: state machine, kinematics, rules, scoring |
| `agentAssignment.md` | Agent model-routing plan used during the build |
| `DESIGN.md` | Design summary and build/test decision log |
| `client/` | Browser client (pose capture, canvas render, synth audio) — planned |
| `server/` | Game server (state machine, physics, rules) — planned |
| `evals/` | 100-pt spec rubric and scoring harness — planned |
| `tests/` | Unit/integration tests — planned |
| `asd-ste100/` | Machine-generated progress report (`index.html`) |

## Status

Early build (M0: planning + scaffold). Spec docs exist; `client/`, `server/`,
`evals/`, `tests/` are scaffolded but empty. See
[asd-ste100/index.html](asd-ste100/index.html) for the live progress report
and [DESIGN.md](DESIGN.md) for decisions so far.

## Planned quickstart

```bash
# server (game logic + WebSocket on 127.0.0.1:8765)
python -m server.app

# client (open in a browser with webcam access)
open client/index.html
```

Not runnable yet — this section becomes real at M2.

## Requirements (target)

- Webcam: 720p @ 60fps (prevents motion blur on fast swings)
- Play space: 4 ft wide x 6 ft deep, 4–7 ft from the display
- Browser with camera access + CDN access (MediaPipe Pose, pending approval)
