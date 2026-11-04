## 1. System Overview & Technical Target

**Project Working Title:** *Retro Diamond: Optical Arcade*
**Genre:** Touchless Arcade Sports Simulation
**Input Method:** Monocular RGB Webcam (Optical Pose Estimation)
**Visual Target:** 160x192 internal pixel grid upscaled to 1080p/4K with CRT scanline emulation and a 16-color high-contrast palette.
**Audio Target:** Dual-channel square-wave and white-noise synthesizer generating pitch whistles, bat cracks, crowd swells, and 8-bit organ jingles.

* **Minimum Camera Spec:** 720p resolution at 60 frames per second to prevent motion blur during high-velocity arm swings.
* **Skeletal Landmarks Tracked:** Nine upper-body keypoints comprising the nose, left/right shoulders, left/right elbows, left/right wrists, and left/right hips.
* **Play Space Footprint:** A clear floor area of 4 feet wide by 6 feet deep, positioned 4 to 7 feet from the computer display.

## 2. Camera Tracking State Machine

The optical tracking engine operates as a deterministic finite state machine, evaluating player landmark coordinates every 16.6 milliseconds to manage transitions without physical peripherals.

| State ID | Trigger Condition | Active Landmarks | Timeout Threshold | Next Valid State |
| --- | --- | --- | --- | --- |
| **01_UNBOUND** | No torso detected | All 9 keypoints | Infinite | 02_CALIBRATE |
| **02_CALIBRATE** | Torso inside frame | Shoulders, Hips | 2.0 seconds | 03_MENU_SELECT |
| **03_MENU_SELECT** | Calibration locked | Left/Right Wrists | 2.0 seconds dwell | 04_STANCE_READY |
| **04_STANCE_READY** | Role selected | Wrists, Shoulders | 10.0 seconds | 05_ACTION_WINDOW |
| **05_ACTION_WINDOW** | Load/Grip held | Wrists, Elbows | 3.5 seconds | 06_PLAY_RESOLVE |
| **06_PLAY_RESOLVE** | Swing/Throw peak | None (Physics lock) | 4.0 seconds | 04_STANCE_READY |
| **07_SYSTEM_PAUSE** | Wrists crossed on chest | Wrists, Shoulders | 1.5 seconds hold | 03_MENU_SELECT |

The system normalizes all movement vectors against the player's calibrated shoulder width ($W_s$), ensuring identical physics calculations regardless of player height or distance from the lens.

* **Occlusion Recovery:** If a wrist keypoint drops below 60 percent confidence during a rapid swing, the engine extrapolates up to 3 frames using the preceding velocity vector.
* **False-Input Rejection:** Movements slower than 1.5 shoulder-widths per second during `05_ACTION_WINDOW` are filtered out as idle posture shifts rather than swings or throws.
* **Emergency Pause Override:** Stepping completely out of the camera frustum for greater than 1.0 second automatically triggers `07_SYSTEM_PAUSE`.

## 3. Core Gameplay Kinematics & Input Mapping

### Batting Mechanics

To initiate a pitch, the batter enters `04_STANCE_READY` by holding both wrists within 0.5 shoulder-widths of their rear shoulder for 0.5 seconds. Once the AI pitcher releases the ball, the engine measures the batter's wrist trajectory across the torso midline.

* **Exit Velocity Calculation:** Hand speed across the torso midline ($V_h$) maps linearly from 2.0 to 8.0 shoulder-widths per second into an in-game exit velocity of 65 to 115 mph.
* **Horizontal Spray Angle:** Contact timing relative to the ball crossing the plate shifts the hit vector across a 90-degree fair territory cone, with early swings pulling the ball and late swings driving to the opposite field.
* **Launch Angle Mapping:** The vertical slope between the wrist start position and contact point sets the launch angle between negative 15 degrees (grounder) and positive 45 degrees (fly ball).
* **Check Swing Threshold:** Halting forward wrist movement before the hands cross the torso midline cancels the swing and allows the pitch to be called a ball or strike.

### Pitching Mechanics

In Pitcher Mode, the player aims with their non-throwing hand during `04_STANCE_READY`, locks a pitch grip via upper-body posture, and throws their pitching hand toward the camera during `05_ACTION_WINDOW`.

| Pitch Type | Pre-Throw Pose | Velocity Scale | Horizontal Break | Vertical Drop |
| --- | --- | --- | --- | --- |
| **Four-Seam Fastball** | Hands together at chest | 100% | 0 pixels | 2 pixels |
| **12-6 Curveball** | Both hands raised overhead | 75% | 2 pixels | 18 pixels |
| **Lateral Slider** | Elbows flared out wide | 85% | 16 pixels | 6 pixels |
| **Changeup** | Non-throwing hand on hip | 70% | 4 pixels | 10 pixels |

Pitch accuracy depends on the stability of the player's head and lead shoulder during the forward arm thrust. If the nose landmark shifts laterally by more than 0.3 shoulder-widths during release, an accuracy penalty scatters the pitch outside the locked target reticle.

## 4. Inning Structure & Pacing Rules

To prevent physical fatigue from repetitive webcam motion, the game condenses traditional baseball rules into an arcade loop with automated baserunning and fielding.

* **Match Length:** Standard games run 3 innings (9 outs per side), with an endurance option for 6 or 9 innings selectable via menu dwell.
* **Arcade Count Structure:** Batters begin every plate appearance with a 1-ball, 1-strike count to accelerate at-bats and maximize ball-in-play frequency.
* **Two-Foul Courtesy Rule:** The first foul ball with two strikes keeps the at-bat alive, while a second consecutive two-strike foul registers as an automatic strikeout.
* **Automated Baserunning:** Baserunners advance automatically based on hit classification, eliminating the need for running-in-place gestures.
* **Role-Swap Half Innings:** In single-player mode, the user bats during the bottom half of the inning and pitches to AI batters during the top half.
* **Mercy Rule:** Any lead equal to or greater than 10 runs at the conclusion of an inning immediately ends the game.

## 5. Hit Resolution & Scoring Ruleset

When a ball is put in play, 8-bit AI fielders move along fixed horizontal zones in the infield and outfield. If the ball clears a defensive sprite's collision box, the hit resolves according to its landing zone and velocity.

| Hit Outcome | Launch Angle Range | Exit Velocity Min | Base Advancement | Arcade Score Value |
| --- | --- | --- | --- | --- |
| **Ground Out / Fly Out** | Any (Fielder intercept) | Any | None (1 Out recorded) | 0 pts |
| **Clean Single** | Negative 5 to 15 deg | 70 mph | Batter to 1B, runners +1 | 100 pts |
| **Gap Double** | 12 to 24 deg | 88 mph | Batter to 2B, runners +2 | 250 pts |
| **Deep Triple** | 18 to 28 deg (Corners) | 98 mph | Batter to 3B, all score | 500 pts |
| **Home Run** | 25 to 38 deg | 102 mph | All runners score | 1,000 pts |

Alongside standard baseball run tracking, an arcade point system rewards technical execution across both modes.

* **Run Scored Bonus:** Each run crossing home plate adds 500 points to the player's cumulative arcade score.
* **Corner Paint Bonus (Pitching):** Striking out a batter on a pitch touching the outer 2-pixel border of the strike zone awards 300 bonus points.
* **Immeculate Inning Multiplier:** Retiring three consecutive batters on nine total pitches triggers a 2x score multiplier for the subsequent batting half-inning.
* **Billboard Smash Bonus (Batting):** Driving a home run into the flashing 8-bit outfield scoreboard graphic awards an instant 2,500-point jackpot and triggers a synthesized firework animation.
