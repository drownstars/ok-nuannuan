"""Local point data and map projection, independent of windows and input."""
import json
import math
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from nuannuan.config import ROOT
from nuannuan.map_vision import BIGMAP_SCALES, MINIMAP_SCALES, MapLocator
from nuannuan.routes import OFFSETS, RouteCatalog, RouteError, game_to_map, number

MAP_NAMES = {'miraland': '奇迹大陆', 'starsea': '星海', 'home': '家园', 'wanxiang': '万相境'}
MASK_SETTINGS = '地图遮罩'
MASK_DEFAULTS = {'显示大地图': True, '显示小地图': True, '显示名称': True, '透明度': 85,
                 '显示流转之柱': True, '显示路线点位': True, '显示导入点位': True,
                 '地图': '自动识别', '预览地图': '星海', '所选路线': '星海拾光_更改音乐', '资源类型': '全部'}


@dataclass(frozen=True)
class MaskPoint:
    id: str
    name: str
    label: str
    map_name: str
    x: float
    y: float
    sequence: int = -1
    action: str = ''


@dataclass(frozen=True)
class Viewport:
    map_name: str
    mode: str
    center: tuple
    scale: float  # full atlas pixels per reference-screen pixel
    rect: tuple  # x/y/width/height in 1920x1080 reference pixels


@dataclass(frozen=True)
class Marker:
    id: str
    name: str
    label: str
    x: float
    y: float
    sequence: int = -1
    action: str = ''


@dataclass(frozen=True)
class Observation:
    viewport: Viewport | None
    message: str
    confidence: float = 0.


def project_points(points, viewport):
    if viewport.scale <= 0 or not math.isfinite(viewport.scale):
        raise RouteError('地图投影比例无效')
    left, top, width, height = viewport.rect
    if width <= 0 or height <= 0: return []
    cx, cy = left+width/2, top+height/2
    markers = []
    for point in points:
        if point.map_name != viewport.map_name: continue
        x = cx+(point.x-viewport.center[0])/viewport.scale
        y = cy+(point.y-viewport.center[1])/viewport.scale
        if not left <= x <= left+width or not top <= y <= top+height: continue
        if viewport.mode == 'minimap' and math.hypot(x-cx, y-cy) > min(width, height)/2-4: continue
        markers.append(Marker(point.id, point.name, point.label, x, y, point.sequence, point.action))
    return markers


def logical_rect(physical, physical_monitor_origin, logical_monitor_origin, ratio):
    if not math.isfinite(ratio) or ratio <= 0: raise RouteError('屏幕缩放比例无效')
    x, y, width, height = physical
    return (round(logical_monitor_origin[0]+(x-physical_monitor_origin[0])/ratio),
            round(logical_monitor_origin[1]+(y-physical_monitor_origin[1])/ratio),
            round(width/ratio), round(height/ratio))


class PointLibrary:
    def __init__(self, path=None):
        self.path = Path(path or ROOT/'configs/map-points.json')

    @staticmethod
    def parse(data):
        if isinstance(data, dict): data = data.get('points')
        if not isinstance(data, list) or len(data) > 50000: raise RouteError('点位文件需要最多 50000 项的 points 列表')
        result, identities = [], set()
        for row in data:
            if not isinstance(row, dict): raise RouteError('点位必须是对象')
            identity = str(row.get('id') or uuid.uuid4().hex)
            if identity in identities: raise RouteError('文件包含重复点位 ID')
            identities.add(identity)
            map_name = row.get('map_name', row.get('map', 'miraland'))
            if map_name not in OFFSETS: raise RouteError(f'不支持的点位地图：{map_name}')
            if row.get('image_x') is not None and row.get('image_y') is not None:
                x, y = number(row['image_x']), number(row['image_y'])
            elif row.get('game_x') is not None and row.get('game_y') is not None:
                x, y = game_to_map((row['game_x'], row['game_y']), map_name)
            else: raise RouteError('点位需要 image_x/image_y 或 game_x/game_y 坐标')
            name = str(row.get('name') or '未命名点位')[:120]
            label = str(row.get('label_id') or '资源点')[:80]
            result.append(MaskPoint(identity, name, label, map_name, x, y))
        return result

    def points(self):
        if not self.path.exists(): return []
        return self.parse(json.loads(self.path.read_text(encoding='utf-8')))

    def import_data(self, data):
        incoming = self.parse(data)
        current = self.points()
        by_id = {point.id: point for point in current}
        imported = 0
        for point in incoming:
            old = by_id.get(point.id)
            if old == point: continue
            if old is not None: raise RouteError(f'点位 ID 已存在且内容不同：{point.id}；未覆盖原有数据')
            by_id[point.id] = point
            imported += 1
        if len(by_id) > 50000: raise RouteError('点位总数超过 50000')
        rows = [{'id': p.id, 'name': p.name, 'label_id': p.label, 'map_name': p.map_name,
                 'image_x': p.x, 'image_y': p.y} for p in by_id.values()]
        payload = json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name+'.tmp')
        try:
            temporary.write_text(payload, encoding='utf-8')
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return imported


def builtin_points(route_name=''):
    checkpoints = json.loads((ROOT/'assets/maps/checkpoints.json').read_text(encoding='utf-8'))
    points = []
    for map_name, rows in checkpoints.items():
        if map_name not in OFFSETS: continue
        for index, row in enumerate(rows):
            x, y = game_to_map(row['position'], map_name)
            points.append(MaskPoint(f'checkpoint:{map_name}:{index}', row.get('name') or row.get('region') or '流转之柱',
                                    'teleport', map_name, x, y))
    if route_name:
        route = RouteCatalog().get(route_name)
        for index, point in enumerate(route.points):
            x, y = game_to_map(point.position, route.map_name)
            points.append(MaskPoint(f'route:{route.name}:{point.id}', f'{index+1} · {point.action or "途经点"}',
                                    'route', route.map_name, x, y, index, point.action or ''))
    return points


def filtered_points(points, settings):
    for point in points:
        if point.label == 'teleport' and not settings.get('显示流转之柱', True): continue
        if point.label == 'route' and not settings.get('显示路线点位', True): continue
        if point.label not in {'teleport', 'route'}:
            if not settings.get('显示导入点位', True): continue
            label = settings.get('资源类型', '全部')
            if label != '全部' and point.label != label: continue
        yield point


class MapMaskEngine:
    def __init__(self, locator=None):
        self.locator = locator or MapLocator()
        self.map_name = None
        self.position = None
        self.thumbnail = None

    def observe(self, frame, has_feature, map_name='自动识别'):
        if frame is None or frame.ndim != 3 or frame.mean() < 2:
            return Observation(None, '尚未取得有效游戏画面')
        if has_feature('IconUIBigmap') or has_feature('IconUIBigmapJoystick'):
            if not (has_feature('IconBigMapMaxScale') or has_feature('IconBigMapMaxScaleJoyStick')):
                self.thumbnail = None
                self.position = None
                return Observation(None, '请用地图缩放按钮切换到最大档位')
            reference = MapLocator.reference(frame)
            thumbnail = cv2.resize(cv2.cvtColor(reference[156:924, 320:1600], cv2.COLOR_BGR2GRAY), (160, 96))
            old, self.thumbnail = self.thumbnail, thumbnail
            if old is None or np.mean(cv2.absdiff(old, thumbnail)) > 6:
                return Observation(None, '地图移动中，画面稳定后显示点位')
            candidates = [map_name] if map_name in OFFSETS else ([self.map_name] if self.map_name else [])
            candidates += [name for name in OFFSETS if name not in candidates] if map_name not in OFFSETS else []
            matches = []
            for candidate in candidates:
                try:
                    center = self.locator.bigmap(frame, candidate)
                    confidence = self.locator.last_observation.get('confidence', 0)
                    matches.append((confidence, candidate, center))
                    if candidate == self.map_name and confidence > .65: break
                except RouteError: continue
            matches.sort(reverse=True, key=lambda row: row[0])
            if not matches or (len(matches) > 1 and matches[0][0]-matches[1][0] < .04):
                return Observation(None, '地图定位不可靠，已隐藏；可手动选择地图重试')
            confidence, chosen, center = matches[0]
            self.map_name, self.position = chosen, center
            return Observation(Viewport(chosen, 'bigmap', center, BIGMAP_SCALES[chosen], (320, 156, 1280, 768)),
                               f'{MAP_NAMES[chosen]} · 大地图点位', confidence)
        self.thumbnail = None
        if has_feature('IconPageMainFeature'):
            if self.position is None or (map_name in OFFSETS and map_name != self.map_name):
                return Observation(None, '首次使用小地图遮罩，请先打开大地图并对准角色附近')
            try:
                position = self.locator.minimap(frame, self.map_name, self.position)
                if math.dist(position, self.position) > 180:
                    raise RouteError('小地图位置变化过大')
                self.position = position
                return Observation(Viewport(self.map_name, 'minimap', position, MINIMAP_SCALES[self.map_name], (81, 22, 200, 200)),
                                   f'{MAP_NAMES[self.map_name]} · 小地图点位', self.locator.last_observation.get('confidence', 0))
            except RouteError:
                self.position = None
                return Observation(None, '小地图定位失败，已隐藏；请打开大地图重新定位')
        return Observation(None, '当前页面不显示地图遮罩')
