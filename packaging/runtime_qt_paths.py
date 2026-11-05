"""Register and preload bundled Qt runtime DLLs before PySide6 is imported."""

import ctypes
import os
import sys


if sys.platform == "win32":
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        for relative_path in ("PySide6", "shiboken6"):
            runtime_dir = os.path.join(bundle_root, relative_path)
            if os.path.isdir(runtime_dir):
                os.add_dll_directory(runtime_dir)
                os.environ["PATH"] = runtime_dir + os.pathsep + os.environ.get(
                    "PATH",
                    "",
                )

        preload_files = (
            os.path.join(bundle_root, "MSVCP140.dll"),
            os.path.join(bundle_root, "MSVCP140_1.dll"),
            os.path.join(bundle_root, "MSVCP140_2.dll"),
            os.path.join(bundle_root, "VCRUNTIME140.dll"),
            os.path.join(bundle_root, "VCRUNTIME140_1.dll"),
            os.path.join(bundle_root, "shiboken6", "shiboken6.abi3.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Core.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Gui.dll"),
            os.path.join(bundle_root, "PySide6", "Qt6Widgets.dll"),
        )
        try:
            for path in preload_files:
                if os.path.isfile(path):
                    ctypes.WinDLL(path)
        except OSError as exc:
            log_path = os.path.join(
                os.path.dirname(sys.executable),
                "startup-error.log",
            )
            try:
                with open(log_path, "w", encoding="utf-8") as stream:
                    stream.write(f"{path}\n{exc}\n")
            except OSError:
                pass

