"""Additional opt-in background helpers using the shared framework executor."""
import time

from ok import TriggerTask
from nuannuan.config import KEYS_NAME, ROUTE_OPTIONS_NAME, ROOT
from nuannuan.extra_daily import EXTRA_SETTINGS
from nuannuan.daily import AutomationError
from nuannuan.runtime import RuntimePort


class ExtraAssistTask(TriggerTask):
    mode = ''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trigger_interval = .2
        self.global_config_names = [KEYS_NAME, ROUTE_OPTIONS_NAME, EXTRA_SETTINGS]
        self.default_config = {'操作间隔（秒）': 12.}
        self._last = 0
        self._stable = 0

    def port(self):
        port = RuntimePort(self, ROOT/'logs/assist', dict(self.get_global_config(KEYS_NAME)))
        port.route_options = dict(self.get_global_config(ROUTE_OPTIONS_NAME))
        port.extra_options = dict(self.get_global_config(EXTRA_SETTINGS))
        return port

    def validate_config(self, key, value):
        if key == '操作间隔（秒）':
            import math
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 120:
                return '请输入 1 至 120 秒'

    def trigger(self):
        from nuannuan.run_control import assist_allowed
        if not assist_allowed(self.executor): return False
        if time.monotonic() - self._last < self.config['操作间隔（秒）']:
            return False
        port = self.port()
        try:
            if self.mode == 'fish':
                ready = port.fishing_state() in {'wait', 'strike', 'pull', 'reel'}
            elif self.mode == 'clean':
                ready = port.exists('IconSkip') and port.ability_icon('IconAbilityAnimal')
            else:
                icon = 'IconAbilityFlourish' if self.mode == 'flourish' else 'IconAbilityInsect'
                ready = port.exists('IconPageMainFeature') and port.ability_icon(icon)
            self._stable = self._stable + 1 if ready else 0
            return self._stable >= 2
        except AutomationError:
            self._stable = 0
            return False

    def run(self):
        from nuannuan.run_control import assist_allowed
        if not assist_allowed(self.executor): return
        backend = self.executor.interaction
        if hasattr(backend, 'resume_helpers'): backend.resume_helpers()
        port = self.port()
        try:
            if self.mode == 'fish':
                from nuannuan.gathering import FishingRunner
                result = FishingRunner(port).run(casts=1, home=port.exists('IconFishingHomeFeature'), already_cast=True)
                self.info_set('辅助结果', result['message'])
            elif self.mode == 'clean':
                if port.exists('IconSkip') and port.ability_icon('IconAbilityAnimal'):
                    port.key(port.settings.get('交互', 'f'))
                    self.info_add('清洁动画跳过次数')
            else:
                from nuannuan.gathering import ability_action
                result = ability_action(port, '芳间巡游' if self.mode == 'flourish' else '花套捕虫')
                self.info_set('辅助结果', result['message'])
        except AutomationError:
            control = getattr(self.executor, '_nuannuan_run_control', None)
            if control is None or not control.busy: raise
        finally:
            port.release_inputs()
            self._last = time.monotonic()
            self._stable = 0

    def disable(self):
        self._stable = 0
        super().disable()


class AutoFishingTask(ExtraAssistTask):
    mode = 'fish'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '自动钓鱼辅助'
        self.description = '手动抛竿后，连续确认钓鱼界面再接管当前一竿；不会自动移动找鱼。'


class AutoCleanTask(ExtraAssistTask):
    mode = 'clean'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '清洁动画跳过'
        self.description = '确认动物清洁能力和跳过标识后跳过动画，不选择对话。'


class AutoFlourishTask(ExtraAssistTask):
    mode = 'flourish'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '芳间巡游辅助'
        self.description = '已选中芳间巡游能力时，按间隔使用；开启后会自动操作右键和衍生技能。'


class AutoFloralTask(ExtraAssistTask):
    mode = 'floral'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '花套捕虫辅助'
        self.description = '已选中捕虫能力时，按间隔使用右键；停止或关闭开关即可结束。'
