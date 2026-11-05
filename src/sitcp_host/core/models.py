"""Small transport-independent data models shared by core and GUI layers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    temperature_raw: int
    jesd_sync_state: int
    jesd_reset_state: int

