"""Controls for the original Whimbox official-map provider."""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CheckBox, ComboBox, PushButton
from nuannuan.pearpal._pearpal.pearpal_provider import OfficialPearPalProvider
from nuannuan.pearpal.bridge import adapt_points, LABELS


class PearPalPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from ok.util.config import Config
        self.preferences = Config('pearpal-map', {'region': 'cn', 'hide_awarded': True, 'labels': list(LABELS)})
        self.provider = OfficialPearPalProvider(enabled=True, region=self.preferences['region'])
        self.provider.set_hide_awarded(self.preferences['hide_awarded'])
        self.started = False
        self.dialogs = {}
        self._revision = -1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.region = ComboBox(self)
        self.region.addItems(['国服 · 美鸭梨', '国际服 · PearPal'])
        self.region.setCurrentIndex(0 if self.preferences['region'] == 'cn' else 1)
        row.addWidget(self.region)
        self.login_button = PushButton('登录官方地图', self)
        self.login_button.clicked.connect(self.login)
        row.addWidget(self.login_button)
        self.load_button = PushButton('加载官方点位', self)
        self.load_button.clicked.connect(self.load)
        row.addWidget(self.load_button)
        self.refresh_button = PushButton('同步收集进度', self)
        self.refresh_button.clicked.connect(lambda: self.provider.refresh_user_state())
        row.addWidget(self.refresh_button)
        self.disconnect_button = PushButton('断开登录', self)
        self.disconnect_button.clicked.connect(self.disconnect)
        row.addWidget(self.disconnect_button)
        self.clear_button = PushButton('清除登录信息', self)
        self.clear_button.clicked.connect(self.clear_login)
        row.addWidget(self.clear_button)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        self.hide_collected = CheckBox('隐藏已收集', self)
        self.hide_collected.setChecked(self.preferences['hide_awarded'])
        self.hide_collected.toggled.connect(self.set_hide_collected)
        row.addWidget(self.hide_collected)
        self.labels = {}
        for identity, name in LABELS.items():
            box = CheckBox(name, self)
            box.setChecked(identity in self.preferences['labels'])
            box.toggled.connect(self.save_labels)
            self.labels[identity] = box
            row.addWidget(box)
        row.addStretch()
        layout.addLayout(row)
        self.status = BodyLabel('官方点位未加载；登录后可同步个人收集进度。', self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.region.currentIndexChanged.connect(self.set_region)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)

    @property
    def region_id(self): return 'cn' if self.region.currentIndex() == 0 else 'oversea'

    def set_region(self, _):
        self.preferences['region'] = self.region_id
        for dialog in self.dialogs.values(): dialog.hide()
        self.provider.set_region(self.region_id)
        if self.started: self.load()
        self.changed.emit()

    def set_hide_collected(self, value):
        self.preferences['hide_awarded'] = value
        self.provider.set_hide_awarded(value)
        self.changed.emit()

    def save_labels(self, _):
        self.preferences['labels'] = [key for key, box in self.labels.items() if box.isChecked()]
        self.changed.emit()

    def load(self):
        self.started = True
        self.provider.list_points()
        self.poll()

    def login(self):
        from nuannuan.pearpal.login import PearPalLogin
        region = self.region_id
        if region not in self.dialogs:
            self.dialogs[region] = PearPalLogin(self.provider, region, self)
        dialog = self.dialogs[region]
        dialog._submitted = None
        dialog.show()
        dialog.raise_()
        self.load()

    def disconnect(self):
        self.provider.disconnect_user()
        for dialog in self.dialogs.values(): dialog.hide()
        self.poll()

    def clear_login(self):
        self.login()
        self.dialogs[self.region_id].clear_login()

    def points(self):
        if not self.started: return []
        selected = [key for key, box in self.labels.items() if box.isChecked()]
        return adapt_points(self.provider.list_points(label_ids=selected))

    def poll(self):
        if not self.started: return
        status = self.provider.get_data_status()
        user = self.provider.get_user_status()
        self.refresh_button.setEnabled(user['authenticated'] and not user['refreshing'])
        self.disconnect_button.setEnabled(user['authenticated'])
        authentication = '已登录 '+user['openid_masked'] if user['authenticated'] else '未登录'
        error = user.get('auth_error') or user.get('refresh_error') or status.get('points_error', '')
        count = len(self.provider.list_points())
        self.status.setText(f'{authentication} · 官方可显示点位 {count} · 最近同步：{user.get("last_refresh_at") or "尚未同步"}'
                            +(f' · {error}' if error else ''))
        if user['authenticated']:
            dialog = self.dialogs.get(self.region_id)
            if dialog is not None: dialog.hide()
        revision = self.provider.points_revision
        if revision != self._revision:
            self._revision = revision
            self.changed.emit()
