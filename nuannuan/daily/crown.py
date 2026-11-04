"""Mira Crown recommended-outfit challenge and bounded reward collection."""
from nuannuan.daily.runner import DailyRunner
from nuannuan.core.text import count_option, require, read_fraction


class CrownRunner:
    def __init__(self, port, options):
        self.port, self.options = port, options

    def enter(self):
        self.port.goto_page('美鸭梨')
        require(self.port.click_text('奇迹之冠', 'AreaEscEntrances', scroll=True), '未找到奇迹之冠')
        self.port.sleep(1)
        self.port.click_region('AreaMiraCrownEntrance')
        self.port.sleep(1)
        if self.port.wait('ButtonMiraCrownRank', timeout=1):
            self.port.click_feature('ButtonMiraCrownRank')

    def claim(self):
        require(self.port.wait('reward_popup', timeout=20), '未确认奇迹之冠奖励')
        self.port.evidence('crown_reward')
        self.port.key(self.port.settings.get('交互', 'f'))

    def skip_dialogue(self):
        for _ in range(30):
            if not self.port.exists('IconSkipDialog'): return
            self.port.key(self.port.settings.get('交互', 'f'))
        require(False, '奇迹之冠对话超时')

    def run(self, *, only_unstarted=False):
        limit = count_option(self.options['奇迹之冠最多挑战'], '最多挑战次数', 30)
        self.port.goto_page('奇想日历')
        before, total = read_fraction(self.port.text('AreaMiraCrownOverview'))
        if only_unstarted and before > 0:
            return {'status': 'skipped', 'progress': {'current': before, 'total': total},
                    'message': f'运行前复查奇迹之冠已有进度 {before}/{total}，跳过挑战、领奖和兑换'}
        if before >= total:
            if self.options['领取巅峰赛奖励']:
                self.rewards()
            return {'status': 'skipped', 'message': f'巅峰赛进度已完成 {before}/{total}'}
        self.enter()
        quick = self.port.wait('ButtonMiraCrownQuickReward', timeout=2)
        if quick:
            self.port.click_feature('ButtonMiraCrownQuickReward')
            self.claim()
        self.port.click_region('AreaMiraCrownSecondDoor' if quick else 'AreaMiraCrownThirdDoor')
        if not self.port.wait('ButtonMiraCrownStartChallenge'):
            require(False, '未找到巅峰赛开始挑战按钮，请检查解锁状态')
        self.port.click_feature('ButtonMiraCrownStartChallenge')
        require(self.port.wait('IconPageMainFeature', timeout=25), '未进入巅峰赛内部')
        self.port.approach_interaction(None, 'AreaPickup')
        for _ in range(limit):
            self.skip_dialogue()
            if not (self.port.click_text('继续挑战', 'AreaDialogSelection')
                    or self.port.click_text('开始挑战', 'AreaDialogSelection')):
                break
            self.skip_dialogue()
            require(self.port.wait('ButtonMiraCrownNextStep', timeout=15), '未进入搭配阶段')
            require(self.port.click_text('推荐搭配', 'AreaMiraCrownAutoMatchButton'), '未找到推荐搭配')
            self.port.sleep(5)
            self.port.click_feature('ButtonMiraCrownNextStep')
            require(self.port.wait('ButtonMiraCrownConfirmMatch'), '未出现确认搭配')
            self.port.click_feature('ButtonMiraCrownConfirmMatch')
            seen_result = False
            for _ in range(35):
                if self.port.exists('ButtonMiraCrownSkipAll'):
                    self.port.click_feature('ButtonMiraCrownSkipAll')
                if self.port.exists('reward_popup'):
                    self.claim()
                    seen_result = True
                    break
                self.port.sleep(1)
            require(seen_result, '巅峰赛挑战后未出现可确认结果')
            if self.port.exists('IconPageMainFeature'): break
        DailyRunner(self.port).recover_home()
        self.port.goto_page('奇想日历')
        after, _ = read_fraction(self.port.text('AreaMiraCrownOverview'))
        require(after > before, '挑战后巅峰赛进度未增加，未计入成功')
        if self.options['领取巅峰赛奖励']:
            self.rewards()
        return {'status': 'succeeded' if after >= total else 'partial',
                'message': f'巅峰赛进度复核 {before} → {after}/{total}；本次最多挑战 {limit} 次'}

    def rewards(self):
        self.enter()
        require(self.port.wait('ButtonMiraCrownAward'), '未找到赛事嘉奖')
        self.port.click_feature('ButtonMiraCrownAward')
        if self.port.wait('ButtonMiraCrownRewardGet', timeout=2):
            self.port.click_feature('ButtonMiraCrownRewardGet')
            self.claim()
        self.port.key('esc')
        targets = [t.strip() for t in self.options.get('巅峰赛兑换物品', '').replace('，', ',').split(',') if t.strip()]
        require(len(targets) <= 6, '兑换物品最多 6 项')
        if not targets: return
        require(self.port.wait('ButtonMiraCrownShop'), '未找到晶石兑换')
        self.port.click_feature('ButtonMiraCrownShop')
        for target in targets:
            require(self.port.click_text(target, 'AreaMiraCrownShopItemList', scroll=True), f'未找到兑换物品：{target}')
            require(self.port.confirm_single_quantity(), '未确认兑换数量为 1，不兑换')
            require(self.port.wait('ButtonMiraCrownShopConfirm'), '未找到兑换确认')
            self.port.click_feature('ButtonMiraCrownShopConfirm')
            self.claim()
