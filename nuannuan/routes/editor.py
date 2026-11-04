"""Editable route points and ability requirements backed by the validated store."""
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMessageBox, QSpinBox, QTableWidgetItem, QVBoxLayout)
from qfluentwidgets import BodyLabel, ComboBox, PushButton, TableWidget

from nuannuan.routes.ability import ABILITY_ICONS, JUMP_ICONS
from nuannuan.routes.model import SUPPORTED_ACTIONS, RouteError
MAP_LABELS = {'miraland': '奇迹大陆', 'starsea': '星海', 'home': '家园', 'wanxiang': '万相境'}


class RouteEditor(QDialog):
    def __init__(self, store, name, parent=None):
        super().__init__(parent)
        self.store, self.original_name = store, name
        self.original = store.get_data(name)
        self.saved_name = None
        self.setWindowTitle('修改跑图路线')
        self.resize(1100, 720)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(self.original['info']['name'], self)
        form.addRow('路线名称', self.name_edit)
        self.map_combo = ComboBox(self)
        self.map_combo.addItems(list(MAP_LABELS.values()))
        self.map_combo.setCurrentText(MAP_LABELS[self.original['info']['map']])
        form.addRow('地图', self.map_combo)
        self.target_edit=QLineEdit(self.original['info'].get('target') or '',self)
        self.target_edit.setPlaceholderText('捕虫 / 清洁路线需填写实际材料名称，例如 珠链蝶、暮暮蝶')
        form.addRow('目标材料',self.target_edit)
        self.count_spin=QSpinBox(self)
        self.count_spin.setRange(0,10000)
        self.count_spin.setValue(int(self.original['info'].get('count') or 0))
        form.addRow('目标数量（0 = 跑完整条路线）',self.count_spin)
        options = QHBoxLayout()
        self.jump_combo = ComboBox(self)
        self.jump_combo.addItems(['自动', *JUMP_ICONS])
        self.jump_combo.setCurrentText(self.original['info'].get('jump_ability', '自动'))
        options.addWidget(BodyLabel('跳跃能力', self))
        options.addWidget(self.jump_combo)
        self.active_combo = ComboBox(self)
        self.active_combo.addItems(['自动', *ABILITY_ICONS])
        self.active_combo.setCurrentText(self.original['info'].get('active_ability', '自动'))
        options.addWidget(BodyLabel('主能力', self))
        options.addWidget(self.active_combo)
        self.extra_edit = QLineEdit(','.join(self.original['info'].get('abilities', [])), self)
        self.extra_edit.setPlaceholderText('额外轮盘能力，以逗号分隔，例如 捕虫,化万相')
        options.addWidget(self.extra_edit, 1)
        form.addRow('跑图前能力配置', options)
        layout.addLayout(form)
        hint = BodyLabel('坐标使用原路线游戏坐标。可修改点位、移动方式、动作及参数；保存前会校验整条路线。'
                         '\n含循环的路线需保留循环引用的点位编号。原文件修改前会保存历史。', self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        actions = QHBoxLayout()
        for text, callback in [('添加点位', self.add_point), ('删除选中点位', self.remove_points),
                               ('上移', lambda: self.move_point(-1)), ('下移', lambda: self.move_point(1))]:
            button = PushButton(text, self)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.points = TableWidget(self)
        self.points.setColumnCount(7)
        self.points.setHorizontalHeaderLabels(['编号', 'X 坐标', 'Y 坐标', '移动方式', '点位类型', '动作', '参数'])
        self.points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.points.setSelectionBehavior(TableWidget.SelectRows)
        layout.addWidget(self.points, 1)
        self.render_points(self.original['points'])
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def render_points(self, points):
        self.points.setRowCount(len(points))
        for row, point in enumerate(points):
            values = [str(point['id']), str(point['position'][0]), str(point['position'][1]),
                      point['move_mode'], point['point_type'], point.get('action') or '', point.get('action_params') or '']
            for column in [0, 1, 2, 6]:
                item = QTableWidgetItem(str(values[column]))
                if column == 0:
                    item.setData(Qt.UserRole, copy.deepcopy(point))
                self.points.setItem(row, column, item)
            for column, choices in [(3, ['WALK', 'JUMP']), (4, ['TARGET', 'PATH', 'WAY', 'PASS']),
                                     (5, ['', *sorted(action for action in SUPPORTED_ACTIONS if action)])]:
                combo = ComboBox(self.points)
                if values[column] not in choices:
                    choices = [*choices, values[column]]
                combo.addItems(choices)
                combo.setCurrentText(values[column])
                self.points.setCellWidget(row, column, combo)

    def read_points(self):
        points = []
        for row in range(self.points.rowCount()):
            identity = self.points.item(row, 0)
            point = copy.deepcopy(identity.data(Qt.UserRole) or {})
            try:
                point['id'] = int(identity.text())
                point['position'] = [float(self.points.item(row, 1).text()), float(self.points.item(row, 2).text()),
                                      *point.get('position', [])[2:]]
            except (TypeError, ValueError) as error:
                raise RouteError(f'第 {row + 1} 行的编号或坐标无效') from error
            point['move_mode'] = self.points.cellWidget(row, 3).currentText()
            point['point_type'] = self.points.cellWidget(row, 4).currentText()
            action = self.points.cellWidget(row, 5).currentText()
            params = self.points.item(row, 6).text().strip()
            point.pop('action', None)
            point.pop('action_params', None)
            if action:
                point['action'] = action
            if params:
                point['action_params'] = params
            points.append(point)
        return points

    def build_data(self):
        data = copy.deepcopy(self.original)
        map_name = next(key for key, label in MAP_LABELS.items() if label == self.map_combo.currentText())
        data['info'].update({'name': self.name_edit.text().strip(), 'map': map_name,
                             'target':self.target_edit.text().strip(),'count':self.count_spin.value(),
                             'jump_ability': self.jump_combo.currentText(), 'active_ability': self.active_combo.currentText(),
                             'abilities': [part.strip() for part in self.extra_edit.text().replace('，', ',').split(',') if part.strip()]})
        data['points'] = self.read_points()
        return data

    def add_point(self):
        try:
            points = self.read_points()
            identity = max((p['id'] for p in points), default=-1) + 1
            position = list(points[-1]['position']) if points else [0., 0.]
            points.append({'id': identity, 'position': position, 'move_mode': 'WALK', 'point_type': 'TARGET'})
            self.render_points(points)
            self.points.selectRow(len(points) - 1)
        except RouteError as error:
            QMessageBox.warning(self, '无法添加点位', str(error))

    def remove_points(self):
        rows = sorted({index.row() for index in self.points.selectedIndexes()}, reverse=True)
        for row in rows:
            self.points.removeRow(row)

    def move_point(self, delta):
        row = self.points.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.points.rowCount():
            return
        try:
            points = self.read_points()
            points[row], points[target] = points[target], points[row]
            self.render_points(points)
            self.points.selectRow(target)
        except RouteError as error:
            QMessageBox.warning(self, '无法移动点位', str(error))

    def save(self):
        try:
            self.saved_name = self.store.update(self.original_name, self.build_data())
        except (RouteError, OSError, ValueError) as error:
            QMessageBox.warning(self, '无法保存路线', str(error))
            return
        self.accept()
