"""Shared single-operation dispatch, settings navigation and status controls."""
import time

import psutil
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, InfoBar, PushButton
from ok import og

from nuannuan.tasks import OperationTask


def dispatch_operation(page, name, values=None):
    task = page.get_task(OperationTask)
    control = getattr(page.executor, '_nuannuan_run_control', None)
    if ((control is not None and control.busy) or page.executor.current_task is not None or task.enabled
            or time.monotonic() < getattr(task, '_dispatch_until', 0)):
        InfoBar.warning('已有任务在运行', '请先停止当前任务，再开始新的操作。', parent=page.window())
        return False
    if name!='进入游戏' and not any((p.info['name'] or '').lower() == 'x6game-win64-shipping.exe' for p in psutil.process_iter(['name'])):
        InfoBar.warning('请先连接游戏', '打开游戏后，在连接页面选择游戏窗口。', parent=page.window())
        return False
    values = {'工具功能': name, **(values or {})}
    options = {**dict(task.config), **values}
    for key, value in values.items():
        if key != '流程JSON': task.config[key] = value
    task._pending_options = options
    task._dispatch_until = time.monotonic()+1
    og.app.start_controller.start(task)
    return True


def open_extra_settings(page):
    window = page.window()
    window.setting_tab.goto_config('活跃能量用途')
    window.switchTo(window.setting_tab)
    target = next(card for card in window.setting_tab.config_groups if card.has_key('活跃能量用途'))
    QTimer.singleShot(300, lambda: window.setting_tab.verticalScrollBar().setValue(
        target.mapTo(window.setting_tab.view, QPoint(0, 0)).y()))


class OperationStatus(QWidget):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 12, 0, 0)
        self.label = BodyLabel('尚未开始操作。', self)
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)
        self.stop_button = PushButton('停止当前操作', self)
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        row.addWidget(self.stop_button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)

    def refresh(self):
        if self.page.executor is None: return
        task = self.page.get_task(OperationTask)
        control = getattr(self.page.executor, '_nuannuan_run_control', None)
        active = task.enabled or self.page.executor.current_task is task or (control is not None and control.task is task)
        self.stop_button.setEnabled(active)
        if task.info:
            state = task.info.get('运行状态', '执行中' if active else '已结束')
            title = task.info.get('当前操作', '')
            result = task.info.get('操作结果', '')
            self.label.setText(f'{state} · {title}' + (f'\n{result}' if result else ''))

    def stop(self):
        task = self.page.get_task(OperationTask)
        control = getattr(self.page.executor, '_nuannuan_run_control', None)
        if control is not None and control.task is task: control.stop()
        else: task.disable()
        self.label.setText('正在停止，等待释放游戏输入…')
