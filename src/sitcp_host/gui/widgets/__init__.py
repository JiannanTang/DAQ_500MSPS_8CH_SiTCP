"""Reusable widgets for the SiTCP desktop interface."""

from sitcp_host.gui.widgets.connection import ConnectionBar
from sitcp_host.gui.widgets.data import DataPanel
from sitcp_host.gui.widgets.raw_access import RawAccessPanel
from sitcp_host.gui.widgets.registers import RegisterPanel
from sitcp_host.gui.widgets.status import StatusPanel

__all__ = [
    "ConnectionBar",
    "DataPanel",
    "RawAccessPanel",
    "RegisterPanel",
    "StatusPanel",
]

