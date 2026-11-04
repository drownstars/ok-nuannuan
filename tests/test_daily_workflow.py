import unittest

from nuannuan.core.errors import AutomationError
from nuannuan.daily.workflow import DailyWorkflow, migrate_daily_options
from nuannuan.config import make_config


class Port:
    def __init__(self):
        self.events = []
        self.status = 'succeeded'
        self.failed_attempt = False
        self.partial_unsupported = True
    def validate_follow_route(self, name):
        self.events.append(('validate', name))
        if name == 'missing':
            raise AutomationError('路线不存在')
    def run_daily_action(self, action):
        self.events.append(('daily', action))
        return {'name': action, 'status': self.status, 'message': 'done',
                'unsupported': [{'reason': 'not supported'}] if self.status == 'partial' and self.partial_unsupported else [],
                'attempts': [{'status': 'failed'}] if self.failed_attempt else []}
    def run_route(self, name):
        self.events.append(('route', name))
        return {'name': name, 'status': 'succeeded', 'message': 'route done'}


class DailyWorkflowTests(unittest.TestCase):
    def options(self):
        return {'朝夕心愿': True, '星海拾光': True, '美鸭梨挖掘': False, '奇迹之旅奖励': False,
                '运行模式': '自动执行', '每日结束后跑图': True, '接续跑图路线': 'route'}

    def test_photography_and_duplicate_task_entries_are_not_daily_stages(self):
        port = Port()
        DailyWorkflow(port).run(self.options())
        actions = [action for kind, action in port.events if kind == 'daily']
        self.assertEqual(actions, ['enter_game', 'energy_check', 'auto_home', 'auto_weekly',
                                   'auto_wish', 'auto_energy', 'auto_crystal', 'starsea', 'auto_crown', 'finish_daily'])
        registered = {name for _, name in make_config()['onetime_tasks']}
        self.assertFalse(registered & {'PhotoTask', 'WishAutoTask', 'StarseaTask', 'ObjectiveScanTask', 'WishTask'})

    def test_follow_route_runs_after_daily_and_is_checked_beforehand(self):
        port = Port()
        DailyWorkflow(port).run(self.options())
        self.assertEqual(port.events[0], ('validate', 'route'))
        self.assertEqual(port.events[-2:], [('route', 'route'), ('daily', 'finish_daily')])
        self.assertEqual(len([e for e in port.events if e[0] == 'route']), 1)

    def test_missing_follow_route_prevents_daily_inputs(self):
        port = Port()
        options = {**self.options(), '接续跑图路线': 'missing'}
        with self.assertRaises(AutomationError):
            DailyWorkflow(port).run(options)
        self.assertFalse(any(e[0] == 'daily' for e in port.events))

    def test_identify_only_never_follows_route_or_basic_daily_actions(self):
        port = Port()
        options = {**self.options(), '运行模式': '只识别', '美鸭梨挖掘': True}
        DailyWorkflow(port).run(options)
        self.assertFalse(any(e[0] in {'route', 'validate'} or e == ('daily', 'dig') for e in port.events))

    def test_execution_failure_prevents_follow_but_unsupported_partial_allows_it(self):
        port = Port()
        port.status = 'partial'
        DailyWorkflow(port).run(self.options())
        self.assertIn(('route', 'route'), port.events)
        port.events.clear()
        port.failed_attempt = True
        DailyWorkflow(port).run(self.options())
        self.assertNotIn(('route', 'route'), port.events)

    def test_cancellation_preserves_completed_results_and_does_not_follow(self):
        class Cancelled(Exception):
            pass
        port = Port()
        original = port.run_daily_action
        def action(name):
            if name == 'starsea':
                raise Cancelled()
            return original(name)
        port.run_daily_action = action
        workflow = DailyWorkflow(port)
        with self.assertRaises(Cancelled):
            workflow.run(self.options())
        self.assertEqual(len(workflow.results), 7)
        self.assertNotIn(('route', 'route'), port.events)

    def test_old_unconditional_photo_setting_is_dropped_without_enabling_it_elsewhere(self):
        options = migrate_daily_options({'每日拍照': True, '自动朝夕心愿': False, '星海拾光': True,
                                         '单条路线最大分钟': 7})
        self.assertNotIn('每日拍照', options)
        self.assertFalse(options['朝夕心愿'])
        self.assertEqual(options['单条路线最大分钟'], 7)
        self.assertFalse(options['每日结束后跑图'])

    def test_old_custom_flows_never_execute_and_automatic_checks_ignore_old_toggles(self):
        port = Port()
        DailyWorkflow(port).run({**self.options(), '每日前自定义流程': True, '每日后自定义流程': True,
                                 '每周幻境': False, '检查活跃能量': False})
        actions = [action for kind, action in port.events if kind == 'daily']
        self.assertNotIn('pre_flow', actions)
        self.assertNotIn('post_flow', actions)
        self.assertIn('auto_weekly', actions)
        self.assertIn('energy_check', actions)

    def test_removed_options_are_migrated_from_current_version_files(self):
        import json
        import tempfile
        from pathlib import Path
        from nuannuan.config import ROOT
        from nuannuan.daily.workflow import DAILY_DEFAULTS, migrate_daily_file
        removed = ['检查活跃能量', '家园日常', '每周幻境', '奇迹之冠', '素材激化',
                   '祝福闪光幻境', '魔物试炼', '每日前自定义流程', '每日后自定义流程']
        self.assertFalse(set(DAILY_DEFAULTS) & set(removed))
        old = {**self.options(), **dict.fromkeys(removed, True), '_enabled': False}
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as directory:
            path = Path(directory)/'DailyTask.json'
            path.write_text(json.dumps(old), encoding='utf-8')
            migrate_daily_file(path)
            migrated = json.loads(path.read_text(encoding='utf-8'))
            self.assertFalse(set(migrated) & set(removed))
            self.assertEqual(migrated['接续跑图路线'], 'route')
            self.assertTrue(migrated['每日结束后跑图'])
            self.assertFalse(migrated['_enabled'])
            self.assertEqual(len(list((path.parent/'migrations').glob('*.json'))), 1)
            migrate_daily_file(path)
            self.assertEqual(len(list((path.parent/'migrations').glob('*.json'))), 1)

    def test_partial_challenge_and_execution_failures_do_not_run_post_flow(self):
        port = Port()
        port.status = 'partial'
        port.partial_unsupported = False
        port.validate_daily_flow = lambda action: None
        results = DailyWorkflow(port).run({**self.options(), '每日后自定义流程': True})
        self.assertNotIn(('daily', 'post_flow'), port.events)
        self.assertNotIn(('route', 'route'), port.events)
        self.assertEqual(results[-1]['status'], 'skipped')

    def test_whimbox_daily_order_and_finish_after_follow_route(self):
        port = Port()
        events = []
        port.workflow_progress = lambda label, state, message: events.append((label, state))
        options = {**self.options(), '美鸭梨挖掘': True, '奇迹之旅奖励': True}
        results = DailyWorkflow(port).run(options)
        names = [result['name'] for result in results]
        expected = ['进入游戏', '检查活跃能量', '美鸭梨挖掘', '家园日常', '每周幻境', '朝夕心愿',
                    '活跃能量处理', '星光结晶收集', '星海拾光', '奇迹之冠', '奇迹之旅奖励', '每日后跑图 · route', '每日结束操作']
        self.assertEqual(names, expected)
        self.assertEqual([label for label, state in events if state == 'running'], expected)
        self.assertEqual([label for label, state in events if state == 'succeeded'], expected)

    def test_failed_daily_never_executes_finish_actions(self):
        port = Port()
        port.status = 'failed'
        results = DailyWorkflow(port).run(self.options())
        self.assertNotIn(('daily', 'finish_daily'), port.events)
        self.assertEqual(results[-1]['name'], '每日结束操作')
        self.assertEqual(results[-1]['status'], 'skipped')

    def test_identify_only_has_no_start_energy_crystal_or_finish_actions(self):
        port = Port()
        DailyWorkflow(port).run({**self.options(), '运行模式': '只识别'})
        self.assertEqual(port.events, [('daily', 'auto_wish'), ('daily', 'starsea')])
