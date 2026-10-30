"""Original NPC minigame flow with bounded retry and explicit fee setting."""
from nuannuan.routes import RouteError, validate_macro
from nuannuan.extra_daily import EXTRA_DEFAULTS


class MinigameRunner:
    def __init__(self, port):
        self.port = port

    def require(self, value, message):
        if not value:
            raise RouteError(message)

    def skip_dialogue(self):
        for _ in range(25):
            if not self.port.exists('IconSkipDialog'):
                return
            self.port.key(self.port.settings.get('交互', 'f'))
        raise RouteError('小游戏对话跳过超时')

    def run(self, macro):
        validate_macro(macro)
        options = {**EXTRA_DEFAULTS, **getattr(self.port, 'extra_options', {})}
        self.require(options['允许小游戏支付噗灵'], '小游戏需要支付噗灵，请在扩展功能设置中开启')
        retries = options['小游戏最多重试']
        self.require(type(retries) is int and 0 <= retries <= 3, '小游戏重试次数需为 0 至 3')
        self.port.key(self.port.settings.get('交互', 'f'))
        self.require(self.port.wait('IconSkipDialog'), '未进入小游戏 NPC 对话')
        self.skip_dialogue()
        self.require(self.port.click_text('开始游戏', 'AreaDialogSelection'), '未找到开始游戏选项')
        self.skip_dialogue()
        self.require(self.port.click_text('没问题', 'AreaDialogSelection'), '未找到小游戏支付噗灵选项')
        self.skip_dialogue()
        for attempt in range(retries + 1):
            self.require(self.port.wait('IconPageMainFeature', timeout=15), '未进入小游戏操作阶段')
            self.port.execute_macro(macro)
            self.port.sleep(1)
            if self.port.exists('IconSkipDialog'):
                self.skip_dialogue()
                self.require(self.port.wait('reward_popup'), '小游戏结束但未确认奖励')
                self.port.evidence('minigame_reward')
                self.port.key(self.port.settings.get('交互', 'f'))
                self.skip_dialogue()
                self.port.click_text('谢谢你', 'AreaDialogSelection')
                self.skip_dialogue()
                self.require(self.port.wait('IconPageMainFeature'), '小游戏结束后未返回主界面')
                return {'status': 'succeeded', 'message': '已确认小游戏奖励'}
            if attempt == retries:
                if self.port.exists('ButtonMinigameQuit'):
                    self.port.click_feature('ButtonMinigameQuit')
                raise RouteError('小游戏未确认成功，达到重试上限')
            if self.port.exists('ButtonMinigameRetry'):
                self.port.click_feature('ButtonMinigameRetry')
            else:
                self.port.key('esc')
                self.require(self.port.click_text('重试', 'AreaMinigameEscSelect'), '未找到小游戏重试')
            self.require(self.port.wait('ButtonMinigameRetryOk'), '未找到重试确认')
            self.port.click_feature('ButtonMinigameRetryOk')
