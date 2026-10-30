"""Validated local macros, music, flows and input/route recording data."""
import copy
import math
import time

from nuannuan.routes import Route, RouteCatalog, RouteError, OFFSETS, validate_macro


class ScriptRunner:
    def __init__(self, port, catalog=None):
        self.port = port
        self.catalog = catalog or RouteCatalog()
        self.results = []

    def route(self, name):
        self.catalog.get(name)
        return self.port.execute_route(name)

    def macro(self, name):
        name = self.catalog.resolve_name(name)
        if name not in self.catalog.macros:
            raise RouteError(f'宏 / 乐谱不存在：{name}')
        record = self.catalog.macros[name]
        validate_macro(record)
        if record['info'].get('type') == '乐谱':
            # Do not interpret ordinary game keys as notes until the music HUD is visible.
            self.port.goto_page('演奏')
        self.port.execute_macro(record)
        return {'status': 'succeeded', 'message': f'已执行宏 / 乐谱：{name}；游戏结果需任务卡或获得结果另行复核'}

    def validate_flow(self, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise RouteError('流程需要 1 至 100 个步骤')
        enabled = []
        for item in items:
            if not isinstance(item, dict) or item.get('type') not in {'path', 'macro'} or not isinstance(item.get('script_name'), str):
                raise RouteError('流程步骤需 type=path/macro 和 script_name')
            if not item.get('enabled', True):
                continue
            name = self.catalog.resolve_name(item['script_name'])
            if item['type'] == 'path':
                route = self.catalog.get(name)
                validate = getattr(self.port, 'validate_route', None)
                if validate:
                    validate(route)
            else:
                if name not in self.catalog.macros:
                    raise RouteError(f'宏不存在：{name}')
                validate_macro(self.catalog.macros[name])
            enabled.append({**item, 'script_name': name})
        if not enabled:
            raise RouteError('请至少启用一个流程步骤')
        return enabled

    def flow(self, items):
        enabled = self.validate_flow(items)
        self.results = []
        for item in enabled:
            name = item['script_name']
            try:
                result = self.route(name) if item['type'] == 'path' else self.macro(name)
            except RouteError as error:
                self.results.append({'name': name, 'status': 'failed', 'message': str(error)})
                raise
            self.results.append({'name': name, **result})
        return {'status': 'succeeded', 'message': f'已执行 {len(enabled)} 个流程步骤', 'steps': self.results}


class MacroRecording:
    """Receives game-scoped events; never records text or windows outside the game."""
    def __init__(self, name):
        self.name = str(name).strip()
        self.steps = []
        self.held = {}
        self.previous = 0.
        self.elapsed = 0.

    def gap(self, timestamp):
        if not math.isfinite(timestamp) or timestamp < self.previous or timestamp > 180:
            raise RouteError('录制时间无效或超过 180 秒')
        duration = timestamp - self.previous
        while duration > 0:
            part = min(duration, 30.)
            self.steps.append({'type': 'gap', 'duration': part})
            duration -= part
        self.previous = timestamp

    def feed(self, kind, key, action, timestamp, position=None, in_game=True):
        if kind not in {'keyboard', 'mouse'} or action not in {'press', 'release'}:
            raise RouteError('录制仅支持键盘与鼠标按下 / 释放')
        identity = kind, key
        if not in_game or (action == 'press' and identity in self.held) or (action == 'release' and identity not in self.held):
            return
        step = {'type': kind, 'key': key, 'action': action}
        if kind == 'mouse':
            if not isinstance(position, (list, tuple)) or len(position) != 2:
                raise RouteError('录制鼠标位置无效')
            step['position'] = list(position)
        self.gap(float(timestamp))
        self.steps.append(step)
        if action == 'press': self.held[identity] = step
        else: self.held.pop(identity)

    def finish(self, timestamp):
        if not self.steps:
            raise RouteError('没有记录到游戏输入，未保存空宏')
        self.gap(float(timestamp))
        for (kind, key), step in list(self.held.items()):
            self.steps.append({**step, 'action': 'release'})
        self.held.clear()
        result = {'info': {'name': self.name, 'type': '宏', 'version': '3.0'}, 'steps': copy.deepcopy(self.steps)}
        validate_macro(result)
        return result


class RouteRecording:
    def __init__(self, name, map_name):
        if map_name not in OFFSETS:
            raise RouteError('无效录制地图')
        self.name, self.map_name, self.points = name, map_name, []

    def add(self, position, teleport=False, action=None, mode='WALK'):
        offset = OFFSETS[self.map_name]
        raw = [round((position[i] - offset[i]) * 45, 3) for i in range(2)]
        if self.points and math.dist(raw, self.points[-1]['position']) < 90 and not action:
            return
        self.points.append({'id': len(self.points), 'position': raw, 'move_mode': mode,
                            'point_type': 'TARGET' if teleport or action else 'PASS',
                            'action': 'TELEPORT' if teleport else action})

    def finish(self):
        if len(self.points) < 2:
            raise RouteError('有效点位不足 2 个，未保存路线')
        self.points[-1]['point_type'] = 'TARGET'
        data = {'info': {'name': self.name, 'map': self.map_name, 'version': '2.0'}, 'points': self.points}
        Route.from_dict(data)
        return data


def record_route(port, seed_name, duration, name):
    from nuannuan.routes import game_to_map
    from nuannuan.route_runtime import RouteRuntime
    from nuannuan.route_store import RouteStore
    seed = RouteCatalog().get(seed_name)
    first = seed.points[0]
    if first.action != 'TELEPORT':
        raise RouteError('参考路线起点必须是流转之柱')
    runtime = RouteRuntime(port)
    hint = game_to_map(first.position, seed.map_name)
    runtime.nearest_checkpoint(hint, seed.map_name)
    current = runtime.locate(seed.map_name, hint)
    if math.dist(current, hint) > 60:
        raise RouteError('请先手动到参考路线的起点流转之柱附近再录制')
    recorder = RouteRecording(name, seed.map_name)
    recorder.add(hint, teleport=True)
    recorder.add(current)
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        port.sleep(.25)
        current = runtime.locate(seed.map_name, current)
        recorder.add(current)
        port.task.info_set('录制点位', len(recorder.points))
    record = recorder.finish()
    names = RouteStore().import_records([record])
    return {'status': 'succeeded', 'message': f'路线录制完成：{names[0]}，可在路线面板继续编辑', 'points': len(record['points'])}


def record_macro(port, duration, name):
    import win32api
    import win32gui
    from nuannuan.route_store import RouteStore
    hwnd = getattr(port.task.executor.device_manager.hwnd_window, 'hwnd', None)
    if not hwnd:
        raise RouteError('没有游戏窗口句柄，不能限定录制范围')
    recorder = MacroRecording(name)
    keys = {**{ord(k.upper()): k for k in 'abcdefghijklmnopqrstuvwxyz0123456789'},
            0x20: 'space', 0x10: 'shift', 0x11: 'ctrl', 0x12: 'alt', 0x1B: 'esc',
            0x0D: 'enter', 0x08: 'backspace', 0x09: 'tab', 0x25: 'left', 0x26: 'up',
            0x27: 'right', 0x28: 'down', 0x01: 'mouse_left', 0x02: 'mouse_right'}
    held = set()
    start = time.monotonic()
    while time.monotonic() - start < duration:
        timestamp = time.monotonic() - start
        foreground = win32gui.GetForegroundWindow()
        active = foreground == hwnd or win32gui.IsChild(foreground, hwnd)
        for vk, key in keys.items():
            down = bool(win32api.GetAsyncKeyState(vk) & 0x8000) and active
            if down == (vk in held):
                continue
            position = None
            if key.startswith('mouse'):
                x, y = win32gui.ScreenToClient(hwnd, win32gui.GetCursorPos())
                _, _, width, height = win32gui.GetClientRect(hwnd)
                position = [max(0, min(1919, x * 1920 / max(1, width))),
                            max(0, min(1079, y * 1080 / max(1, height)))]
            recorder.feed('mouse' if key.startswith('mouse') else 'keyboard', key,
                          'press' if down else 'release', timestamp, position)
            if down: held.add(vk)
            else: held.discard(vk)
        port.sleep(.02)
    data = recorder.finish(time.monotonic() - start)
    names = RouteStore().import_records([data])
    return {'status': 'succeeded', 'message': f'已保存游戏窗口内的宏：{names[0]}；取消录制时不保存'}
