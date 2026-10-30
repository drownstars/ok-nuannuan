"""Bounded fishing, star fishing and nearby ability actions."""
import re
import time

from nuannuan.daily import AutomationError
from nuannuan.extra_daily import count_option, require

FISHING_FEATURES = [('IconFishingNoFish', 'empty'), ('IconFishingStrike', 'strike'),
                    ('IconFishingPullLine', 'pull'), ('IconFishingPullLineHome', 'pull'),
                    ('IconFishingReelIn', 'reel'), ('IconFishingFinish', 'wait'),
                    ('IconFishingSkip', 'result'), ('IconSkip', 'result')]


class FishingRunner:
    def __init__(self, port):
        self.port = port

    def run(self, casts=3, home=False, already_cast=False):
        casts = count_option(casts, '抛竿次数', 20)
        caught, materials = 0, []
        star_active = False
        try:
            if not already_cast:
                self.port.select_ability('采星' if home else '钓鱼')
                if home:
                    self.port.mouse_right()
                    star_active = True
                    self.port.sleep(2)
            for cast in range(casts):
                if not (already_cast and cast == 0):
                    if home: self.port.key(self.port.settings.get('能力衍生', 'r'))
                    else: self.port.mouse_right()
                unknown, strike_count, result_seen = 0, 0, False
                deadline = time.monotonic() + 90
                for _ in range(450):
                    require(time.monotonic() < deadline, '钓鱼超时，已释放输入')
                    state = self.port.fishing_state()
                    if state == 'empty':
                        if not self.port.exists('IconPageMainFeature'):
                            if home: self.port.key(self.port.settings.get('能力衍生', 'r'))
                            else: self.port.mouse_right()
                            require(self.port.wait('IconPageMainFeature'), '无鱼后未能退出钓鱼状态')
                        return self.result(caught, materials, '附近已无可钓目标')
                    if state == 'unknown':
                        unknown += 1
                        require(unknown < 12, '钓鱼状态无法识别，已停止')
                    else:
                        unknown = 0
                    if state == 'strike':
                        strike_count += 1
                        require(strike_count <= 4, '连续提竿未出现结果，已停止')
                        self.port.key(self.port.settings.get('后退', 's'))
                    elif state == 'pull': self.port.fishing_pull()
                    elif state == 'reel': self.port.mouse_right()
                    elif state == 'result':
                        self.port.evidence('fishing_result')
                        self.port.key(self.port.settings.get('交互', 'f'))
                        require(self.port.wait('IconPageMainFeature', timeout=10), '钓鱼结果后未返回主界面')
                        self.port.sleep(.5)
                        text = self.port.text('AreaMaterialGetText')
                        if home:
                            require('陨星' in text or '星' in text, '未识别到采星获得文本，未计入成功')
                        else:
                            require(re.search(r'[×xX]\s*\d+(?:\.\d+)?\s*kg', text, re.I), '未识别到钓鱼获得文本，未计入成功')
                        materials.append(text)
                        caught += 1
                        result_seen = True
                        break
                    self.port.sleep(0.2)
                require(result_seen, '等待钓鱼结果超时')
            return self.result(caught, materials)
        finally:
            # No pause-aware wait before releasing held input.
            self.port.release_inputs()
            if star_active:
                # Only toggle off while still on the expected HUD; cancellation must not send another input.
                try:
                    executor = self.port.task.executor
                    if not executor.paused and not self.port.task.paused and self.port.exists('IconPageMainFeature'):
                        self.port.mouse_right()
                except (AttributeError, AutomationError):
                    pass

    @staticmethod
    def result(caught, materials, suffix=''):
        return {'status': 'succeeded' if caught else 'skipped', 'caught': caught, 'materials': materials,
                'message': f'已确认 {caught} 次获得结果' + (f'；{suffix}' if suffix else '')}


def ability_action(port, action):
    abilities = {'清洁动物': '动物清洁', '花套捕虫': '捕虫', '芳间巡游': '芳间巡游',
                 '变大': '变大', '变小': '变小', '开启化万相': '化万相',
                 '械控注入': '械控', '械控抽取': '械控', '万物交响': '万物交响'}
    require(action in abilities, '未知能力动作')
    port.select_ability(abilities[action])
    if action == '开启化万相':
        before = port.subability_active()
        if not before:
            port.key(port.settings.get('大世界能力衍生', 'g'))
            port.sleep(1)
        require(port.subability_active(), '未确认化万相衍生能力已启用')
    elif action in {'械控注入', '械控抽取'}:
        desired = 'IconAbilityMachineInfuse' if action == '械控注入' else 'IconAbilityMachineExtract'
        if not port.ability_icon(desired):
            port.key(port.settings.get('大世界能力衍生', 'g'))
            port.sleep(0.8)
        require(port.ability_icon(desired), '未确认械控模式')
        port.mouse_right()
    else:
        port.mouse_right()
        if action == '芳间巡游':
            port.sleep(4)
            port.key(port.settings.get('大世界能力衍生', 'g'))
            port.sleep(5)
            port.mouse_right()
        elif action == '清洁动物':
            require(port.wait('IconSkip', timeout=10), '附近未出现动物清洁动画')
            port.key(port.settings.get('交互', 'f'))
            require(port.wait('IconPageMainFeature', timeout=12), '清洁后未返回大世界')
            require(bool(port.text('AreaMaterialGetText')), '清洁后未确认获得材料')
    port.evidence('ability_action')
    return {'status': 'succeeded', 'message': f'已执行{action}；采集数量以获得文本和心愿复核为准'}
