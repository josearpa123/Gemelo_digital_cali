"""Traffic light strategies. Each controller drives every tls of the running simulation."""

from sim.controllers.base import Controller
from sim.controllers.fixed import FixedTimeController

__all__ = ["Controller", "FixedTimeController"]
