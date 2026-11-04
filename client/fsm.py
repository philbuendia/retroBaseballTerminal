"""Client tracking FSM: re-exported from the server so both ends of the
wire can never diverge. The client runs this locally to drive overlays
(calibration progress, dwell bar, stance gate) and gesture measurement;
the server runs its own copy as the authority for game flow.

API: TrackingFSM.update(landmarks, dt) -> Transition | None, force_pause().
Landmark input: {"points": [(x, y)] * 9, "conf": [float] * 9} in +y-up
coordinates (use SilhouetteCalibrator.norm first).
"""

from server.state_machine import (  # noqa: F401  (re-export)
    UNBOUND, CALIBRATE, MENU, STANCE, ACTION, RESOLVE, PAUSE,
    STATES, STATE_TIMEOUTS, ROLE_BAT, ROLE_PITCH,
    Transition, TrackingFSM,
)
