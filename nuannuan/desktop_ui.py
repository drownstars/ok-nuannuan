"""Use the native Fluent workbench shell with readable window backgrounds."""
def apply_desktop_layout(app, window):
    from PySide6.QtGui import QColor
    from qfluentwidgets import qconfig, setThemeColor
    accent = QColor('#9b6d99')
    window._configured_theme_color = accent
    def sync_accent():
        if qconfig.get(qconfig.themeColor) != accent:
            setThemeColor(accent, save=False)
    sync_accent()
    if not getattr(window, '_nuannuan_palette_installed', False):
        qconfig.themeChangedFinished.connect(sync_accent)
        window._nuannuan_palette_installed = True
    window.setCustomBackgroundColor('#f7f5f9', '#1b1a20')
    if not window.ok_config.get('nuannuan_workbench_v1', False):
        window.navigationInterface.expand(False)
        window.ok_config['nuannuan_workbench_v1'] = True
    from nuannuan.run_dialog import attach_run_dialog
    return attach_run_dialog(app, window)
