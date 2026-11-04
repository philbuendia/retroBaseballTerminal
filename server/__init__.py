"""Retro Diamond deterministic game server (stdlib only)."""

from .config import PROTOCOL_VERSION, DEFAULT_PORT, DEFAULT_INNINGS
from .state_machine import TrackingFSM, Transition, STATES
from .game import GameState, Count
from .ai import ScriptedAI

__version__ = "0.1.0"
__all__ = ["PROTOCOL_VERSION", "DEFAULT_PORT", "DEFAULT_INNINGS",
           "TrackingFSM", "Transition", "STATES",
           "GameState", "Count", "ScriptedAI"]
