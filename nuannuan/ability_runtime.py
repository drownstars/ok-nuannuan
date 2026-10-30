"""Visual wheel/HUD recognition and ok-script ability-page interaction."""
import cv2

from nuannuan.ability import ABILITY_ICONS, JUMP_ICONS
from nuannuan.config import ROOT
from nuannuan.daily import AutomationError, DailyRunner
from nuannuan.routes import RouteError

SLOT_CENTERS = [(1063, 257), (1205, 433), (1199, 640), (1048, 829),
                (641, 829), (498, 640), (485, 433), (610, 257)]
JUMP_CENTER = (227, 634)


def glyph(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (0, 0, 230), (179, 60, 255))


class AbilityVision:
    def __init__(self, root=None):
        self.root = root or ROOT / 'assets/ability_icons'
        self.icons = {}

    def icon(self, name):
        if name not in self.icons:
            image = cv2.imread(str(self.root / f'{name}.png'))
            if image is None:
                raise RouteError(f'能力识别图标缺失：{name}')
            self.icons[name] = glyph(image)
        return self.icons[name]

    def identify(self, image, candidates, scale=1.):
        if image.size == 0:
            return None
        mask = glyph(image)
        scores = []
        for label, name in candidates.items():
            template = self.icon(name)
            if scale != 1:
                template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if mask.shape[0] < template.shape[0] or mask.shape[1] < template.shape[1]:
                continue
            score = cv2.minMaxLoc(cv2.matchTemplate(mask, template, cv2.TM_CCOEFF_NORMED))[1]
            scores.append((score, label))
        scores.sort(reverse=True)
        if scores and scores[0][0] >= .82 and (len(scores) == 1 or scores[0][0] - scores[1][0] > .025):
            return scores[0][1]
        return None

    @staticmethod
    def reference(frame):
        return cv2.resize(frame, (1920, 1080)) if frame.shape[:2] != (1080, 1920) else frame

    def at(self, frame, center, candidates):
        frame = self.reference(frame)
        x, y = center
        return self.identify(frame[y-50:y+50, x-50:x+50], candidates)


class AbilityRuntime:
    def __init__(self, port):
        self.port = port
        self.vision = AbilityVision()

    def recover_home(self):
        DailyRunner(self.port).recover_home()

    def open_ability_page(self):
        from nuannuan.page_navigation import open_confirmed_page
        def open_page():
            self.port.key(self.port.settings.get('换装', 'c'))
            if not self.port.wait('IconWardrobeFeature'):
                raise RouteError('未进入换装界面')
            self.port.key(self.port.settings.get('能力配置', 'e'))
        try:
            open_confirmed_page(self.port, '能力配置', 'IconAbilityFeature', open_page)
        except AutomationError as error:
            raise RouteError(str(error)) from error

    def choose_ability_plan(self, value):
        self.port.click_region('AreaAbilityPlanChangeButton')
        self.port.click_region(f'AreaAbilityPlan{value}Button')
        self.port.sleep(.4)
        if not self.port.wait('IconAbilityFeature'):
            raise RouteError('切换能力方案后未确认能力页面')
        title = ''.join(self.port.text('AreaAbilityPlanChangeButton').split())
        numeral = {1: '一', 2: '二', 3: '三'}[value]
        if f'方案{value}' not in title and f'方案{numeral}' not in title:
            raise RouteError(f'未确认选择的能力方案 {value}：{title or "未识别"}')

    def read_ability_slots(self):
        frame = self.port.fresh()
        if not self.port.match('IconAbilityFeature', frame):
            raise RouteError('当前不是能力配置界面，不能读取能力轮盘')
        return {slot: name for slot, center in enumerate(SLOT_CENTERS, 1)
                if (name := self.vision.at(frame, center, ABILITY_ICONS)) is not None}

    def read_jump_ability(self):
        return self.vision.at(self.port.fresh(), JUMP_CENTER, JUMP_ICONS)

    def set_ability_slot(self, slot, name):
        center = JUMP_CENTER if slot == 'jump' else SLOT_CENTERS[slot - 1]
        self.port.click_reference(*center)
        if name not in self.port.text('AreaAbilityChange') and self.port.exists('ButtonAbilityChangeList'):
            self.port.click_feature('ButtonAbilityChangeList')
        if not self.port.click_text(name, 'AreaAbilityChange', scroll=True):
            raise RouteError(f'能力选择列表中未找到“{name}”，请确认已解锁')
        self.port.sleep(.3)

    def save_abilities(self):
        if not self.port.wait('ButtonAbilitySave'):
            raise RouteError('未找到能力保存按钮')
        self.port.click_feature('ButtonAbilitySave')
        self.port.sleep(.5)
        self.port.evidence('abilities_saved')

    def activate_ability(self, slot, name):
        self.port.key(str(slot))
        def active():
            frame = self.port.fresh()
            box = self.port.region('AreaAbilityButton', frame)
            crop = frame[box.y:box.y + box.height, box.x:box.x + box.width]
            scale = .73 * frame.shape[0] / 1080
            return self.vision.identify(crop, {name: ABILITY_ICONS[name]}, scale) == name
        if not self.port.task.wait_until(active, time_out=5, settle_time=.2):
            raise RouteError(f'切换后未在主界面确认能力“{name}”')
