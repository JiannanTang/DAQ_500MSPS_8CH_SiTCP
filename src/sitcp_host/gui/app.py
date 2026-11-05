"""Application entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from sitcp_host.config import default_config_path
from sitcp_host.core.registers import load_profile
from sitcp_host.errors import SitcpError
from sitcp_host.gui.i18n import set_language, tx
from sitcp_host.gui.main_window import MainWindow
from sitcp_host.gui.theme import APP_STYLE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SiTCP desktop application")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args(argv)

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("DAQ_500MSPS_8CH_SiTCP")
    app.setOrganizationName("SiTCP")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    saved_language = str(QSettings("SiTCP", "Host").value("language", "zh"))
    set_language(saved_language if saved_language in {"zh", "en"} else "zh")

    try:
        profile = load_profile(args.config)
    except (OSError, SitcpError, ValueError) as exc:
        QMessageBox.critical(None, tx("配置加载失败"), str(exc))
        return 2

    window = MainWindow(profile)
    if args.smoke_test:
        app.processEvents()
        window.close()
        app.processEvents()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

