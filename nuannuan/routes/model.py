"""Validated route data. Never executes source files or imports Whimbox."""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from nuannuan.config import ROOT
from nuannuan.core.errors import AutomationError

OFFSETS = {'miraland': (20819, 21099), 'starsea': (2448, 1051), 'home': (1989, 1243), 'wanxiang': (1950, 987)}
SUPPORTED_ACTIONS = {None, 'TELEPORT', 'PICK_UP', 'CATCH_INSECT', 'WAIT', 'KEY_CLICK', 'GAME_KEY_CLICK',
                     'MACRO', 'TAKE_PHOTO', 'PLACE_ITEM', 'CHANGE_MUSIC', 'GROUP_CHAT',
                     'PICKUP_BOTTLE', 'DELIVERY_BOTTLE', 'TRANS_ANIMAL'}
SUPPORTED_ACTIONS.update({'MINIGAME', 'FISHING_STAR', 'FISHING', 'CLEAN_ANIMAL', 'FLOURISH',
                          'FLORAL_INSECT', 'MAGNET', 'BIG', 'FAIRY_ANIMAL', 'MACHINE_INFUSE', 'MACHINE_EXTRACT'})
GAME_KEYS = {'jump', 'falling', 'forward', 'interaction', 'item', 'bell', 'back', 'sprint',
             'map', 'daily_task', 'take_photo', 'monthly_pass', 'chat', 'ability_1', 'ability_2',
             'ability_3', 'ability_4', 'ability_5', 'ability_6', 'ability_7', 'ability_8'}
GAME_KEYS.update({'backward', 'left', 'right', 'event', 'dress', 'ability_derivation_world_1',
                   'ability_derivation_1', 'fishing_reel_in'})


class RouteError(AutomationError):
    pass


def number(value, low=-3_000_000, high=3_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise RouteError(f'无效路线数值：{value!r}')
    return float(value)


def game_to_map(position, map_name):
    if map_name not in OFFSETS or len(position) < 2:
        raise RouteError(f'不支持的地图或坐标：{map_name}')
    return tuple(number(position[i]) * (2 / 90) + OFFSETS[map_name][i] for i in range(2))


def validate_macro(data):
    raw = data.get('steps')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3000:
        raise RouteError('宏步骤数量无效')
    steps = []
    def expand(rows, depth=0):
        if depth > 4:
            raise RouteError('宏循环嵌套超过 4 层')
        index = 0
        while index < len(rows):
            row = rows[index]
            if not isinstance(row, dict): raise RouteError('宏步骤必须为对象')
            if row.get('type') == 'loop':
                count, length = row.get('loop_count'), row.get('loop_steps')
                if type(count) is not int or not 1 <= count <= 20 or type(length) is not int or not 1 <= length <= len(rows)-index-1:
                    raise RouteError('宏循环需要有限次数和有效步骤范围')
                for _ in range(count): expand(rows[index+1:index+1+length], depth+1)
                index += length+1
            else:
                steps.append(row)
                if len(steps) > 3000: raise RouteError('宏循环展开后超过 3000 步')
                index += 1
    expand(raw)
    held, elapsed = set(), 0.
    for step in steps:
        kind = step.get('type')
        if kind == 'gap':
            elapsed += number(step.get('duration'), 0, 30)
            if elapsed > 180:
                raise RouteError('宏总等待时间超过 180 秒')
        elif kind in {'wait_game_page', 'wait_not_game_page', 'goto_game_page'}:
            from nuannuan.daily.game_tools import PAGES
            if step.get('target_game_page') not in PAGES or held:
                raise RouteError('宏页面无效，或等待页面前仍有按下输入')
            elapsed += 20
            if elapsed > 180: raise RouteError('宏总等待时间超过 180 秒')
        elif kind in {'keyboard', 'game_key', 'mouse'}:
            key = step.get('key', '')
            if kind == 'game_key' and key not in GAME_KEYS:
                raise RouteError(f'不支持的游戏按键：{key}')
            if kind == 'keyboard' and not re.fullmatch(r'[a-z0-9_]{1,16}', key):
                raise RouteError(f'无效宏按键：{key}')
            if kind == 'mouse':
                if key not in {'mouse_left', 'mouse_right'}:
                    raise RouteError('不支持的鼠标按钮')
                xy = step.get('position')
                if not isinstance(xy, (list, tuple)) or len(xy) != 2:
                    raise RouteError('宏鼠标坐标缺失')
                number(xy[0], 0, 1919)
                number(xy[1], 0, 1079)
            action = step.get('action')
            identity = kind, key
            if action == 'press':
                if identity in held:
                    raise RouteError('宏重复按下同一输入')
                held.add(identity)
            elif action == 'release' and identity in held:
                held.remove(identity)
            else:
                raise RouteError('宏按下 / 释放顺序无效')
        else:
            raise RouteError(f'不支持的宏步骤：{kind}')
    if held:
        raise RouteError('宏结束时仍有未释放的输入')
    return steps


@dataclass(frozen=True)
class Point:
    id: int
    position: tuple[float, float]
    move_mode: str
    point_type: str
    action: str | None = None
    params: str | None = None


@dataclass(frozen=True)
class Route:
    name: str
    map_name: str
    points: list[Point]
    loops: list[dict] = field(default_factory=list)
    macros: dict = field(default_factory=dict)
    abilities: tuple[str, ...] = ()
    jump_ability: str = '自动'
    active_ability: str = '自动'
    origin_name: str = ''
    material_target: str = ''
    expected_count: int | None = None

    @classmethod
    def from_dict(cls, data, macros=None):
        macros = macros or {}
        if not isinstance(data, dict):
            raise RouteError('路线文件顶层必须为对象')
        info = data.get('info', {})
        if not isinstance(info, dict):
            raise RouteError('路线信息必须为对象')
        name, map_name = info.get('name'), info.get('map')
        if not isinstance(name, str) or not name.strip() or not isinstance(map_name, str) or map_name not in OFFSETS:
            raise RouteError('路线名称或地图无效')
        if info.get('version') not in {'2.0', '2.1', '2.2'}:
            raise RouteError('支持的路线版本为 2.0、2.1、2.2')
        raw_points = data.get('points')
        if not isinstance(raw_points, list) or not 1 <= len(raw_points) <= 5000:
            raise RouteError('路线需要 1 至 5000 个点位')
        points, ids = [], set()
        for raw in raw_points:
            if not isinstance(raw, dict):
                raise RouteError('路线点位必须为对象')
            identity = raw.get('id')
            if type(identity) is not int or identity in ids:
                raise RouteError('点位 ID 必须唯一且为整数')
            ids.add(identity)
            xy = raw.get('position')
            if not isinstance(xy, list) or len(xy) < 2:
                raise RouteError('点位坐标缺失')
            position = (number(xy[0]), number(xy[1]))
            mode, point_type = raw.get('move_mode'), raw.get('point_type')
            if mode not in {'WALK', 'JUMP'} or point_type not in {'TARGET', 'PATH', 'WAY', 'PASS'}:
                raise RouteError(f'不支持的移动方式或点位类型：{mode}/{point_type}')
            action, params = raw.get('action') or None, raw.get('action_params')
            if not isinstance(action, (str, type(None))) or action not in SUPPORTED_ACTIONS:
                label = {'MINIGAME': '小游戏', 'FISHING_STAR': '家园采星'}.get(str(action), str(action))
                raise RouteError(f'尚未支持的路线动作：{label}')
            if action in {'MACRO', 'MINIGAME'}:
                if not isinstance(params, str) or params not in macros:
                    raise RouteError(f'缺少路线依赖宏：{params}')
                validate_macro(macros[params])
            if action == 'WAIT':
                try:
                    number(float(params or 0.2), 0, 30)
                except (TypeError, ValueError) as error:
                    raise RouteError('等待时长无效') from error
            if action == 'GAME_KEY_CLICK' and params not in GAME_KEYS:
                raise RouteError(f'无效游戏按键：{params}')
            if action == 'KEY_CLICK' and (not isinstance(params, str) or not re.fullmatch(r'[a-z0-9_]{1,16}', params)):
                raise RouteError('无效路线按键')
            if action == 'TRANS_ANIMAL' and str(params or '1') not in {'1', '2', '3'}:
                raise RouteError('动物交互次数必须为 1 至 3')
            if action in {'CATCH_INSECT','CLEAN_ANIMAL'} and params not in (None,''):
                if not re.fullmatch(r'\d{1,3}',str(params)) or not 1<=int(params)<=100:
                    raise RouteError('采集点目标数量必须为 1 至 100')
            points.append(Point(identity, position, mode, point_type, action, params))
        loops = data.get('loops') or []
        if not isinstance(loops, list) or any(not isinstance(loop, dict) for loop in loops):
            raise RouteError('循环分段必须为对象列表')
        previous_end = -1
        id_index = {point.id: index for index, point in enumerate(points)}
        expanded_count = len(points)
        if loops and info['version'] == '2.0':
            raise RouteError('循环路线需要 2.1 或 2.2 版本')
        for loop in loops:
            start, end = id_index.get(loop.get('start_point_id'), -1), id_index.get(loop.get('end_point_id'), -1)
            count = loop.get('loop_count')
            if type(count) is not int or not 1 <= count <= 20 or not previous_end < start < end:
                raise RouteError('循环必须有限、顺序排列且不重叠（1 至 20 次）')
            if points[start].action != 'TELEPORT' and math.dist(game_to_map(points[start].position, map_name),
                                                                             game_to_map(points[end].position, map_name)) > 30:
                raise RouteError('循环起点必须可传送或靠近终点')
            expanded_count += (end - start + 1) * (count - 1)
            previous_end = end
        if expanded_count > 5000:
            raise RouteError('循环展开后超过 5000 个点位')
        from nuannuan.routes.ability import ABILITY_ICONS, JUMP_ICONS
        abilities = info.get('abilities', [])
        jump = info.get('jump_ability', '自动')
        active = info.get('active_ability', '自动')
        if not isinstance(abilities, list) or len(abilities) > 8 or any(not isinstance(a, str) or a not in ABILITY_ICONS for a in abilities):
            raise RouteError('路线额外能力列表无效')
        if jump not in ['自动', *JUMP_ICONS] or active not in ['自动', *ABILITY_ICONS]:
            raise RouteError('路线跳跃 / 主能力设置无效')
        origin = info.get('origin_name', name)
        if not isinstance(origin, str):
            raise RouteError('路线来源名称无效')
        target = info.get('target') or ''
        if not isinstance(target, str) or len(target) > 100:
            raise RouteError('路线目标材料名称无效')
        raw_count = info.get('count')
        if isinstance(raw_count, bool):
            raise RouteError('路线目标数量必须为整数')
        count = None
        if raw_count not in (None, '', 0, '0'):
            if not re.fullmatch(r'\d{1,5}', str(raw_count)) or not 1 <= int(raw_count) <= 10000:
                raise RouteError('路线目标数量需要 1 至 10000，或 0 表示跑完整条路线')
            count = int(raw_count)
        return cls(name, map_name, points, loops, macros, tuple(dict.fromkeys(abilities)), jump, active, origin, target, count)

    def expanded(self):
        indices = {point.id: index for index, point in enumerate(self.points)}
        by_start = {indices[loop['start_point_id']]: loop for loop in self.loops}
        index = 0
        while index < len(self.points):
            loop = by_start.get(index)
            if loop:
                end = indices[loop['end_point_id']]
                for _ in range(loop['loop_count']):
                    yield from self.points[index:end + 1]
                index = end + 1
            else:
                yield self.points[index]
                index += 1


class RouteCatalog:
    def __init__(self, root=None):
        self.root = Path(root or ROOT / 'routes')
        self.records, self.macros, self.errors = {}, {}, {}
        self.paths = {}
        state = self.root / '.library/state.json'
        self.aliases = json.loads(state.read_text(encoding='utf-8')).get('aliases', {}) if state.exists() else {}
        for path in sorted(self.root.glob('*.json')):
            if path.name == 'manifest.json':
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or not isinstance(data.get('info'), dict):
                    raise RouteError('路线文件需要有效的基本信息对象')
                name = data.get('info', {}).get('name')
                if not isinstance(name, str) or not name.strip() or name in self.records or name in self.macros:
                    raise RouteError('路线 / 宏名称缺失或重复')
                (self.records if 'points' in data else self.macros)[name] = data
                self.paths[name] = path
            except (ValueError, OSError, RouteError) as error:
                self.errors[path.name] = str(error)

    def resolve_name(self, name):
        seen = set()
        while name in self.aliases:
            if name in seen:
                raise RouteError('路线别名存在循环')
            seen.add(name)
            name = self.aliases[name]
        return name

    def get(self, name):
        name = self.resolve_name(name)
        if name not in self.records:
            raise RouteError(f'路线不存在：{name}')
        try:
            return Route.from_dict(self.records[name], self.macros)
        except (TypeError, KeyError, AttributeError, ValueError) as error:
            raise RouteError(f'路线数据结构无效：{error}') from error

    def inventory(self):
        rows = []
        for name, data in self.records.items():
            reason = ''
            try:
                self.get(name)
            except RouteError as error:
                reason = str(error)
            rows.append({'name': name, 'map': data['info'].get('map'), 'points': len(data.get('points', [])),
                         'ready': not reason, 'reason': reason})
        return rows
