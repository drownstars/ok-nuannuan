"""Non-modal task log window; foreground game input continues while it is open."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QTextBrowser, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, PushButton, SubtitleLabel, isDarkTheme, qconfig


class RunDialog(QDialog):
    def __init__(self, control, parent=None):
        super().__init__(parent, Qt.Tool)
        self.setObjectName('nuannuanRunDialog')
        self.control = control
        self.setWindowTitle('任务运行')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(460, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.title_label = SubtitleLabel('当前任务', self)
        self.state_label = CaptionLabel('待机', self)
        self.current_label = BodyLabel('', self)
        self.current_label.setWordWrap(True)
        self.log = QTextBrowser(self)
        self.log.setObjectName('runDetails')
        self.log.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.current_label)
        layout.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.pause_button = PushButton('暂停', self)
        self.pause_button.clicked.connect(control.pause_or_resume)
        self.stop_button = PushButton('停止', self)
        self.stop_button.setToolTip('停止任务（/）')
        self.stop_button.clicked.connect(control.stop)
        self.hide_button = PushButton('收起', self)
        self.hide_button.clicked.connect(self.hide)
        for button in [self.pause_button, self.stop_button, self.hide_button]: row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(CaptionLabel('/ 停止    ·    F9 暂停或继续', self))
        self.apply_palette()
        qconfig.themeChangedFinished.connect(self.apply_palette)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)
        self._rendered = None

    def apply_palette(self):
        dark = isDarkTheme()
        background, card, ink = ('#222027', '#29262f', '#e7e0eb') if dark else ('#f7f5f9', '#ffffff', '#35303d')
        self.setStyleSheet(
            f'QDialog#nuannuanRunDialog {{background: {background};}}'
            f'QTextBrowser#runDetails {{background: {card}; color: {ink}; border: none; border-radius: 10px; padding: 10px;}}'
        )

    def refresh(self):
        self.control.reconcile()
        task = self.control.task or self.control.last_task
        if task is None: return
        self.title_label.setText(task.name)
        paused = self.control.app.task_executor.paused or task.paused
        self.state_label.setText('已暂停' if self.control.busy and paused else self.control.state)
        self.current_label.setText('当前步骤：'+str(task.info.get('当前步骤', task.info.get('启动状态', task.name))))
        markers = {'running': '→', 'succeeded': '✓', 'failed': '×', 'partial': '△', 'skipped': '·'}
        rows = [f'{markers.get(state, "·")} {label}'+(f'：{message}' if message else '')
                for label, state, message in list(self.control.events)]
        rows += [f'{key}：{value}' for key, value in list(task.info.items())[-10:]]
        text = '\n'.join(rows)
        if text != self._rendered:
            self.log.setPlainText(text)
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
            self._rendered = text
        self.stop_button.setEnabled(self.control.busy and not self.control.cancel_event.is_set())
        self.pause_button.setEnabled(self.control.busy and self.control.state == '执行中')
        self.pause_button.setText('继续' if paused else '暂停')

    def present(self):
        self.refresh()
        if not self.isVisible(): self.show()


def attach_run_dialog(app, window):
    if getattr(app, 'run_dialog', None) is not None: return app.run_dialog
    dialog = app.run_dialog = RunDialog(app.run_control, window)
    app.run_control.show_requested.connect(dialog.present)
    return dialog
