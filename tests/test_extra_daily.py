import unittest

from nuannuan.core.errors import AutomationError


class RealmPort:
    def __init__(self, reward=True, progress='0/2'):
        self.events = []
        self.reward = reward
        self.progress = progress
        self.settings = {}
    def goto_page(self, name): self.events.append(('page', name))
    def exists(self, name): return name != 'ButtonHuanjingCancel'
    def wait(self, name, timeout=6):
        return self.reward if name == 'reward_popup' else True
    def click_feature(self, name): self.events.append(('click', name))
    def click_region(self, name): self.events.append(('region', name))
    def click_text(self, text, region=None, scroll=False):
        self.events.append(('text', text))
        return True
    def key(self, key): self.events.append(('key', key))
    def sleep(self, seconds): pass
    def text(self, name):
        return {'AreaWeeklyCountText': self.progress, 'AreaZxxyEnergy': '250/350',
                'AreaDialog': '数量：1 消耗40点活跃能量'}.get(name, '')
    def evidence(self, name): self.events.append(('evidence', name))


class ExtraDailyTests(unittest.TestCase):
    def test_default_exchange_material_exists_and_supports_exchange(self):
        import json
        from nuannuan.config import ROOT
        from nuannuan.daily.extra import EXTRA_DEFAULTS
        materials=json.loads((ROOT/'assets/materials.json').read_text(encoding='utf-8'))
        self.assertIn(EXTRA_DEFAULTS['激化材料'],materials)
        self.assertTrue(materials[EXTRA_DEFAULTS['激化材料']]['jihua'])

    def test_finish_keeps_game_by_default_and_optional_close_order_is_explicit(self):
        from unittest.mock import patch
        from nuannuan.daily.extra import ExtraDaily
        events=[]
        class Tools:
            def __init__(self,port):pass
            def close(self):events.append('game');return {'status':'succeeded','message':'closed'}
            def close_launcher(self):events.append('launcher');return {'status':'succeeded','message':'launcher closed'}
        port=RealmPort()
        with patch('nuannuan.daily.game_tools.GameTools',Tools):
            result=ExtraDaily(port).run('finish_daily')
            self.assertEqual(result['status'],'skipped')
            self.assertFalse(events)
            ExtraDaily(port,{'每日结束操作':'关闭游戏和助手','每日结束时关闭启动器':True}).run('finish_daily')
        self.assertEqual(events,['game','launcher'])
        self.assertTrue(port.request_exit_after_report)

    def test_old_energy_destination_is_preserved_and_removed_flows_are_backed_up(self):
        import json
        import tempfile
        from pathlib import Path
        from nuannuan.config import ROOT
        import nuannuan.daily.extra as module
        self.assertTrue(hasattr(module, 'migrate_extra_file'))
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as directory:
            path = Path(directory)/'扩展功能设置.json'
            old = {'心愿体力幻境': '祝福闪光幻境', '激化材料': '花环木球',
                   '每日前流程JSON': '[{"type":"path","script_name":"旧路线"}]', '每日后流程JSON': '[]'}
            path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
            module.migrate_extra_file(path)
            migrated = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(migrated['活跃能量用途'], '祝福闪光幻境')
            self.assertEqual(migrated['激化材料'], '花环木球')
            self.assertNotIn('每日前流程JSON', migrated)
            backups = list((path.parent/'migrations').glob('*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8')), old)
            module.migrate_extra_file(path)
            self.assertEqual(len(list((path.parent/'migrations').glob('*.json'))), 1)

    def test_fraction_rejects_ambiguous_or_invalid_energy(self):
        from nuannuan.core.text import read_fraction
        self.assertEqual(read_fraction(' V 250 / 350 '), (250, 350))
        for text in ['350', '1/2 3/4', '999/350', '0/0', '-1/350']:
            with self.assertRaises(AutomationError): read_fraction(text)

    def test_realm_never_uses_max_and_requires_observed_reward(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        result = ExtraDaily(port, {'快速挑战次数': 1, '魔物关卡': '攀越'}).quick_realm('monster')
        self.assertEqual(result['status'], 'succeeded')
        self.assertNotIn(('click', 'ButtonBlessHuanjingNumMax'), port.events)
        self.assertIn(('click', 'ButtonHuanjingConfirm'), port.events)
        port = RealmPort(reward=False)
        with self.assertRaisesRegex(AutomationError, '奖励'):
            ExtraDaily(port, {'快速挑战次数': 1, '魔物关卡': '攀越'}).quick_realm('monster')

    def test_invalid_challenge_count_fails_before_input(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        with self.assertRaises(AutomationError):
            ExtraDaily(port, {'快速挑战次数': 0}).quick_realm('monster')
        self.assertFalse(port.events)

    def test_completed_weekly_is_skipped_without_entering_realm(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort(progress='2/2')
        result = ExtraDaily(port, {'每周幻境目标': '奇格格达,卷卷'}).weekly()
        self.assertEqual(result['status'], 'skipped')
        self.assertNotIn(('page', '心之突破幻境'), port.events)

    def test_insufficient_energy_prevents_confirmation(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        with self.assertRaisesRegex(AutomationError, '能量'):
            ExtraDaily(port, {'快速挑战次数': 10, '魔物关卡': '攀越'}).quick_realm('monster')
        self.assertNotIn(('click', 'ButtonHuanjingConfirm'), port.events)

    def test_identify_only_filters_new_daily_steps(self):
        from nuannuan.daily.workflow import DailyWorkflow
        from tests.test_daily_workflow import Port
        port = Port()
        DailyWorkflow(port).run({'朝夕心愿': True, '每周幻境': True, '奇迹之冠': True,
                                 '检查活跃能量': True, '家园日常': True, '运行模式': '只识别'})
        self.assertEqual(port.events, [('daily', 'auto_wish')])

    def test_daily_energy_defaults_to_exchange_without_duplicate_realm_switches(self):
        from nuannuan.daily.workflow import DAILY_DEFAULTS
        from nuannuan.daily.extra import EXTRA_DEFAULTS
        for key in ['每周幻境', '奇迹之冠', '素材激化', '祝福闪光幻境', '魔物试炼', '家园日常',
                    '每日前自定义流程', '每日后自定义流程']:
            self.assertNotIn(key, DAILY_DEFAULTS)
        self.assertEqual(EXTRA_DEFAULTS['活跃能量用途'], '素材激化')
        self.assertNotIn('每日前流程JSON', EXTRA_DEFAULTS)
        self.assertNotIn('每日后流程JSON', EXTRA_DEFAULTS)
        self.assertFalse(EXTRA_DEFAULTS['允许小游戏支付噗灵'])

    def test_completed_crown_skips_challenge_and_empty_exchange_does_not_spend(self):
        from nuannuan.daily.crown import CrownRunner
        from nuannuan.daily.extra import EXTRA_DEFAULTS
        port = RealmPort()
        port.text = lambda region: '25/25' if region == 'AreaMiraCrownOverview' else ''
        result = CrownRunner(port, {**EXTRA_DEFAULTS, '领取巅峰赛奖励': False}).run()
        self.assertEqual(result['status'], 'skipped')
        self.assertFalse(any(e[0] == 'click' for e in port.events))

    def test_detected_energy_and_specific_realm_wishes_are_enabled(self):
        from types import SimpleNamespace
        from nuannuan.daily.objective_actions import ObjectiveActions
        from nuannuan.daily.objectives import Objective
        port = SimpleNamespace(extra_options={}, allow_chat=False)
        item = Objective(0, '消耗150点活跃能量', 'energy', False)
        self.assertEqual(ObjectiveActions(port).reason('wish', item), '')
        self.assertEqual(ObjectiveActions(port).reason('wish', Objective(1, '祝福闪光幻境', 'bless', False)), '')


class EnergyPort(RealmPort):
    def __init__(self, energy=250, costs=(100, 50), reward=True):
        super().__init__(reward=reward)
        self.energy_value = energy
        self.costs = list(costs)
        self.exchanges = 0
        self.energy_reads = []
        self.energy_unreadable_after = False
    def text(self, name):
        if name == 'AreaZxxyEnergy':
            self.energy_reads.append(self.energy_value)
            if self.energy_unreadable_after and self.exchanges: return '无法识别'
            return f'{self.energy_value}/350'
        return super().text(name)
    def click_feature(self, name):
        super().click_feature(name)
        if name == 'ButtonHuanjingConfirm':
            self.energy_value -= 40
        if name == 'ButtonJihuaFinallyConfirm':
            self.energy_value -= self.costs[min(self.exchanges, len(self.costs)-1)]
            self.exchanges += 1
    def approach_interaction(self, *args): pass
    def select_material(self, material): return True
    def confirm_single_quantity(self): return True


class AutomaticEnergyTests(unittest.TestCase):
    def test_unavailable_realm_entrance_is_skipped_without_energy_spending(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort()
        port.exists = lambda name: name == 'IconPageMainFeature'
        result = ExtraDaily(port).run('auto_energy')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(port.exchanges, 0)

    def test_exchange_rechecks_observed_energy_and_stops_exactly_at_100(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort()
        result = ExtraDaily(port).spend_energy()
        self.assertEqual(port.energy_value, 100)
        self.assertEqual(port.exchanges, 2)
        self.assertEqual(result['confirmed_runs'], 2)
        self.assertEqual(result['energy_after'], 100)
        self.assertIn(150, port.energy_reads)
        self.assertIn(100, port.energy_reads)

    def test_first_exchange_runs_even_below_100_but_not_below_cost(self):
        from nuannuan.daily.extra import ExtraDaily
        for energy, runs in [(100, 1), (50, 1), (9, 0), (0, 0)]:
            with self.subTest(energy=energy):
                port = EnergyPort(energy, (10,))
                result = ExtraDaily(port).spend_energy()
                self.assertEqual(port.exchanges, runs)
                self.assertEqual(result['status'], 'succeeded' if runs else 'skipped')

    def test_stale_energy_or_failed_read_never_triggers_another_exchange(self):
        from nuannuan.daily.extra import ExtraDaily
        for unreadable in [False, True]:
            with self.subTest(unreadable=unreadable):
                port = EnergyPort(costs=(0,))
                port.energy_unreadable_after = unreadable
                with self.assertRaises(AutomationError): ExtraDaily(port).spend_energy()
                self.assertEqual(port.exchanges, 1)

    def test_unconfirmed_reward_stops_repeat(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort(reward=False)
        with self.assertRaisesRegex(AutomationError, '奖励'): ExtraDaily(port).spend_energy()
        self.assertEqual(port.exchanges, 1)

    def test_cancellation_during_energy_recheck_is_propagated(self):
        from nuannuan.daily.extra import ExtraDaily
        class Cancelled(Exception): pass
        port = EnergyPort()
        original = port.text
        def text(name):
            if name == 'AreaZxxyEnergy' and port.exchanges: raise Cancelled()
            return original(name)
        port.text = text
        with self.assertRaises(Cancelled): ExtraDaily(port).spend_energy()
        self.assertEqual(port.exchanges, 1)

    def test_invalid_destination_never_falls_back_to_spending(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort()
        with self.assertRaises(AutomationError):
            ExtraDaily(port, {'活跃能量用途': '未知幻境'}).spend_energy()
        self.assertFalse(port.events)

    def test_explicit_realm_is_used_without_exchange_fallback(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort()
        result = ExtraDaily(port, {'活跃能量用途': '魔物试炼'}).spend_energy()
        self.assertEqual(port.exchanges, 0)
        self.assertIn(('page', '魔物试炼幻境'), port.events)
        self.assertEqual(result['confirmed_runs'], 1)

    def test_unavailable_progress_and_home_are_skipped_without_running_routes(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        port.text = lambda name: ''
        port.exists = lambda name: name == 'IconPageMainFeature'
        for action in ['auto_weekly', 'auto_crown', 'auto_home']:
            with self.subTest(action=action):
                result = ExtraDaily(port).run(action)
                self.assertEqual(result['status'], 'skipped')
        self.assertNotIn(('page', '心之突破幻境'), port.events)

    def test_other_world_region_is_not_mistaken_for_home(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        port.text = lambda name: '伊赞之土' if name == 'AreaBigMapRegionName' else ''
        port.exists = lambda name: name == 'IconPageMainFeature'
        result = ExtraDaily(port).run('auto_home')
        self.assertEqual(result['status'], 'skipped')
        self.assertIn(('region', 'AreaBigMapRegionName'), port.events)

    def test_detected_home_entrance_runs_saved_route_and_reports_meteor(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        port.text = lambda name: '今日巨陨星' if name == 'AreaBigMapMeteorText' else '花愿镇'
        def execute_route(name):
            port.events.append(('route', name))
            return {'status': 'succeeded', 'message': '已确认采星'}
        port.execute_route = execute_route
        result = ExtraDaily(port).run('auto_home')
        self.assertEqual(result['status'], 'succeeded')
        self.assertIn(('route', '家园日常'), port.events)
        self.assertTrue(result['has_meteor'])

    def test_automatic_completed_weekly_and_crown_do_not_challenge(self):
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        port.text = lambda region: {'AreaWeeklyCountText': '2/2', 'AreaMiraCrownOverview': '25/25'}.get(region, '')
        for action in ['auto_weekly', 'auto_crown']:
            result = ExtraDaily(port, {'领取巅峰赛奖励': False}).run(action)
            self.assertEqual(result['status'], 'skipped')
        self.assertFalse(any(event[0] == 'click' for event in port.events))

    def test_daily_crown_skips_any_prior_progress_including_rewards_and_exchange(self):
        from unittest.mock import patch
        from nuannuan.daily.extra import ExtraDaily
        for progress in ['1/24', '23/24', '24/24']:
            with self.subTest(progress=progress):
                port = RealmPort()
                port.text = lambda region: progress if region == 'AreaMiraCrownOverview' else ''
                with patch('nuannuan.daily.crown.CrownRunner.run') as run:
                    result = ExtraDaily(port).automatic('auto_crown')
                self.assertEqual(result['status'], 'skipped')
                run.assert_not_called()
                self.assertIn(progress, result['message'])
                self.assertFalse(any(event[0] == 'click' for event in port.events))

    def test_daily_crown_runs_only_confirmed_zero_progress(self):
        from unittest.mock import patch
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        port.text = lambda region: '0/24' if region == 'AreaMiraCrownOverview' else ''
        with patch('nuannuan.daily.crown.CrownRunner.run', return_value={'status': 'succeeded', 'message': '已挑战'}) as run:
            result = ExtraDaily(port).automatic('auto_crown')
        run.assert_called_once()
        self.assertEqual(result['status'], 'succeeded')

    def test_daily_crown_unreliable_progress_never_enters_challenge(self):
        from unittest.mock import patch
        from nuannuan.daily.extra import ExtraDaily
        for progress in ['', '0/0', 'O/24', '25/24']:
            with self.subTest(progress=progress):
                port = RealmPort()
                port.text = lambda region: progress
                with patch('nuannuan.daily.crown.CrownRunner.run') as run:
                    result = ExtraDaily(port).automatic('auto_crown')
                self.assertEqual(result['status'], 'skipped')
                run.assert_not_called()

    def test_daily_crown_rechecks_progress_before_entering(self):
        from unittest.mock import patch
        from nuannuan.daily.extra import ExtraDaily
        port = RealmPort()
        progress = iter(['0/24', '1/24'])
        port.text = lambda region: next(progress)
        with patch('nuannuan.daily.crown.CrownRunner.enter') as enter:
            result = ExtraDaily(port).automatic('auto_crown')
        enter.assert_not_called()
        self.assertEqual(result['status'], 'skipped')

    def test_failed_energy_wish_is_not_repeated_by_daily_fallback(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort(reward=False)
        with self.assertRaises(AutomationError): ExtraDaily(port).spend_energy()
        result = ExtraDaily(port).run('auto_energy')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(port.exchanges, 1)

    def test_failed_realm_reward_blocks_remaining_daily_consumption(self):
        from nuannuan.daily.extra import ExtraDaily
        port = EnergyPort(reward=False)
        with self.assertRaises(AutomationError): ExtraDaily(port).run('monster')
        result = ExtraDaily(port).run('auto_energy')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(port.exchanges, 0)
