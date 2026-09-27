"""启动入口：python -m zhepub [文件.epub | 文件.txt]"""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """资源文件路径；打包成 exe 后资源解压在 sys._MEIPASS 下。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def main() -> int:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from .ui.main_window import APP_NAME, MainWindow

    if sys.platform == "win32":
        # 让任务栏显示本程序的图标，而不是 Python 的图标
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zhepub.editor")
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    icon = resource_path("assets/icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
