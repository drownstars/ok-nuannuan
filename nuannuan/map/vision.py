"""Visual map matching using the supplied map scales and coordinate system."""
from pathlib import Path

import cv2
import numpy as np

from nuannuan.config import ROOT
from nuannuan.routes.model import RouteError

PREFIXES = {'miraland': 'w01_v12', 'starsea': 'w14000000_v2', 'home': 'w8000001_v1', 'wanxiang': 'w4020034'}
MINIMAP_SCALES = {'miraland': 0.975, 'starsea': 0.8, 'home': 0.8, 'wanxiang': 0.8}
BIGMAP_SCALES = {'miraland': 0.637, 'starsea': 0.62, 'home': 0.61, 'wanxiang': 0.621}


class MapLocator:
    def __init__(self, root=None, *, images=None):
        self.root = Path(root or ROOT / 'assets/maps')
        self.images = images
        self._loaded = {}
        self.last_observation = {}

    def atlas(self, map_name, scale):
        if map_name not in PREFIXES:
            raise RouteError(f'没有该地图的视觉素材：{map_name}')
        if self.images is not None:
            return self.images[map_name][scale]
        key = map_name, scale
        if key not in self._loaded:
            path = self.root / f'{PREFIXES[map_name]}_luma_{scale}.png'
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise RouteError(f'地图素材无法读取：{path}')
            # Never hold every large world map in memory at once.
            self._loaded.clear()
            self._loaded[key] = image
        return self._loaded[key]

    @staticmethod
    def reference(frame):
        if frame is None or frame.ndim != 3:
            raise RouteError('没有可用的地图截图')
        height, width = frame.shape[:2]
        if abs(width / height - 16 / 9) > 0.02:
            raise RouteError('地图定位需要 16:9 游戏画面')
        return cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_NEAREST) if (width, height) != (1920, 1080) else frame

    @staticmethod
    def luma(frame):
        # Match the supplied Whimbox maps' original RGB2YUV convention.
        return cv2.cvtColor(frame, cv2.COLOR_RGB2YUV)[:, :, 0]

    def _match(self, search, template, *, mask=None, minimum=0.35):
        if (template.size == 0 or search.size == 0 or template.std() < 2
                or search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]):
            raise RouteError('地图特征不足或搜索区域无效，已停止定位')
        result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED, mask=mask)
        np.nan_to_num(result, copy=False, nan=-1, posinf=-1, neginf=-1)
        _, confidence, _, location = cv2.minMaxLoc(result)
        contrast = result - cv2.GaussianBlur(result, (9, 9), 0)
        strength = float(contrast[location[1], location[0]])
        if confidence < minimum or strength < 0.005:
            raise RouteError(f'地图定位置信度不足（{confidence:.3f} / {strength:.3f}），已停止')
        self.last_observation = {'confidence': confidence, 'local_contrast': strength}
        return location

    def minimap(self, frame, map_name, hint):
        if hint is None or len(hint) != 2 or not np.isfinite(hint).all():
            raise RouteError('缺少可信的小地图初始位置，请从路线传送点开始')
        reference = self.reference(frame)
        image = self.luma(reference[22:222, 81:281])
        scale = MINIMAP_SCALES[map_name] * 0.5
        template = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        yy, xx = np.ogrid[:200, :200]
        radius = np.hypot(xx - 100, yy - 100)
        mask = ((radius < 96) & (radius > 16)).astype(np.uint8) * 255
        mask = cv2.resize(mask, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_NEAREST)
        atlas = self.atlas(map_name, '05x')
        center_x, center_y = np.array(hint) * 0.5
        margin = 110
        left, top = max(0, int(center_x - margin)), max(0, int(center_y - margin))
        right, bottom = min(atlas.shape[1], int(center_x + margin)), min(atlas.shape[0], int(center_y + margin))
        location = self._match(atlas[top:bottom, left:right], template, mask=mask)
        position = ((location[0] + left + template.shape[1] / 2) * 2,
                    (location[1] + top + template.shape[0] / 2) * 2)
        self.last_observation['position'] = list(position)
        return position

    def bigmap(self, frame, map_name):
        reference = self.reference(frame)
        # The central map rectangle avoids page title, region selector, and zoom controls.
        crop = self.luma(reference[156:924, 320:1600])
        scale = BIGMAP_SCALES[map_name] * 0.125
        template = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        location = self._match(self.atlas(map_name, '0125x'), template)
        position = ((location[0] + template.shape[1] / 2) / 0.125,
                    (location[1] + template.shape[0] / 2) / 0.125)
        self.last_observation['position'] = list(position)
        return position
