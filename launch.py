"""Desktop launcher and shared path setup for local checks."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def prepare(*, silent=False):
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    (ROOT / 'logs').mkdir(exist_ok=True)
    (ROOT / '.cache/tmp').mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = str(ROOT / '.cache/tmp')
    os.environ['TMP'] = str(ROOT / '.cache/tmp')
    if silent:
        if sys.stdout is None:
            sys.stdout = (ROOT / 'logs/startup.log').open('a', encoding='utf-8', buffering=1)
        if sys.stderr is None:
            sys.stderr = sys.stdout


def build_app():
    from nuannuan.local_app import LocalApp
    from nuannuan.config import make_config
    from nuannuan.extra_daily import migrate_extra_file
    from nuannuan.run_control import migrate_runtime_file

    if not (ROOT / 'assets/manifest.json').is_file():
        raise RuntimeError('识别素材尚未导入，请先运行 bootstrap.ps1')
    migrate_extra_file(ROOT/'configs/扩展功能设置.json')
    migrate_runtime_file(ROOT/'configs/devices.json')
    if not (ROOT / 'configs/ui_config.json').exists():
        from ok.ui.qt.common.config import cfg, Language
        cfg.set(cfg.language, Language.CHINESE_SIMPLIFIED)
        cfg.set(cfg.micaEnabled, False)
    return LocalApp(make_config())


def main():
    prepare(silent=True)
    app = None
    try:
        app = build_app()
        from PySide6.QtCore import QTimer
        from nuannuan.home import HomeTab

        def open_home():
            window = app.app.main_window
            if window is not None:
                home = window.findChild(HomeTab)
                if home is not None:
                    window.switchTo(home)
                from nuannuan.desktop_ui import apply_desktop_layout
                apply_desktop_layout(app, window)
                app.run_control.install_hotkey()
                app.app.app.aboutToQuit.connect(app.run_control.close)
                import json
                (ROOT / 'logs/gui-start.json').write_text(json.dumps({
                    'pid': os.getpid(), 'executable': sys.executable,
                    'window_visible': window.isVisible(), 'title': window.windowTitle(),
                    'control_interface_removed': True,
                }, ensure_ascii=False, indent=2), encoding='utf-8')
        QTimer.singleShot(0, open_home)
        app.start()
    except Exception:
        import traceback
        traceback.print_exc()
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, '启动失败，详情见 logs\\startup.log。\n首次使用请先运行 bootstrap.ps1。',
                                        '暖暖小助手', 0x10)
        raise
    finally:
        if app is not None:
            app.quit()
