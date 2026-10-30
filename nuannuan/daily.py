"""Bounded, observable daily workflows, independent of the GUI and game runtime."""


class AutomationError(RuntimeError):
    """A known game state could not be observed within the allowed time."""


class DailyRunner:
    LABELS = {'photo': '每日拍照', 'dig': '美鸭梨挖掘', 'auto_wish': '自动朝夕心愿', 'starsea': '星海拾光',
              'wish': '朝夕心愿已有奖励', 'pass': '奇迹之旅已有奖励'}

    def __init__(self, port, keys=None):
        self.port = port
        self.keys = {'photo': 'p', 'calendar': 'l', 'pass': 'j', 'interaction': 'f'}
        self.keys.update(keys or {})

    def require(self, condition, message):
        if not condition:
            raise AutomationError(message)

    def recover_home(self):
        for attempt in range(9):
            if self.port.exists('IconPageMainFeature'):
                return
            self.require(attempt < 8, '返回主界面超时，请先手动回到大世界')
            # Never select dialogue choices or confirm an unknown modal.
            self.port.key('esc')
            self.port.sleep(0.5)

    def run_one(self, action):
        self.require(action in self.LABELS, f'未知任务：{action}')
        try:
            self.recover_home()
            result = getattr(self, f'_{action}')()
            self.recover_home()
            return {'action': action, 'name': self.LABELS[action], **result}
        except AutomationError:
            self.port.evidence(f'{action}_failed')
            raise

    def run_many(self, actions):
        results = []
        for action in actions:
            try:
                results.append(self.run_one(action))
            except AutomationError as exc:
                self.port.evidence(f'{action}_batch_failed')
                results.append({'action': action, 'name': self.LABELS.get(action, action),
                                'status': 'failed', 'message': str(exc)})
        return results

    def _photo(self):
        self.port.key(self.keys['photo'])
        self.require(self.port.wait('IconPhotoFeature'), '未进入拍照界面')
        self.port.key('space')
        self.require(self.port.wait('IconPhotoEdit', timeout=12), '拍照后未出现照片预览')
        self.port.evidence('photo_result')
        return {'status': 'succeeded', 'message': '已拍照并确认照片预览，保留照片'}

    def _dig(self):
        self.port.key('esc')
        self.require(self.port.wait('menu_page'), '未进入美鸭梨菜单')
        self.require(self.port.click_text('美鸭梨挖掘', region='AreaEscEntrances', scroll=True),
                     '菜单中未识别到美鸭梨挖掘入口')
        self.require(self.port.wait('dig_page'), '未进入美鸭梨挖掘界面')
        if not self.port.exists('ButtonDigGather'):
            count = self.port.text('AreaDigingNumText')
            return {'status': 'skipped', 'message': f'暂无可收获项目，当前挖掘数量：{count or "未识别"}'}
        self.port.click_feature('ButtonDigGather')
        if self.port.wait('ButtonDigGatherConfirm', timeout=1):
            self.port.click_feature('ButtonDigGatherConfirm')
        self.require(self.port.wait('ButtonDigAgain', timeout=10), '挖掘收获后未出现再次挖掘按钮')
        self.port.click_feature('ButtonDigAgain')
        self.require(self.port.wait('dig_active', timeout=10), '再次挖掘后未确认进行中的派遣')
        self.port.evidence('dig_dispatched')
        return {'status': 'succeeded', 'message': '已收获，并确认再次挖掘正在进行'}

    def _wish(self):
        self.port.key(self.keys['calendar'])
        self.require(self.port.wait('calendar_page'), '未进入奇想日历')
        self.port.click_feature('ButtonZxxyEntrance')
        self.require(self.port.wait('IconZxxyFeature'), '未进入朝夕心愿')
        count = self.port.claim_wish_rewards()
        score = self.port.text('AreaZxxyScore')
        self.port.evidence('wish_result')
        return {'status': 'succeeded' if count else 'skipped', 'claimed': count, 'score': score,
                'message': f'朝夕心愿已有奖励：已确认领取 {count} 次；当前分数 {score or "未识别"}'}

    def _pass(self):
        self.port.key(self.keys['pass'])
        self.require(self.port.wait('pass_page', timeout=10), '未进入奇迹之旅，请先手动完成开启探索')
        tabs = [('旅行任务', 'AreaMonthlyPassTab2'), ('旅行秘宝', 'AreaMonthlyPassTab1')]
        checks = []
        # Finish inspecting both pages before any reward-changing action.
        for tab, region in tabs:
            if not self.port.click_text(tab, region=region) or not self.port.wait('pass_page'):
                self.port.evidence('pass_precheck_unknown')
                return {'status': 'skipped', 'claimed': 0, 'checked_tabs': checks,
                        'message': f'未确认奇迹之旅{tab}页面，未执行奖励领取'}
            self.port.sleep(.6)
            first = self.port.exists('ButtonMonthlyPassAward')
            self.port.sleep(.2)
            second = self.port.exists('ButtonMonthlyPassAward')
            if first != second:
                self.port.evidence('pass_precheck_unstable')
                return {'status': 'skipped', 'claimed': 0, 'checked_tabs': checks,
                        'message': f'未确认奇迹之旅{tab}稳定领取状态，未执行奖励领取'}
            checks.append({'tab': tab, 'pending': bool(second)})
        self.port.evidence('pass_precheck')
        pending = {item['tab'] for item in checks if item['pending']}
        if not pending:
            return {'status': 'skipped', 'claimed': 0, 'checked_tabs': checks,
                    'message': '奇迹之旅两页均无待领取奖励，已跳过'}
        count = 0
        for tab, region in tabs:
            if tab not in pending: continue
            self.require(self.port.click_text(tab, region=region), f'未识别到奇迹之旅的{tab}页签')
            self.require(self.port.wait('pass_page'), f'领取前未确认奇迹之旅{tab}页面')
            self.port.sleep(0.6)
            for _ in range(4):
                if not self.port.exists('ButtonMonthlyPassAward'):
                    break
                self.port.click_feature('ButtonMonthlyPassAward')
                self.require(self.port.wait('reward_popup'), '领取奇迹之旅后未出现奖励结果')
                self.port.key(self.keys['interaction'])
                self.require(self.port.wait('pass_page'), '领取奖励后未返回奇迹之旅')
                count += 1
            self.require(not self.port.exists('ButtonMonthlyPassAward'), '奇迹之旅领取按钮反复出现，请检查界面')
        self.port.evidence('pass_result')
        return {'status': 'succeeded' if count else 'skipped', 'claimed': count, 'checked_tabs': checks,
                'message': f'奇迹之旅已有奖励：已确认领取 {count} 次'}

    def _auto_wish(self):
        from nuannuan.objective_runner import ObjectiveRunner
        return ObjectiveRunner(self.port).run('wish', execute=getattr(self.port, 'execute_objectives', True))

    def _starsea(self):
        from nuannuan.objective_runner import ObjectiveRunner
        return ObjectiveRunner(self.port).run('starsea', execute=getattr(self.port, 'execute_objectives', True))
