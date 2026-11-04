"""ok-script adapters shared by additional task implementations."""
import json
import re
from types import SimpleNamespace

import cv2
import numpy as np

from nuannuan.config import ROOT
from nuannuan.core.text import require


class ExtraRuntimeMixin:
    def page_visible(self, page):
        from nuannuan.daily.game_tools import GameTools
        return GameTools(self).visible(page)

    def goto_page(self, page):
        from nuannuan.daily.game_tools import GameTools
        GameTools(self).goto(page)

    def execute_route(self, name):
        from nuannuan.tasks.daily_tasks import execute_route
        return execute_route(self, name)

    def validate_route(self, route):
        from nuannuan.routes.runtime import RouteRuntime
        RouteRuntime(self, allow_chat=self.allow_chat).preflight(route)

    def execute_macro(self, record):
        from nuannuan.routes.runtime import RouteRuntime
        from nuannuan.routes.model import validate_macro
        validate_macro(record)
        self.fresh()
        RouteRuntime(self).macro(record)

    def select_ability(self, name):
        from nuannuan.routes.ability import AbilityManager, ABILITY_DEFAULTS
        from nuannuan.routes.ability_runtime import AbilityRuntime
        manager = getattr(self, '_ability_manager', None)
        if manager is not None and name in manager.slots:
            manager.port.activate_ability(manager.slots[name], name)
            return
        manager = AbilityManager(AbilityRuntime(self))
        route = SimpleNamespace(abilities=(name,), points=[], active_ability=name, jump_ability='自动')
        manager.prepare(route, {**ABILITY_DEFAULTS, **getattr(self, 'route_options', {})})
        self._ability_manager = manager

    def ability_icon(self, name):
        from nuannuan.routes.ability_runtime import AbilityVision
        frame = self.fresh()
        box = self.region('AreaAbilityButton', frame)
        crop = frame[box.y:box.y+box.height, box.x:box.x+box.width]
        return AbilityVision().identify(crop, {name: name}, .73*frame.shape[0]/1080) == name

    def subability_active(self):
        samples = []
        for _ in range(3):
            frame = self.fresh()
            box = self.region('AreaSubAbilityButton', frame)
            crop = frame[box.y:box.y+box.height, box.x:box.x+box.width]
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([0, 80, 200]), np.array([30, 110, 255]))
            samples.append(np.count_nonzero(mask) / (frame.shape[0]/1080)**2)
            self.sleep(.1)
        return sum(samples)/len(samples) > 200

    def mouse_right(self):
        self.fresh()
        self.task.click_relative(.5, .5, key='right', after_sleep=.18)

    def input_runtime(self):
        from nuannuan.routes.runtime import RouteRuntime
        if not hasattr(self, '_input_runtime'):
            self._input_runtime = RouteRuntime(self)
        return self._input_runtime

    def release_inputs(self):
        if hasattr(self, '_input_runtime'):
            self._input_runtime.release_all()

    def fishing_state(self):
        from nuannuan.daily.gathering import FISHING_FEATURES
        frame = self.fresh()
        for feature, state in FISHING_FEATURES:
            if self.match(feature, frame): return state
        return 'unknown'

    def fishing_pull(self):
        def pixels():
            frame = self.fresh()
            box = self.region('AreaFishingDetection', frame)
            roi = frame[box.y:box.y+box.height, box.x:box.x+box.width]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            return np.count_nonzero(cv2.inRange(hsv, np.array([20, 50, 245]), np.array([30, 90, 255])))
        before = pixels()
        direction = getattr(self, '_fish_direction', 'a')
        key = self.settings.get('向左' if direction == 'a' else '向右', direction)
        require(self.input_runtime().hold(key, .2), '钓鱼拉线因暂停中断')
        after = pixels()
        if after >= before - 5:
            self._fish_direction = 'd' if direction == 'a' else 'a'

    def approach_interaction(self, text=None, region='AreaPickup'):
        for attempt in range(4):
            if (self.text_contains(text, region) if text else self.exists('IconTalkFeature')):
                self.key(self.settings.get('交互', 'f'))
                return
            if attempt < 3:
                runtime = self.input_runtime()
                require(self.exists('IconPageMainFeature'), '靠近交互前未在大世界')
                require(runtime.hold(self.settings.get('前进', 'w'), .8), '靠近交互已中断')
        require(False, f'附近未出现交互：{text or "对话"}')

    def click_exact_text(self, text, region, scroll=False):
        for attempt in range(7 if scroll else 1):
            frame = self.fresh()
            box = self.region(region, frame)
            matches = [item for item in self.task.ocr(box=box, frame=frame, threshold=.8)
                       if re.sub(r'\s+', '', item.name) == re.sub(r'\s+', '', text)]
            require(len(matches) <= 1, '识别到多个同名目标，未执行选择')
            if matches:
                self.task.click_box(matches[0], after_sleep=.5)
                return True
            if scroll:
                self.task.scroll(box.x+box.width//2, box.y+box.height//2, -3)
                self.sleep(.3)
        return False

    def confirm_single_quantity(self):
        text = self.text('AreaDialog')
        match = re.search(r'(?:数量|次数|兑换份数)\s*[:：]?\s*(\d+)', text)
        return bool(match and int(match[1]) == 1)

    def select_material(self, name):
        manifest = json.loads((ROOT/'assets/materials.json').read_text(encoding='utf-8'))
        info = manifest.get(name)
        require(info is not None and info['jihua'], '该材料不支持激化')
        image = cv2.imdecode(np.frombuffer((ROOT/info['local_icon']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        require(image is not None, '材料图标无法读取')
        for attempt in range(15):
            frame = self.fresh()
            box = self.region('AreaJihuaCostSelect', frame)
            roi = frame[box.y:box.y+box.height, box.x:box.x+box.width]
            template = cv2.resize(image, None, fx=.5*frame.shape[0]/1080, fy=.5*frame.shape[0]/1080)
            if roi.shape[0] >= template.shape[0] and roi.shape[1] >= template.shape[1]:
                result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
                _, confidence, _, point = cv2.minMaxLoc(result)
                if confidence >= .8:
                    self.task.click(box.x+point[0]+template.shape[1]//2,
                                    box.y+point[1]+template.shape[0]//2, after_sleep=.5)
                    return True
            self.task.scroll(box.x+box.width//2, box.y+box.height//2, 12 if attempt == 0 else -4)
            self.sleep(.3)
        return False
