"""Additional daily tasks reconstructed from local Whimbox task sources."""
import json
import os
import re
import uuid
from pathlib import Path

from nuannuan.core.errors import AutomationError
from nuannuan.core.text import count_option, read_fraction, require
from nuannuan.daily.runner import DailyRunner

EXTRA_SETTINGS = '扩展功能设置'
EXTRA_DEFAULTS = {
    '活跃能量用途': '素材激化', '快速挑战次数': 1,
    '激化产物': '闪亮泡泡', '激化材料': '布布果', '祝福关卡': '古铸剑遗址',
    '魔物关卡': '攀越', '每周幻境目标': '奇格格达,卷卷', '奇迹之冠最多挑战': 10,
    '领取巅峰赛奖励': True, '巅峰赛兑换物品': '', '家园日常路线': '家园日常',
    '钓鱼抛竿次数': 3, '钓鱼前万物交响': False, '结晶收集前化万相': False,
    '小游戏最多重试': 1, '允许小游戏支付噗灵': False,
    '每日结束操作': '保持游戏', '每日结束时关闭启动器': False,
    '自动启动游戏': True,
}
REALMS = {'monster': '魔物试炼幻境', 'bless': '祝福闪光幻境', 'weekly': '心之突破幻境', 'realm': '素材激化幻境'}


def migrate_extra_file(path):
    path = Path(path)
    if not path.exists():
        return
    old = json.loads(path.read_text(encoding='utf-8'))
    migrated = {key: old.get(key, default) for key, default in EXTRA_DEFAULTS.items()}
    if migrated['激化材料']=='萤光草':
        migrated['激化材料']='布布果'
    if '活跃能量用途' not in old:
        migrated['活跃能量用途'] = {'素材激化幻境': '素材激化', '魔物试炼幻境': '魔物试炼',
                                 '祝福闪光幻境': '祝福闪光幻境'}.get(old.get('心愿体力幻境'), '素材激化')
    if migrated == old:
        return
    backup = path.parent/'migrations'
    backup.mkdir(parents=True, exist_ok=True)
    (backup/f'ExtraDaily-before-auto-daily-{uuid.uuid4().hex}.json').write_bytes(path.read_bytes())
    temporary = path.with_suffix('.migration.tmp')
    temporary.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class ExtraDaily:
    def __init__(self, port, options=None):
        self.port = port
        self.options = {**EXTRA_DEFAULTS, **(options or {})}

    def energy(self):
        self.port.goto_page('奇想日历')
        current, total = read_fraction(self.port.text('AreaZxxyEnergy'))
        self.port.evidence('energy')
        return {'status': 'succeeded', 'energy': current, 'capacity': total,
                'message': f'活跃能量 {current}/{total}'}

    def claim_result(self, label):
        require(self.port.wait('reward_popup', timeout=15), f'{label}后未确认奖励结果，停止后续消耗')
        self.port.evidence(label)
        self.port.key(self.port.settings.get('交互', 'f'))

    def quick_realm(self, kind, target=None, count=None):
        require(kind in {'monster', 'bless', 'weekly'}, '不支持的快速挑战类型')
        count = count_option(self.options['快速挑战次数'] if count is None else count, '快速挑战次数')
        target = target or self.options['魔物关卡' if kind == 'monster' else '祝福关卡']
        target = str(target).split('|')[0].strip()
        require(bool(target), '请先设置幻境关卡')
        energy = self.energy()['energy']
        # Each requested run is separately confirmed; never click MAX.
        require(energy > 0, '活跃能量不足')
        self.port.goto_page(REALMS[kind])
        require(self.port.click_text(target, 'AreaBlessHuanjingLevelsSelect', scroll=True), f'未找到关卡：{target}')
        if kind == 'bless':
            require(self.port.click_text('困难', 'AreaBlessHuanjingDifficulty3'), '未找到困难难度')
        for _ in range(count):
            require(self.port.wait('ButtonBlessHuanjingQuickPlay'), '未找到快速挑战按钮；需先手动通关并解锁')
            self.port.click_feature('ButtonBlessHuanjingQuickPlay')
            require(self.port.wait('ButtonHuanjingConfirm'), '未找到注入能量确认，未消耗体力')
            # Inspect the actual dialog before committing energy.
            dialog = self.port.text('AreaDialog')
            if '不足' in dialog or '溢出' in dialog or '已达上限' in dialog:
                raise AutomationError(f'幻境无法继续：{dialog}')
            quantity = re.search(r'(?:数量|次数)\s*[:：]?\s*(\d+)', dialog)
            require(quantity is not None and int(quantity[1]) == 1, '未确认单次挑战数量为 1，请手动调整')
            cost = re.search(r'(?:消耗|注入)\s*(\d+)\s*(?:点)?活跃能量', dialog)
            require(cost is not None and int(cost[1]) > 0, '未识别到本次活跃能量消耗，未确认挑战')
            require(energy >= int(cost[1]) * count, '活跃能量不足以完成设置的挑战次数')
            self.port.click_feature('ButtonHuanjingConfirm')
            if '溢出' in self.port.text('AreaDialog'):
                self.port.key('esc')
                raise AutomationError('祝福闪光数量溢出，未继续挑战')
            self.claim_result('realm_reward')
        return {'status': 'succeeded', 'confirmed_runs': count, 'message': f'{REALMS[kind]} · {target}：确认 {count} 次奖励'}

    def weekly(self):
        targets = [t.strip() for t in re.split('[,，]', self.options['每周幻境目标']) if t.strip()]
        require(targets and len(targets) == len(set(targets)) and len(targets) <= 2, '每周目标需填写 1 至 2 个不同关卡')
        self.port.goto_page('奇想日历')
        finished, total = read_fraction(self.port.text('AreaWeeklyCountText'))
        if finished >= min(total, len(targets)):
            return {'status': 'skipped', 'message': f'每周幻境已完成 {finished}/{total}'}
        completed = 0
        # Already finished rows are skipped by their visible completion state.
        for target in targets:
            if finished + completed >= min(total, len(targets)):
                break
            self.port.goto_page('心之突破幻境')
            require(self.port.click_text(target, 'AreaBlessHuanjingLevelsSelect', scroll=True), f'未找到周本：{target}')
            if not self.port.exists('ButtonBlessHuanjingQuickPlay'):
                require('已完成' in self.port.text('AreaDialog'), '未确认周本已完成或已解锁快速挑战')
                continue
            self.quick_realm('weekly', target, count=1)
            completed += 1
        self.port.goto_page('奇想日历')
        after, _ = read_fraction(self.port.text('AreaWeeklyCountText'))
        require(after >= finished + completed and completed > 0, '周本奖励后完成次数未增加')
        return {'status': 'succeeded', 'message': f'每周幻境复核 {after}/{total}'}

    def exchange(self):
        require(self.options['激化产物'] in {'噗灵', '丝线', '闪亮泡泡'}, '不支持的激化产物')
        material = str(self.options['激化材料']).strip()
        require(bool(material), '请先设置激化消耗材料')
        require(self.energy()['energy'] >= 10, '活跃能量不足 10，未开始激化')
        self.port.goto_page('素材激化幻境')
        require(self.port.wait('ButtonJihuaInnerGo'), '未找到素材激化入口')
        self.port.click_feature('ButtonJihuaInnerGo')
        require(self.port.wait('IconPageMainFeature', timeout=25), '未进入素材激化幻境')
        self.port.approach_interaction('打开素材激化台', 'AreaTextJihuatai')
        require(self.port.click_text(self.options['激化产物'], 'AreaJihuaTargetSelect', scroll=True), '未找到激化产物')
        require(self.port.select_material(material), f'未找到指定激化材料：{material}')
        require(self.port.wait('ButtonJihuaNumConfirm'), '未出现激化数量窗口')
        # Source default is one; do not silently consume a selected previous amount.
        require(self.port.confirm_single_quantity(), '未确认激化数量为 1，请手动把数量调为 1')
        self.port.click_feature('ButtonJihuaNumConfirm')
        require(self.port.wait('ButtonJihuaFinallyConfirm'), '体力或材料不足，未开始激化')
        self.port.click_feature('ButtonJihuaFinallyConfirm')
        if self.port.wait('IconSkip', timeout=3):
            self.port.key(self.port.settings.get('交互', 'f'))
        self.claim_result('exchange_reward')
        return {'status': 'succeeded', 'message': f'已确认一份{self.options["激化产物"]}激化奖励；材料：{material}'}

    def spend_energy(self):
        """Use the selected destination; re-observe energy after every exchange."""
        self.port._daily_energy_processed = True
        target = self.options.get('活跃能量用途') or '素材激化'
        require(target in {'素材激化', '祝福闪光幻境', '魔物试炼'}, '不支持的活跃能量用途')
        before = self.energy()['energy']
        minimum = 10 if target == '素材激化' else 1
        if before < minimum:
            return {'status': 'skipped', 'energy_after': before, 'message': f'活跃能量 {before}，不足以开始{target}'}
        if not self.port.exists('ButtonHuanjingGo'):
            return {'status': 'skipped', 'energy_after': before, 'message': '未检测到幻境挑战入口，未消耗活跃能量'}
        if target != '素材激化':
            result = self.quick_realm('bless' if target == '祝福闪光幻境' else 'monster')
            after = self.energy()['energy']
            require(after < before, '挑战后活跃能量未下降，未继续消耗')
            return {**result, 'energy_before': before, 'energy_after': after}
        current, runs = before, 0
        while True:
            require(runs < 100, '素材激化达到单次每日上限 100 份，已停止')
            self.exchange()
            runs += 1
            after = self.energy()['energy']
            require(after < current, '素材激化后活跃能量未下降，停止再次激化')
            current = after
            if current <= 100:
                break
        return {'status': 'succeeded', 'confirmed_runs': runs, 'energy_before': before, 'energy_after': current,
                'message': f'素材激化确认 {runs} 份；活跃能量 {before} → {current}，已不大于 100'}

    def automatic(self, action):
        if action == 'auto_crystal':
            from nuannuan.daily.starsea_crystal import CrystalRuntime,StarseaCrystalRunner
            return StarseaCrystalRunner(CrystalRuntime(self.port)).run()
        if action == 'auto_energy':
            if getattr(self.port, '_energy_spending_failed', False):
                return {'status': 'skipped', 'message': '此前幻境消耗未确认成功，未继续消耗能量'}
            if getattr(self.port, '_daily_energy_processed', False):
                return {'status': 'skipped', 'message': '心愿中已处理活跃能量，未重复尝试；结果见心愿记录'}
            return self.spend_energy()
        if action in {'auto_weekly', 'auto_crown'}:
            self.port.goto_page('奇想日历')
            region, label = ('AreaWeeklyCountText', '每周幻境') if action == 'auto_weekly' else ('AreaMiraCrownOverview', '奇迹之冠')
            try:
                current, total = read_fraction(self.port.text(region))
            except AutomationError:
                self.port.evidence(f'{action}_not_detected')
                return {'status': 'skipped', 'message': f'未识别到{label}有效进度，未执行'}
            if action == 'auto_crown':
                self.port.evidence('daily_crown_progress_check')
                if current > 0:
                    return {'status': 'skipped', 'progress': {'current': current, 'total': total},
                            'message': f'奇迹之冠本期已有挑战进度 {current}/{total}，跳过挑战、领奖和兑换'}
                from nuannuan.daily.crown import CrownRunner
                return CrownRunner(self.port, self.options).run(only_unstarted=True)
            return self.run('weekly' if action == 'auto_weekly' else 'crown')
        require(action == 'auto_home', '未知自动日常')
        self.port.goto_page('地图')
        region = self.port.text('AreaBigMapRegionName')
        if '家园' not in region:
            self.port.click_region('AreaBigMapRegionName')
            if not self.port.exists('IconBigMapHomeFeature'):
                return {'status': 'skipped', 'message': '未检测到家园地图入口，未运行家园路线'}
        return self.run('home_daily')

    def run(self, action):
        try:
            if action=='enter_game':
                from nuannuan.daily.game_tools import GameTools
                return GameTools(self.port).enter()
            if action=='finish_daily':
                from nuannuan.daily.game_tools import GameTools
                finish=self.options['每日结束操作']
                require(finish in {'保持游戏','关闭游戏','关闭游戏和助手'},'未知每日结束操作')
                if finish=='保持游戏':
                    return {'status':'skipped','message':'每日流程已结束，保持游戏运行'}
                result=GameTools(self.port).close()
                if self.options['每日结束时关闭启动器']:
                    launcher=GameTools(self.port).close_launcher()
                    result={**launcher,'message':result['message']+'；'+launcher['message']}
                if result['status']=='succeeded' and finish=='关闭游戏和助手':
                    self.port.request_exit_after_report=True
                return result
            if action in {'realm', 'weekly', 'bless', 'monster'} and getattr(self.port, '_energy_spending_failed', False):
                return {'status': 'skipped', 'message': '此前幻境消耗未确认成功，未再次挑战'}
            if action.startswith('auto_'): result = self.automatic(action)
            elif action == 'energy_check': result = self.energy()
            elif action == 'weekly': result = self.weekly()
            elif action == 'realm': result = self.exchange()
            elif action in {'monster', 'bless'}: result = self.quick_realm(action)
            elif action == 'crown':
                from nuannuan.daily.crown import CrownRunner
                result = CrownRunner(self.port, self.options).run()
            elif action == 'home_daily':
                from nuannuan.routes.scripts import ScriptRunner
                result = ScriptRunner(self.port).route(self.options['家园日常路线'])
                self.port.goto_page('地图')
                text = self.port.text('AreaBigMapMeteorText')
                result = {**result, 'has_meteor': '巨陨星' in text,
                          'message': result['message'] + ('；发现巨陨星' if '巨陨星' in text else '；未识别到巨陨星提示')}
            else: raise AutomationError(f'未知扩展任务：{action}')
            DailyRunner(self.port).recover_home()
            return result
        except AutomationError:
            if action in {'realm', 'weekly', 'bless', 'monster', 'auto_energy'}:
                self.port._energy_spending_failed = True
            self.port.evidence(f'{action}_failed')
            raise
