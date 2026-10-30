from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QTableWidgetItem
from qfluentwidgets import (BodyLabel, ComboBox, FluentIcon, InfoBar, PrimaryPushButton,
                            PushButton, SpinBox, SwitchButton, TableWidget, TitleLabel)

from ok import og
from ok.ui.qt.widget.CustomTab import CustomTab

from nuannuan.routes import RouteCatalog
from nuannuan.tasks import DailyTask, RouteTask
from nuannuan.route_store import RouteStore
from nuannuan.config import ROOT, ROUTE_OPTIONS_NAME
from nuannuan.ability import ABILITY_ICONS, JUMP_ICONS


class RouteTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.store = RouteStore()
        self.selected_name = ''
        self.add_widget(TitleLabel('路线与自动跑图', self))
        intro = BodyLabel('选择本地路线，自动传送、识别小地图位置并逐点移动。\n'
                          '可在跑图前自动配置并复核能力；修改、删除会保留历史，修改从下次运行生效。', self)
        intro.setWordWrap(True)
        self.add_widget(intro)
        row = QHBoxLayout()
        self.route_combo = ComboBox(self)
        self.route_combo.setMinimumWidth(370)
        row.addWidget(self.route_combo, 1)
        self.start_button = PrimaryPushButton(FluentIcon.PLAY, '开始跑图', self)
        self.start_button.clicked.connect(self.start_route)
        row.addWidget(self.start_button)
        refresh = PushButton(FluentIcon.SYNC, '刷新路线', self)
        refresh.clicked.connect(self.reload_catalog)
        row.addWidget(refresh)
        self.addLayout(row)
        options = QHBoxLayout()
        options.addWidget(BodyLabel('单条路线最多运行（分钟）', self))
        self.timeout = SpinBox(self)
        self.timeout.setRange(1, 120)
        self.timeout.setValue(20)
        options.addWidget(self.timeout)
        options.addStretch()
        options.addWidget(BodyLabel('允许聚会聊天', self))
        self.chat_switch = SwitchButton(self)
        self.chat_switch.setOnText('允许')
        self.chat_switch.setOffText('关闭')
        options.addWidget(self.chat_switch)
        self.addLayout(options)
        ability_row = QHBoxLayout()
        ability_row.addWidget(BodyLabel('跑图前自动配置能力', self))
        self.ability_switch = SwitchButton(self)
        self.ability_switch.setOnText('开启')
        self.ability_switch.setOffText('关闭')
        ability_row.addWidget(self.ability_switch)
        ability_row.addWidget(BodyLabel('能力方案', self))
        self.ability_plan = SpinBox(self)
        self.ability_plan.setRange(1, 3)
        ability_row.addWidget(self.ability_plan)
        ability_row.addWidget(BodyLabel('默认跳跃', self))
        self.jump_combo = ComboBox(self)
        self.jump_combo.addItems(list(JUMP_ICONS))
        ability_row.addWidget(self.jump_combo)
        ability_row.addWidget(BodyLabel('默认主能力', self))
        self.active_combo = ComboBox(self)
        self.active_combo.addItems(['自动', *ABILITY_ICONS])
        ability_row.addWidget(self.active_combo)
        ability_row.addStretch()
        self.addLayout(ability_row)
        saved = og.global_config.get_config(ROUTE_OPTIONS_NAME)
        self.ability_switch.setChecked(saved['跑图前自动配置能力'])
        self.ability_plan.setValue(saved['能力方案'])
        self.jump_combo.setCurrentText(saved['跳跃能力'])
        self.active_combo.setCurrentText(saved['主能力'])
        self.ability_switch.checkedChanged.connect(lambda value: self.set_ability_option('跑图前自动配置能力', value))
        self.ability_plan.valueChanged.connect(lambda value: self.set_ability_option('能力方案', value))
        self.jump_combo.currentTextChanged.connect(lambda value: self.set_ability_option('跳跃能力', value))
        self.active_combo.currentTextChanged.connect(lambda value: self.set_ability_option('主能力', value))
        management = QHBoxLayout()
        self.import_button = PushButton(FluentIcon.DOWNLOAD, '导入路线 / 宏', self)
        self.import_button.clicked.connect(self.choose_import)
        self.edit_button = PushButton(FluentIcon.EDIT, '修改路线', self)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = PushButton(FluentIcon.DELETE, '删除路线', self)
        self.delete_button.clicked.connect(self.delete_selected)
        self.follow_button = PushButton(FluentIcon.CALENDAR, '每日后运行此路线', self)
        self.follow_button.clicked.connect(self.set_daily_follow)
        for button in [self.import_button, self.edit_button, self.delete_button, self.follow_button]:
            management.addWidget(button)
        management.addStretch()
        self.addLayout(management)
        self.summary = BodyLabel('', self)
        self.summary.setWordWrap(True)
        self.add_widget(self.summary)
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['路线', '地图', '点位', '状态'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setMinimumHeight(290)
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.cellClicked.connect(self.select_row)
        self.add_widget(self.table)
        self.progress_label = BodyLabel('尚未开始跑图。按 / 停止任务，F9 暂停 / 继续；运行小窗显示当前步骤。', self)
        self.progress_label.setWordWrap(True)
        self.add_card('当前进度', self.progress_label)
        self.rows = []
        self.route_combo.currentTextChanged.connect(self.describe_route)
        self.reload_catalog()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_progress)
        self.timer.start(500)

    @property
    def name(self):
        return '路线与跑图'

    @property
    def icon(self):
        return FluentIcon.GLOBE

    @property
    def add_after_default_tabs(self):
        return True

    def reload_catalog(self):
        selected = self.route_combo.currentText()
        self.rows = RouteCatalog(self.store.root).inventory()
        self.route_combo.blockSignals(True)
        self.route_combo.clear()
        self.route_combo.addItems([row['name'] for row in self.rows if row['ready']])
        if selected:
            self.route_combo.setCurrentText(selected)
        self.route_combo.blockSignals(False)
        self.table.setRowCount(len(self.rows))
        map_labels = {'starsea': '星海', 'miraland': '奇迹大陆', 'home': '家园', 'wanxiang': '万相境'}
        for index, row in enumerate(self.rows):
            values = [row['name'], map_labels.get(row['map'], row['map']), str(row['points']),
                      '可运行 · 待实机校验' if row['ready'] else row['reason']]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
        self.describe_route(self.route_combo.currentText())

    def describe_route(self, name):
        self.selected_name = name
        row = next((row for row in self.rows if row['name'] == name), None)
        ready = sum(item['ready'] for item in self.rows)
        self.summary.setText(f'已载入 {len(self.rows)} 条路线，其中 {ready} 条通过数据与动作校验。'
                             + (f'\n当前选择：{row["name"]}，{row["points"]} 个点位。' if row else ''))

    def select_row(self, row, column):
        self.selected_name = self.rows[row]['name']
        if self.rows[row]['ready']:
            self.route_combo.setCurrentText(self.rows[row]['name'])

    def set_ability_option(self, key, value):
        og.global_config.get_config(ROUTE_OPTIONS_NAME)[key] = value

    def library_changed(self, selected=None):
        self.reload_catalog()
        if selected:
            self.route_combo.setCurrentText(selected)
        if self.store.root != (ROOT / 'routes').resolve() or self.executor is None:
            return
        catalog = RouteCatalog(self.store.root)
        names = [row['name'] for row in self.rows if row['ready']]
        for cls, key in [(DailyTask, '接续跑图路线'), (RouteTask, '路线名称')]:
            task = self.get_task(cls)
            configured = task.config.get(key, '')
            resolved = catalog.resolve_name(configured)
            if resolved in names:
                task.config[key] = resolved
            task.config_type[key] = {'type': 'drop_down', 'options': names + ([configured] if configured and configured not in names else [])}
        from ok.core.events import communicate
        communicate.task_list_updated.emit()

    def choose_import(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '导入路线或宏（可多选依赖文件）', str(ROOT), 'JSON 文件 (*.json)')
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        try:
            names = self.store.import_files(paths)
            self.library_changed(names[-1] if names else None)
            InfoBar.success('导入完成', f'已处理 {len(names)} 条路线 / 宏；同名不同内容会另存，不覆盖已有路线。', parent=self.window())
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, '无法导入', str(error))

    def edit_selected(self):
        from nuannuan.route_editor import RouteEditor
        if not self.selected_name:
            return
        try:
            editor = RouteEditor(self.store, self.selected_name, self)
            if editor.exec():
                self.library_changed(editor.saved_name)
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, '无法修改路线', str(error))

    def delete_selected(self):
        if not self.selected_name:
            return
        answer = QMessageBox.question(self, '删除路线', f'删除“{self.selected_name}”？\n原始参考文件不受影响，当前副本会保留在路线历史中。')
        if answer != QMessageBox.Yes:
            return
        try:
            self.store.delete(self.selected_name)
            self.library_changed()
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, '无法删除路线', str(error))

    def set_daily_follow(self):
        name = self.route_combo.currentText()
        try:
            RouteCatalog(self.store.root).get(name)
            task = self.get_task(DailyTask)
            task.config['接续跑图路线'] = name
            task.config['每日结束后跑图'] = True
            InfoBar.success('已设置每日后跑图', f'每日正常结束后将运行“{name}”。可在每日任务设置中关闭。', parent=self.window())
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, '无法设置', str(error))

    def start_route(self):
        task = self.get_task(RouteTask)
        task.config['路线名称'] = self.route_combo.currentText()
        task.config['允许聚会聊天'] = self.chat_switch.isChecked()
        task.config['单条路线最大分钟'] = self.timeout.value()
        og.app.start_controller.start(task)

    def refresh_progress(self):
        if self.executor is None:
            return
        task = self.get_task(RouteTask)
        keys = ['跑图进度', '视觉位置', '定位置信度', '跑图结果', '运行报告', 'Error']
        rows = [f'{key}：{task.info[key]}' for key in keys if key in task.info]
        if rows:
            self.progress_label.setText('\n'.join(rows))
