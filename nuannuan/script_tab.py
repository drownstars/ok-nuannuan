"""Script playback, recording and independent flow editing."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CheckBox, ComboBox, FluentIcon, InfoBar, LineEdit,
                            PrimaryPushButton, PushButton, SpinBox, TableWidget, TitleLabel)
from ok.ui.qt.widget.CustomTab import CustomTab

from nuannuan.config import ROOT
from nuannuan.route_store import RouteStore
from nuannuan.routes import RouteCatalog
from nuannuan.tasks import OperationTask
from nuannuan.ui_actions import OperationStatus, dispatch_operation
from nuannuan.ui_logic import FlowSteps

class ScriptTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.model = FlowSteps()
        self._loading = True
        self._dirty = False
        self._signature = None
        self.add_widget(TitleLabel('脚本管理', self))
        intro = BodyLabel('播放已导入的宏，录制自己的路线，或把路线与宏排成独立流程并手动运行。', self)
        intro.setWordWrap(True)
        self.add_widget(intro)
        row = QHBoxLayout()
        self.section_combo = ComboBox(self)
        self.section_combo.addItems(['宏与乐谱', '流程编排', '录制脚本'])
        row.addWidget(self.section_combo)
        row.addStretch()
        self.import_button = PushButton(FluentIcon.DOWNLOAD, '导入路线 / 宏 / 乐谱', self)
        self.import_button.clicked.connect(self.import_scripts)
        row.addWidget(self.import_button)
        folder = PushButton('打开脚本目录', self)
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'routes'))))
        row.addWidget(folder)
        self.addLayout(row)
        self.stack = QStackedWidget(self)
        self.add_widget(self.stack)
        self.section_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.build_playback()
        self.build_flow()
        self.build_recording()
        self.status = OperationStatus(self)
        self.add_widget(self.status)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_catalog)
        self.timer.start(2000)
        QTimer.singleShot(0, self.initialize)

    @property
    def name(self): return '脚本管理'
    @property
    def icon(self): return FluentIcon.EDIT
    @property
    def add_after_default_tabs(self): return True

    def new_page(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 12)
        self.stack.addWidget(page)
        return page, layout

    def build_playback(self):
        page, layout = self.new_page()
        row = QHBoxLayout()
        row.addWidget(BodyLabel('选择宏 / 乐谱', page))
        self.macro_combo = ComboBox(page)
        row.addWidget(self.macro_combo, 1)
        self.play_button = PrimaryPushButton(FluentIcon.PLAY, '开始播放', page)
        self.play_button.clicked.connect(self.play_macro)
        row.addWidget(self.play_button)
        layout.addLayout(row)
        label = BodyLabel('宏会执行记录的按键与鼠标动作。乐谱需要先在游戏中打开演奏界面。\n'
                          '路线运行和点位修改请前往后面的“路线与跑图”。', page)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()

    def build_flow(self):
        page, layout = self.new_page()
        row = QHBoxLayout()
        row.addWidget(BodyLabel('独立流程 · 保存后点击“立即运行本流程”执行', page))
        row.addStretch()
        for label, handler in [('导入流程', self.import_flow), ('导出流程', self.export_flow)]:
            button = PushButton(label, page)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.add_kind = ComboBox(page)
        self.add_kind.addItems(['路线', '宏 / 乐谱'])
        self.add_kind.currentTextChanged.connect(self.refresh_add_choices)
        row.addWidget(self.add_kind)
        self.add_script = ComboBox(page)
        row.addWidget(self.add_script, 1)
        add = PushButton(FluentIcon.ADD, '添加步骤', page)
        add.clicked.connect(self.add_step)
        row.addWidget(add)
        layout.addLayout(row)
        self.steps = TableWidget(page)
        self.steps.setColumnCount(3)
        self.steps.setHorizontalHeaderLabels(['启用', '步骤类型', '路线 / 宏名称'])
        self.steps.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.steps.setColumnWidth(0, 70)
        self.steps.setColumnWidth(1, 150)
        self.steps.setSelectionBehavior(TableWidget.SelectRows)
        self.steps.setEditTriggers(TableWidget.NoEditTriggers)
        self.steps.setMinimumHeight(250)
        layout.addWidget(self.steps)
        row = QHBoxLayout()
        for label, handler in [('删除选中步骤', self.remove_steps), ('上移', lambda: self.move_step(-1)), ('下移', lambda: self.move_step(1))]:
            button = PushButton(label, page)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch()
        self.save_button = PrimaryPushButton(FluentIcon.SAVE, '保存流程', page)
        self.save_button.clicked.connect(lambda: self.save_flow())
        row.addWidget(self.save_button)
        self.flow_run_button = PushButton(FluentIcon.PLAY, '立即运行本流程', page)
        self.flow_run_button.clicked.connect(self.run_flow)
        row.addWidget(self.flow_run_button)
        layout.addLayout(row)
        self.flow_status = BodyLabel('尚无步骤。选择路线或宏，添加到列表。', page)
        layout.addWidget(self.flow_status)

    def build_recording(self):
        page, layout = self.new_page()
        row = QHBoxLayout()
        row.addWidget(BodyLabel('录制内容', page))
        self.record_kind = ComboBox(page)
        self.record_kind.addItems(['宏', '路线'])
        row.addWidget(self.record_kind)
        row.addWidget(BodyLabel('名称', page))
        self.record_name = LineEdit(page)
        self.record_name.setText('我的录制')
        row.addWidget(self.record_name, 1)
        row.addWidget(BodyLabel('时长（秒）', page))
        self.duration = SpinBox(page)
        self.duration.setRange(1, 120)
        self.duration.setValue(20)
        row.addWidget(self.duration)
        layout.addLayout(row)
        self.seed_widget = QWidget(page)
        row = QHBoxLayout(self.seed_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(BodyLabel('起点参考路线', self.seed_widget))
        self.seed_combo = ComboBox(self.seed_widget)
        row.addWidget(self.seed_combo, 1)
        layout.addWidget(self.seed_widget)
        self.seed_widget.hide()
        self.record_kind.currentTextChanged.connect(lambda name: self.seed_widget.setVisible(name == '路线'))
        self.record_hint = BodyLabel('宏：只记录游戏窗口处于前台时的按键和鼠标；不记录其他窗口。\n'
                                    '路线：先手动站到参考路线起点附近，再开始录制并自行移动。特殊动作可在路线页补充。\n'
                                    '到时自动保存；停止 / 取消不会保存未完成的录制。', page)
        self.record_hint.setWordWrap(True)
        layout.addWidget(self.record_hint)
        row = QHBoxLayout()
        record = PrimaryPushButton(FluentIcon.PLAY, '开始录制', page)
        record.clicked.connect(self.record)
        row.addWidget(record)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def initialize(self):
        task = self.get_task(OperationTask)
        self.record_name.setText(task.config['录制名称'])
        self.duration.setValue(task.config['录制秒数'])
        self.refresh_catalog()
        self.load_flow()
        self._loading = False

    def refresh_catalog(self):
        if self.executor is None: return
        catalog = RouteCatalog()
        signature = tuple(catalog.records), tuple(catalog.macros), tuple(catalog.aliases.items())
        if signature == self._signature: return
        self._signature = signature
        task = self.get_task(OperationTask)
        for combo, values, key in [(self.macro_combo, list(catalog.macros), '宏名称'),
                                   (self.seed_combo, list(catalog.records), '录制参考路线')]:
            chosen = combo.currentText() or task.config[key]
            combo.clear()
            combo.addItems(values)
            combo.setCurrentText(catalog.resolve_name(chosen))
        self.refresh_add_choices()
        from nuannuan.map_mask_tab import MapMaskTab
        mask = self.window().findChild(MapMaskTab)
        if mask is not None: mask.refresh_routes()

    def refresh_add_choices(self):
        catalog = RouteCatalog()
        selected = self.add_script.currentText()
        self.add_script.clear()
        self.add_script.addItems(list(catalog.records if self.add_kind.currentText() == '路线' else catalog.macros))
        if selected: self.add_script.setCurrentText(selected)

    def read_steps(self):
        model = FlowSteps(self.model.items)
        for row, item in enumerate(model.items):
            item.update({'enabled': self.steps.cellWidget(row, 0).isChecked(),
                         'type': 'path' if self.steps.cellWidget(row, 1).currentText() == '路线' else 'macro',
                         'script_name': self.steps.cellWidget(row, 2).currentText()})
        return model

    def render_steps(self):
        # Remove cell widgets immediately; Qt defers their destruction and would
        # otherwise leave old combo boxes visible during reorder / deletion.
        for row in range(self.steps.rowCount()):
            for column in range(self.steps.columnCount()):
                widget = self.steps.cellWidget(row, column)
                if widget is not None:
                    widget.hide()
                    self.steps.removeCellWidget(row, column)
        self.steps.clearContents()
        self.steps.setRowCount(len(self.model.items))
        catalog = RouteCatalog()
        for row, item in enumerate(self.model.items):
            check = CheckBox(self.steps)
            check.setChecked(item['enabled'])
            kind = ComboBox(self.steps)
            kind.addItems(['路线', '宏 / 乐谱'])
            kind.setCurrentText('路线' if item['type'] == 'path' else '宏 / 乐谱')
            name = ComboBox(self.steps)
            values = list(catalog.records if item['type'] == 'path' else catalog.macros)
            if item['script_name'] not in values: values.append(item['script_name'])
            name.addItems(values)
            name.setCurrentText(item['script_name'])
            self.steps.setCellWidget(row, 0, check)
            self.steps.setCellWidget(row, 1, kind)
            self.steps.setCellWidget(row, 2, name)
            self.steps.setRowHeight(row, 42)
            check.stateChanged.connect(self.mark_dirty)
            name.currentTextChanged.connect(self.mark_dirty)
            def change_kind(value, choice=name):
                choices = list(catalog.records if value == '路线' else catalog.macros)
                choice.clear()
                choice.addItems(choices)
                self.mark_dirty()
            kind.currentTextChanged.connect(change_kind)
        self.flow_status.setText(f'{len(self.model.items)} 个步骤' + (' · 修改尚未保存' if self._dirty else ' · 已载入'))

    def mark_dirty(self, *args):
        if self._loading: return
        self._dirty = True
        self.flow_status.setText(f'{self.steps.rowCount()} 个步骤 · 修改尚未保存')

    def add_step(self):
        try:
            self.model = self.read_steps()
            self.model.add('path' if self.add_kind.currentText() == '路线' else 'macro', self.add_script.currentText())
            self.mark_dirty()
            self.render_steps()
        except RuntimeError as error: self.warn(error)

    def remove_steps(self):
        self.model = self.read_steps()
        self.model.remove([index.row() for index in self.steps.selectedIndexes()])
        self.mark_dirty()
        self.render_steps()

    def move_step(self, delta):
        row = self.steps.currentRow()
        self.model = self.read_steps()
        self.model.move(row, delta)
        self.mark_dirty()
        self.render_steps()
        if 0 <= row+delta < len(self.model.items): self.steps.selectRow(row+delta)

    def load_flow(self):
        self._loading = True
        try:
            encoded = self.get_task(OperationTask).config['流程JSON']
            self.model = FlowSteps(json.loads(encoded))
            self._dirty = False
            self.render_steps()
        except (ValueError, RuntimeError) as error: self.warn(error)
        finally: self._loading = False

    def save_flow(self, silent=False):
        try:
            model = self.read_steps()
            data = model.validate(allow_empty=True)
            encoded = json.dumps(data, ensure_ascii=False, indent=2)
            self.get_task(OperationTask).config['流程JSON'] = encoded
            self.model = model
            self._dirty = False
            self.flow_status.setText(f'已保存 {len(data)} 个步骤')
            if not silent: InfoBar.success('流程已保存', '点击“立即运行本流程”执行。', parent=self.window())
            return True
        except (ValueError, RuntimeError) as error:
            self.warn(error)
            return False

    def run_flow(self):
        try:
            data = self.read_steps().validate()
            dispatch_operation(self, '自定义流程', {'流程JSON': json.dumps(data, ensure_ascii=False)})
        except (ValueError, RuntimeError) as error: self.warn(error)

    def play_macro(self):
        dispatch_operation(self, '宏 / 乐谱', {'宏名称': self.macro_combo.currentText()})

    def record(self):
        name = self.record_name.text().strip()
        if not name:
            self.warn('请先填写录制名称')
            return
        dispatch_operation(self, '录制路线' if self.record_kind.currentText() == '路线' else '录制宏',
                           {'录制名称': name, '录制秒数': self.duration.value(), '录制参考路线': self.seed_combo.currentText()})

    def import_scripts(self):
        from nuannuan.route_tab import RouteTab
        tab = self.window().findChild(RouteTab)
        if tab: tab.choose_import()
        self.refresh_catalog()

    def import_flow(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入流程文件', str(ROOT), 'JSON 文件 (*.json)')
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if isinstance(data, dict): data = data.get('items', data.get('steps'))
            model = FlowSteps(data)
            model.validate(allow_empty=True)
            self.model = model
            self.mark_dirty()
            self.render_steps()
        except (ValueError, RuntimeError, OSError) as error: self.warn(error)

    def export_flow(self):
        try:
            data = self.read_steps().validate(allow_empty=True)
            path, _ = QFileDialog.getSaveFileName(self, '导出流程', str(ROOT/'我的流程.json'), 'JSON 文件 (*.json)')
            if path: Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except (ValueError, RuntimeError, OSError) as error: self.warn(error)

    def warn(self, error):
        QMessageBox.warning(self, '请检查步骤设置', str(error))
