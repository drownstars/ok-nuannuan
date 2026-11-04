import json

import psutil
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QTextBrowser, QWidget
from qfluentwidgets import (Action, BodyLabel, CaptionLabel, CardWidget, DropDownToolButton,
                            FluentIcon, IconWidget, PrimaryPushButton, PushButton, RoundMenu,
                            SubtitleLabel, TitleLabel, TransparentPushButton, TransparentToolButton,
                            isDarkTheme, qconfig)

from ok import og
from ok.ui.qt.widget.CustomTab import CustomTab

from nuannuan.config import ROOT
from nuannuan.tasks.daily_tasks import DailyTask

EMPTY_MESSAGE = '尚无运行记录。'


class HomeTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.game_running = False
        self._report_mtime = None
        self._rendered_text = None

        self.vBoxLayout.setContentsMargins(24, 24, 24, 24)
        self.vBoxLayout.setSpacing(18)
        self.view.setObjectName('homeView')
        header = QHBoxLayout()
        header.addWidget(TitleLabel('总览', self), 1)
        self.status_label = CaptionLabel('检查游戏状态…', self)
        self.status_label.setObjectName('homeConnection')
        header.addWidget(self.status_label)
        self.more_button = DropDownToolButton(FluentIcon.MORE, self)
        self.more_button.setToolTip('运行日志与使用说明')
        self.more_button.setAccessibleName('更多选项')
        self.more_menu = RoundMenu(parent=self.more_button)
        self.more_actions = []
        for icon, label, path in [(FluentIcon.FOLDER, '运行日志', ROOT / 'logs'),
                                  (FluentIcon.HELP, '使用说明', ROOT / 'README.md')]:
            action = Action(icon, label, self.more_menu)
            action.triggered.connect(lambda checked=False, target=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))))
            self.more_menu.addAction(action)
            self.more_actions.append(action)
        self.more_button.setMenu(self.more_menu)
        header.addWidget(self.more_button)
        self.addLayout(header)

        self.plan_card = CardWidget(self)
        self.plan_card.setBorderRadius(14)
        plan_layout = QVBoxLayout(self.plan_card)
        plan_layout.setContentsMargins(22, 20, 22, 20)
        plan_layout.setSpacing(12)
        plan_header = QHBoxLayout()
        icon = IconWidget(FluentIcon.CALENDAR, self.plan_card)
        icon.setFixedSize(22, 22)
        plan_header.addWidget(icon)
        plan_header.addWidget(SubtitleLabel('每日任务', self.plan_card))
        self.mode_label = CaptionLabel('自动执行', self.plan_card)
        self.mode_label.setObjectName('homeMode')
        self.mode_label.setTextColor('#77528b', '#d2badc')
        plan_header.addWidget(self.mode_label)
        plan_header.addStretch()
        self.daily_settings_button = TransparentToolButton(FluentIcon.SETTING, self.plan_card)
        self.daily_settings_button.setFixedSize(36, 36)
        self.daily_settings_button.setToolTip('调整每日计划')
        self.daily_settings_button.setAccessibleName('调整每日计划')
        self.daily_settings_button.clicked.connect(self.open_daily_settings)
        plan_header.addWidget(self.daily_settings_button)
        self.daily_button = PrimaryPushButton(FluentIcon.PLAY, '开始每日', self.plan_card)
        self.daily_button.setMinimumHeight(36)
        self.daily_button.clicked.connect(lambda: self.start_task(DailyTask))
        plan_header.addWidget(self.daily_button)
        plan_layout.addLayout(plan_header)
        self.plan_label = BodyLabel('正在读取已保存的设置…', self.plan_card)
        self.plan_label.setWordWrap(True)
        self.plan_label.setToolTip('奇迹之冠仅本期 0 进度运行；奇迹之旅仅领取待领奖励。')
        plan_layout.addWidget(self.plan_label)
        plan_layout.addWidget(CaptionLabel('家园、周本与奇迹之冠自动检测', self.plan_card))
        self.add_widget(self.plan_card)

        self.run_card = CardWidget(self)
        self.run_card.setBorderRadius(14)
        run_layout = QVBoxLayout(self.run_card)
        run_layout.setContentsMargins(22, 20, 22, 20)
        run_layout.setSpacing(12)
        run_header = QHBoxLayout()
        self.record_title = SubtitleLabel('最近运行', self.run_card)
        run_header.addWidget(self.record_title, 1)
        self.run_state_label = CaptionLabel('', self.run_card)
        self.run_state_label.setObjectName('homeRunState')
        self.run_state_label.setTextColor('#77528b', '#d2badc')
        run_header.addWidget(self.run_state_label)
        run_layout.addLayout(run_header)
        self.empty_state = QWidget(self.run_card)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(0, 20, 0, 20)
        empty_layout.setSpacing(6)
        empty_title = BodyLabel('暂无运行记录', self.empty_state)
        empty_title.setAlignment(Qt.AlignCenter)
        empty_hint = CaptionLabel('开始每日后，在这里查看进度', self.empty_state)
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        run_layout.addWidget(self.empty_state)
        self.result_label = QTextBrowser(self.run_card)
        self.result_label.setObjectName('homeResults')
        self.result_label.setFrameShape(QFrame.NoFrame)
        self.result_label.setMinimumHeight(100)
        self.result_label.setMaximumHeight(180)
        self.render_result(EMPTY_MESSAGE)
        run_layout.addWidget(self.result_label)
        controls = QHBoxLayout()
        self.pause_button = TransparentPushButton(FluentIcon.PAUSE, '暂停', self.run_card)
        self.pause_button.setToolTip('暂停或继续（F9）')
        self.pause_button.clicked.connect(self.pause_or_resume)
        self.stop_button = PushButton(FluentIcon.CLOSE, '停止', self.run_card)
        self.stop_button.setToolTip('停止当前任务（/）')
        self.stop_button.clicked.connect(lambda: og.app.run_control.stop())
        self.progress_button = TransparentPushButton('查看详情', self.run_card)
        self.progress_button.clicked.connect(self.show_progress)
        for button in [self.pause_button, self.stop_button]:
            controls.addWidget(button)
        controls.addStretch()
        controls.addWidget(self.progress_button)
        run_layout.addLayout(controls)
        self.add_widget(self.run_card)

        hint = CaptionLabel('/ 停止任务    ·    F9 暂停或继续', self)
        hint.setWordWrap(True)
        self.add_widget(hint)
        self.vBoxLayout.addStretch()
        self.apply_palette()
        qconfig.themeChangedFinished.connect(self.apply_palette)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)

    @property
    def name(self):
        return '运行总览'

    @property
    def icon(self):
        return FluentIcon.HOME

    @property
    def add_after_default_tabs(self):
        return False

    def start_task(self, cls):
        control = getattr(og.app, 'run_control', None)
        if control is not None and control.busy:
            return
        og.app.start_controller.start(self.get_task(cls))

    def pause_or_resume(self):
        og.app.run_control.pause_or_resume()

    def open_daily_settings(self):
        tab = self.window().onetime_tab
        self.window().switchTo(tab)
        for card in tab.card_widgets:
            if card.task.__class__ is DailyTask:
                card.setExpand(True)

    def show_progress(self):
        from nuannuan.ui.run_dialog import attach_run_dialog
        attach_run_dialog(og.app.run_control.app, self.window()).present()

    def apply_palette(self):
        dark = isDarkTheme()
        ink = '#ded9e3' if dark else '#35303d'
        background = '#1b1a20' if dark else '#f7f5f9'
        badge = '#35303e' if dark else '#eee8f2'
        accent = '#d2badc' if dark else '#77528b'
        self.view.setStyleSheet(
            f'QWidget#homeView {{background: {background};}}'
            f'QLabel#homeMode, QLabel#homeConnection, QLabel#homeRunState {{'
            f'background: {badge}; color: {accent}; border-radius: 10px; padding: 4px 10px;}}'
            f'QTextBrowser#homeResults {{background: transparent; border: none; color: {ink}; font-size: 13px;}}'
        )

    def render_result(self, text):
        if text != self._rendered_text:
            self.result_label.setPlainText(text)
            self._rendered_text = text
        empty = text == EMPTY_MESSAGE
        self.result_label.setVisible(not empty)
        self.empty_state.setVisible(empty)

    def refresh(self):
        self.game_running = any((p.info['name'] or '').lower() == 'x6game-win64-shipping.exe'
                                for p in psutil.process_iter(['name']))
        self.status_label.setText('游戏运行中' if self.game_running else '游戏未启动')
        control = getattr(og.app, 'run_control', None)
        owned = control is not None and control.busy
        current = getattr(self.executor, 'current_task', None)
        task = control.task if owned else (current if current not in getattr(self.executor, 'trigger_tasks', []) else None)
        busy = task is not None
        stopping = owned and control.cancel_event.is_set()
        paused = busy and (self.executor is None or self.executor.paused or task.paused)
        state = control.state if owned else '执行中'
        self.daily_button.setEnabled(not busy)
        self.daily_settings_button.setEnabled(not busy)
        self.pause_button.setEnabled(owned and state == '执行中' and not stopping)
        self.stop_button.setEnabled(owned and not stopping)
        self.pause_button.setText('继续' if paused and state == '执行中' else '暂停')
        self.pause_button.setVisible(busy)
        self.stop_button.setVisible(busy)
        has_details = busy or (control is not None and control.last_task is not None)
        self.progress_button.setVisible(has_details)
        self.progress_button.setEnabled(has_details)
        self.record_title.setText(task.name if busy else '最近运行')
        self.run_state_label.setText('已暂停' if paused and state == '执行中' else state)
        self.run_state_label.setVisible(busy)
        if self.executor is not None:
            daily = self.get_task(DailyTask)
            chosen = [name for name in ['美鸭梨挖掘', '朝夕心愿', '星海拾光', '奇迹之旅奖励'] if daily.config.get(name)]
            follow = ('\n结束后跑图：' + daily.config.get('接续跑图路线', '未选择')) if daily.config.get('每日结束后跑图') else ''
            self.mode_label.setText(daily.config.get('运行模式', '自动执行'))
            self.plan_label.setText(' · '.join(chosen) if chosen else '自动检测项目')
            if follow:
                self.plan_label.setText(self.plan_label.text() + follow)
        if busy:
            info = task.info
            label = info.get('当前步骤', info.get('启动状态', task.name))
            rows = [f'{key}：{value}' for key, value in info.items()
                    if key not in {'当前步骤', '运行报告'} and not (key == '启动状态' and value == label)]
            self.render_result(f'当前步骤：{label}\n' + '\n'.join(rows[-6:]))
            self._report_mtime = None
            return
        report_path = ROOT / 'logs/latest_run.json'
        try:
            stamp = report_path.stat().st_mtime_ns
            if stamp != self._report_mtime:
                data = json.loads(report_path.read_text(encoding='utf-8'))
                markers = {'succeeded': '✓', 'failed': '×', 'skipped': '·', 'partial': '⚠'}
                self.render_result('\n'.join(f'{markers.get(item["status"], "·")} {item["name"]}：{item["message"]}'
                                             for item in data['results']) or '本次运行已结束，详情见运行日志。')
                self._report_mtime = stamp
        except (OSError, ValueError, KeyError):
            self.render_result(EMPTY_MESSAGE)
