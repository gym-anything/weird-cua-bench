"""Evaluation support for the Weird CUA benchmark protocol."""

from .control import control_for_environment
from .remote import WeirdRemoteGymEnv

__all__ = ["WeirdRemoteGymEnv", "control_for_environment"]
