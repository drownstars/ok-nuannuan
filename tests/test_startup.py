import unittest
from pathlib import Path

from nuannuan.daily import AutomationError


class LaunchPort:
    def __init__(self,ready=False,button=True):
        self.ready,self.button,self.events,self.now=ready,button,[],0.
    def game_ready(self):return self.ready
    def resolve_path(self):return Path('D:/Official/launcher.exe')
    def launch(self,path):self.events.append(('launch',str(path)))
    def click_launch(self):
        self.events.append('click')
        if self.button:self.ready=True
        return self.button
    def stage(self,name):self.events.append(name)
    def sleep(self,seconds):self.now+=seconds
    def clock(self):return self.now
    def close(self):self.events.append('cleanup')


class StartupTests(unittest.TestCase):
    def test_app_controller_launches_selected_daily_before_framework_connection(self):
        from types import SimpleNamespace
        from unittest.mock import patch, Mock
        from nuannuan.startup import install_launch_support
        task = type('DailyTask', (), {})()
        task.info_set = Mock()
        original = Mock(return_value=True)
        controller = SimpleNamespace(_do_start=original)
        app = SimpleNamespace(_app=SimpleNamespace(start_controller=controller),
                              task_executor=SimpleNamespace(current_task=None),
                              global_config=SimpleNamespace(get_config=lambda name: {'自动启动游戏': True}))
        with patch('nuannuan.startup.LaunchRuntime') as runtime, patch('nuannuan.startup.GameLaunchSequence') as sequence:
            install_launch_support(app)
            wrapped = controller._do_start
            install_launch_support(app)
            self.assertEqual(controller._do_start, wrapped)
            self.assertTrue(controller._do_start(task, True))
            runtime.assert_called_once_with(app, task)
            sequence.return_value.run.assert_called_once()
            original.assert_called_once_with(task, True)
            original.reset_mock()
            sequence.reset_mock()
            sequence.return_value.run.side_effect = AutomationError('权限不匹配')
            self.assertFalse(controller._do_start(task))
            original.assert_not_called()
            task.info_set.assert_called_with('启动状态', '权限不匹配')

    def test_existing_game_is_not_relaunched(self):
        from nuannuan.startup import GameLaunchSequence
        port=LaunchPort(ready=True)
        result=GameLaunchSequence(port,clock=port.clock).run()
        self.assertEqual(result['status'],'skipped')
        self.assertFalse(any(isinstance(item,tuple) for item in port.events))

    def test_launch_and_single_confirmed_button_then_game_ready(self):
        from nuannuan.startup import GameLaunchSequence
        port=LaunchPort()
        result=GameLaunchSequence(port,clock=port.clock).run()
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(port.events.count('click'),1)
        self.assertLess(next(i for i,item in enumerate(port.events) if isinstance(item,tuple)),port.events.index('click'))
        self.assertEqual(port.events[-1],'cleanup')

    def test_clicked_button_with_no_game_does_not_click_repeatedly(self):
        from nuannuan.startup import GameLaunchSequence
        port=LaunchPort()
        def click():port.events.append('click');return True
        port.click_launch=click
        with self.assertRaisesRegex(AutomationError,'超时|未.*启动'):
            GameLaunchSequence(port,clock=port.clock,timeout=3).run()
        self.assertEqual(port.events.count('click'),1)
        self.assertEqual(port.events[-1],'cleanup')

    def test_missing_launcher_fails_before_starting_a_process(self):
        from nuannuan.startup import GameLaunchSequence
        port=LaunchPort()
        port.resolve_path=lambda:None
        with self.assertRaises(AutomationError):GameLaunchSequence(port,clock=port.clock).run()
        self.assertFalse(any(isinstance(item,tuple) for item in port.events))

    def test_cancellation_preserves_no_more_inputs(self):
        from nuannuan.startup import GameLaunchSequence
        class Cancelled(Exception):pass
        port=LaunchPort(button=False)
        def cancel(seconds):raise Cancelled()
        port.sleep=cancel
        with self.assertRaises(Cancelled):GameLaunchSequence(port,clock=port.clock).run()
        self.assertEqual(port.events[-1],'cleanup')
