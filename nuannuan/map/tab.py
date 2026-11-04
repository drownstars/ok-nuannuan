import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout,
                               QHeaderView, QMessageBox, QTableWidgetItem)
from qfluentwidgets import (BodyLabel, CheckBox, ComboBox, FluentIcon, InfoBar, PushButton,
                            SpinBox, SwitchButton, TableWidget, TitleLabel)
from ok import og
from ok.ui.qt.widget.CustomTab import CustomTab

from nuannuan.config import ROOT
from nuannuan.map.mask import (MAP_NAMES, MASK_SETTINGS, PointLibrary,
                               builtin_points, filtered_points)
from nuannuan.map.overlay import COLORS, OverlayController
from nuannuan.map.vision import PREFIXES
from nuannuan.routes.model import RouteCatalog


class MapPreview(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setMinimumHeight(330)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor('#14212f'))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._auto_fit = True
        self._map_name = None

    def wheelEvent(self, event):
        self._auto_fit = False
        scale = 1.18 if event.angleDelta().y() > 0 else 1/1.18
        if .02 < self.transform().m11()*scale < 30: self.scale(scale, scale)
        event.accept()

    def load(self, map_name, points):
        old_center = self.mapToScene(self.viewport().rect().center())
        changed = self._map_name != map_name
        self._map_name = map_name
        self.scene().clear()
        image = QPixmap(str(ROOT/'assets/maps'/f'{PREFIXES[map_name]}_luma_0125x.png'))
        if image.isNull(): return
        self.scene().addPixmap(image)
        previous = None
        for point in points:
            if point.map_name != map_name: continue
            x, y = point.x*.125, point.y*.125
            color = QColor(COLORS.get(point.label, '#b6e79b'))
            if point.label == 'route' and previous is not None and point.sequence == previous.sequence+1 and point.action != 'TELEPORT':
                self.scene().addLine(previous.x*.125, previous.y*.125, x, y, QPen(color, 1))
            previous = point if point.label == 'route' else None
            item = self.scene().addEllipse(x-2, y-2, 4, 4, QPen(QColor('#111b27')), color)
            item.setToolTip(f'{point.name}\n{MAP_NAMES[map_name]} · {point.x:.1f}, {point.y:.1f}')
        self.scene().setSceneRect(0, 0, image.width(), image.height())
        if changed or self._auto_fit: self.fit_map()
        else: self.centerOn(old_center)

    def fit_map(self):
        self._auto_fit = True
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_auto_fit', False) and not self.scene().sceneRect().isEmpty(): self.fit_map()

    def showEvent(self, event):
        super().showEvent(event)
        if self._auto_fit: self.fit_map()


class MapMaskTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.library = PointLibrary()
        self.controller = None
        self.points = []
        self.add_widget(TitleLabel('地图遮罩', self))
        from nuannuan.pearpal.panel import PearPalPanel
        self.official = PearPalPanel(self)
        self.add_widget(self.official)
        self.official.changed.connect(self.refresh_points)
        intro = BodyLabel('在游戏大地图 / 小地图上显示流转之柱、路线与导入资源点。标记穿透鼠标，不影响地图操作。', self)
        intro.setWordWrap(True)
        self.add_widget(intro)
        row = QHBoxLayout()
        row.addWidget(BodyLabel('显示游戏内地图点位', self))
        self.enable_switch = SwitchButton(self)
        self.enable_switch.setOnText('已开启')
        self.enable_switch.setOffText('已关闭')
        row.addWidget(self.enable_switch)
        row.addStretch()
        self.status_label = BodyLabel('地图遮罩已关闭', self)
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(450)
        row.addWidget(self.status_label)
        self.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(BodyLabel('游戏地图', self))
        self.map_combo = ComboBox(self)
        self.map_combo.addItems(['自动识别', *MAP_NAMES.values()])
        row.addWidget(self.map_combo)
        row.addWidget(BodyLabel('参考路线', self))
        self.route_combo = ComboBox(self)
        row.addWidget(self.route_combo, 1)
        self.import_button = PushButton(FluentIcon.DOWNLOAD, '导入资源点位', self)
        self.import_button.clicked.connect(self.choose_import)
        row.addWidget(self.import_button)
        self.addLayout(row)
        row = QHBoxLayout()
        self.checks = {}
        for key, label in [('显示流转之柱', '流转之柱'), ('显示路线点位', '所选路线'), ('显示导入点位', '导入资源'),
                           ('显示大地图', '大地图'), ('显示小地图', '小地图'), ('显示名称', '点位名称')]:
            check = CheckBox(label, self)
            self.checks[key] = check
            row.addWidget(check)
        row.addStretch()
        row.addWidget(BodyLabel('透明度', self))
        self.opacity = SpinBox(self)
        self.opacity.setRange(20, 100)
        row.addWidget(self.opacity)
        self.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(BodyLabel('预览地图', self))
        self.preview_combo = ComboBox(self)
        self.preview_combo.addItems(list(MAP_NAMES.values()))
        row.addWidget(self.preview_combo)
        row.addWidget(BodyLabel('资源类型', self))
        self.resource_combo = ComboBox(self)
        self.resource_combo.addItem('全部')
        row.addWidget(self.resource_combo, 1)
        fit = PushButton('显示整张地图', self)
        row.addWidget(fit)
        self.addLayout(row)
        self.preview = MapPreview(self)
        fit.clicked.connect(self.preview.fit_map)
        self.add_widget(self.preview)
        self.summary = BodyLabel('', self)
        self.add_widget(self.summary)
        hint = BodyLabel('离线预览可拖动 / 滚轮缩放。游戏内目前使用大地图最大缩放档；拖动时暂时隐藏，稳定后重新定位。\n'
                         '小地图首次需先打开大地图并对准角色附近。失焦、未知页面或定位失败时自动隐藏。\n'
                         '官方点位、登录同步与已收集过滤沿用奇想盒；流转之柱、路线和本地点位作为补充。双击官方点位查看详情。', self)
        hint.setWordWrap(True)
        self.add_widget(hint)
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['点位', '类型', '地图坐标'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.setMinimumHeight(180)
        self.table.cellDoubleClicked.connect(self.show_point_detail)
        self.add_widget(self.table)
        QTimer.singleShot(0, self.initialize)

    @property
    def name(self): return '地图遮罩'
    @property
    def icon(self): return FluentIcon.GLOBE
    @property
    def add_after_default_tabs(self): return True

    def initialize(self):
        self.settings = og.global_config.get_config(MASK_SETTINGS)
        self.controller = OverlayController(self.executor, self)
        self.controller.status_changed.connect(self.status_label.setText)
        control = getattr(self.executor, '_nuannuan_run_control', None)
        if control is not None: control.overlay_off.connect(self.disable_for_task)
        self.map_combo.setCurrentText(self.settings['地图'])
        self.route_combo.addItems(list(RouteCatalog().records))
        self.route_combo.setCurrentText(self.settings['所选路线'])
        self.preview_combo.setCurrentText(self.settings['预览地图'])
        self.opacity.setValue(self.settings['透明度'])
        for key, check in self.checks.items():
            check.setChecked(self.settings[key])
            check.stateChanged.connect(lambda value, field=key: self.change(field, value == Qt.Checked.value))
        self.map_combo.currentTextChanged.connect(lambda value: self.change('地图', value))
        self.route_combo.currentTextChanged.connect(lambda value: self.change('所选路线', value))
        self.preview_combo.currentTextChanged.connect(lambda value: self.change('预览地图', value))
        self.resource_combo.currentTextChanged.connect(lambda value: self.change('资源类型', value))
        self.opacity.valueChanged.connect(lambda value: self.change('透明度', value))
        self.enable_switch.checkedChanged.connect(self.controller.set_enabled)
        self.enable_switch.checkedChanged.connect(lambda enabled: self.official.load() if enabled else self.official.provider.note_overlay_inactive())
        self.controller.observation_ready.connect(lambda packet: self.official.provider.note_overlay_activity(is_bigmap_open=packet.get('mode') == 'bigmap') if self.controller.enabled else self.official.provider.note_overlay_inactive())
        from ok.core.events import communicate
        communicate.task_list_updated.connect(self.refresh_routes)
        self.refresh_points()

    def disable_for_task(self):
        self.enable_switch.setChecked(False)
        if self.controller is not None: self.controller.set_enabled(False)
        self.status_label.setText('自动任务运行期间已关闭地图遮罩；结束后可手动开启')

    def refresh_routes(self):
        if self.controller is None: return
        catalog = RouteCatalog()
        names = list(catalog.records)
        current_names = [self.route_combo.itemText(index) for index in range(self.route_combo.count())]
        selected = catalog.resolve_name(self.route_combo.currentText())
        self.route_combo.blockSignals(True)
        if names != current_names:
            self.route_combo.clear()
            self.route_combo.addItems(names)
        if selected in names: self.route_combo.setCurrentText(selected)
        self.route_combo.blockSignals(False)
        self.settings['所选路线'] = self.route_combo.currentText()
        self.refresh_points()

    def change(self, key, value):
        self.settings[key] = value
        self.refresh_points()

    def refresh_points(self):
        if self.controller is None: return
        try:
            official = self.official.points()
            local = builtin_points(self.route_combo.currentText())+self.library.points()
            self.points = official+local
            resource = self.settings.get('资源类型', '全部')
            selected = [p for p in official if resource == '全部' or p.label == resource]+list(filtered_points(local, self.settings))
            labels = sorted({p.label for p in official+self.library.points()})
            self.resource_combo.blockSignals(True)
            self.resource_combo.clear()
            self.resource_combo.addItems(['全部', *labels])
            self.resource_combo.setCurrentText(self.settings.get('资源类型', '全部'))
            self.resource_combo.blockSignals(False)
            settings = dict(self.settings)
            settings['地图'] = next((key for key, value in MAP_NAMES.items() if value == settings['地图']), '自动识别')
            self.controller.configure(settings, selected)
            self.update_preview(selected)
        except (ValueError, OSError, RuntimeError) as error:
            self.enable_switch.setChecked(False)
            self.status_label.setText(f'点位未加载：{error}')

    def update_preview(self, points):
        map_name = next(key for key, value in MAP_NAMES.items() if value == self.preview_combo.currentText())
        self.preview.load(map_name, points)
        rows = [p for p in points if p.map_name == map_name]
        self._visible_rows = rows[:500]
        self.summary.setText(f'{MAP_NAMES[map_name]}：{len(rows)} 个点位；官方点位按登录收集进度过滤，本地点位 {len(self.library.points())} 个。')
        self.table.setRowCount(min(len(rows), 500))
        for row, point in enumerate(rows[:500]):
            for column, value in enumerate([point.name, {'teleport': '流转之柱', 'route': '路线'}.get(point.label, point.label),
                                            f'{point.x:.1f}, {point.y:.1f}']):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def show_point_detail(self, row, column):
        if not 0 <= row < len(getattr(self, '_visible_rows', [])): return
        point = self._visible_rows[row]
        try:
            item = self.official.provider.get_point_detail(point.id)
        except ValueError: return
        detail = item.get('detail', {})
        state = ('已收集' if detail.get('awarded') else '未收集') if not detail.get('anonymous') else '未登录，未同步个人状态'
        QMessageBox.information(self, point.name, state+'\n'+str(detail.get('description') or '官方点位暂无文字说明'))

    def choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入本地图位文件', str(ROOT), 'JSON 文件 (*.json)')
        if path: self.import_points(path)

    def import_points(self, path):
        try:
            count = self.library.import_data(json.loads(Path(path).read_text(encoding='utf-8-sig')))
            self.refresh_points()
            InfoBar.success('点位已导入', f'新增 {count} 个资源点；原有点位已保留。', parent=self.window())
            return count
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, '无法导入点位', str(error))
