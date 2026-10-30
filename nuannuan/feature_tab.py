"""Common game operations, grouped without script or raw-data controls."""
import os
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget, QStackedWidget
from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox, FluentIcon, InfoBar, LineEdit, PushButton, TitleLabel
from ok.ui.qt.widget.CustomTab import CustomTab

from nuannuan.config import ROOT
from nuannuan.game_tools import PAGES
from nuannuan.tasks import OperationTask
from nuannuan.ui_actions import OperationStatus, dispatch_operation, open_extra_settings
from nuannuan.ui_logic import OPERATION_GROUPS


class FeatureTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.add_widget(TitleLabel('常用操作', self))
        intro = CaptionLabel('单次执行；日常自动运行请设置每日计划。', self)
        intro.setWordWrap(True)
        self.add_widget(intro)
        row = QHBoxLayout()
        self.group_combo = ComboBox(self)
        self.group_combo.addItems(list(OPERATION_GROUPS))
        row.addWidget(self.group_combo)
        row.addStretch()
        settings = PushButton(FluentIcon.SETTING, '材料、关卡与次数', self)
        settings.clicked.connect(lambda: open_extra_settings(self))
        row.addWidget(settings)
        guide = PushButton('功能说明', self)
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'README.md'))))
        row.addWidget(guide)
        self.addLayout(row)
        self.stack = QStackedWidget(self)
        self.buttons = {}
        for group, names in OPERATION_GROUPS.items():
            page = QWidget(self)
            layout = QVBoxLayout(page)
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(14)
            ordinary = [name for name in names if name not in {'页面跳转', '切换账号'}]
            for index, name in enumerate(ordinary):
                button = PushButton(name, page)
                button.setMinimumHeight(48)
                button.clicked.connect(lambda checked=False, action=name: self.run_operation(action))
                grid.addWidget(button, index//3, index%3)
                self.buttons[name] = button
            layout.addLayout(grid)
            if group == '游戏与界面':
                row = QHBoxLayout()
                self.page_combo = ComboBox(page)
                self.page_combo.addItems(PAGES)
                row.addWidget(BodyLabel('目标页面', page))
                row.addWidget(self.page_combo, 1)
                jump = PushButton('前往页面', page)
                jump.clicked.connect(lambda: self.run_operation('页面跳转'))
                row.addWidget(jump)
                layout.addLayout(row)
                row = QHBoxLayout()
                self.account_edit = LineEdit(page)
                self.account_edit.setPlaceholderText('填写游戏登录列表中的完整账号显示名')
                row.addWidget(self.account_edit, 1)
                account = PushButton('切换已保存账号', page)
                account.clicked.connect(lambda: self.run_operation('切换账号'))
                row.addWidget(account)
                layout.addLayout(row)
                row = QHBoxLayout()
                launch = PushButton('打开游戏 / 启动器', page)
                launch.clicked.connect(self.launch_game)
                row.addWidget(launch)
                change = PushButton('更换启动程序', page)
                change.clicked.connect(lambda: self.launch_game(select_only=True))
                row.addWidget(change)
                row.addStretch()
                layout.addLayout(row)
            layout.addStretch()
            self.stack.addWidget(page)
        self.add_widget(self.stack)
        self.group_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.hint = CaptionLabel('执行前请确认材料、关卡与次数。', self)
        self.hint.setWordWrap(True)
        self.add_widget(self.hint)
        self.status = OperationStatus(self)
        self.add_widget(self.status)
        QTimer.singleShot(0, self.load_settings)

    @property
    def name(self): return '常用操作'
    @property
    def icon(self): return FluentIcon.APPLICATION
    @property
    def add_after_default_tabs(self): return True

    def load_settings(self):
        task = self.get_task(OperationTask)
        self.page_combo.setCurrentText(task.config['目标页面'])
        self.account_edit.setText(task.config['账号显示名称'])

    def run_operation(self, name):
        values = {}
        if name == '页面跳转': values['目标页面'] = self.page_combo.currentText()
        if name == '切换账号':
            values['账号显示名称'] = self.account_edit.text().strip()
            if not values['账号显示名称']:
                InfoBar.warning('请填写账号显示名', '只选择游戏已经保存的账号，不填写密码。', parent=self.window())
                return
        if name in {'切换账号', '关闭游戏'}:
            detail = '将退出当前账号并选择指定账号。' if name == '切换账号' else '将通过游戏菜单退出游戏。'
            if QMessageBox.question(self, name, detail, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        dispatch_operation(self, name, values)

    def launch_game(self, select_only=False):
        task = self.get_task(OperationTask)
        path = task.config.get('启动程序路径', '')
        if select_only or not Path(path).is_file():
            path, _ = QFileDialog.getOpenFileName(self, '选择游戏或官方启动器', str(ROOT), 'Windows 程序 (*.exe)')
            if not path: return
            task.config['启动程序路径'] = path
        if not select_only:
            try:
                os.startfile(path)
                InfoBar.info('已打开启动程序', '完成更新 / 登录后，在连接页选择游戏窗口。', parent=self.window())
            except OSError as error:
                InfoBar.error('启动失败', str(error), parent=self.window())
