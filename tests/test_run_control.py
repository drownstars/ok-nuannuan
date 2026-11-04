import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class Task:
    name = '每日任务'
    def __init__(self): self.enabled = False; self.paused = False; self.info = {}; self.disabled = 0
    def disable(self): self.enabled = False; self.disabled += 1
    def unpause(self): self.paused = False
    def info_set(self, key, value): self.info[key] = value


class RunControlTests(unittest.TestCase):
    def test_slash_listener_stops_only_an_active_task_and_is_closed(self):
        from unittest.mock import Mock, patch
        control, executor, events = self.make()
        task = Task()
        with patch('pynput.keyboard.Listener') as listener:
            control.install_hotkey()
            pressed = listener.call_args.kwargs['on_press']
            control.reserve(task)
            pressed(SimpleNamespace(char='a'))
            self.assertFalse(control.cancel_event.is_set())
            pressed(SimpleNamespace(char='/'))
            self.assertTrue(control.cancel_event.is_set())
            control.close()
            listener.return_value.stop.assert_called_once()

    def test_pause_button_resumes_a_task_paused_from_its_task_card(self):
        control, executor, events = self.make()
        task = Task()
        task.paused = True
        control.reserve(task)
        executor.start = lambda: events.append('resume')
        executor.pause = lambda: events.append('pause')
        control.pause_or_resume()
        self.assertFalse(task.paused)
        self.assertEqual(events, ['resume'])

    def test_installed_controller_rejects_second_task_and_cleanup_releases_owner(self):
        from nuannuan.core.run_control import install_run_control
        calls = []
        first, second = Task(), Task()
        first.run = lambda: calls.append('run')
        second.run = lambda: calls.append('second')
        def start(task, exit_after):
            calls.append(('start', task))
            task.enabled = True
            return True
        executor = SimpleNamespace(onetime_tasks=[first, second], current_task=None, trigger_tasks=[],
                                   paused=False, interaction=SimpleNamespace(release_all=lambda: calls.append('release')))
        controller = SimpleNamespace(_do_start=start)
        app = SimpleNamespace(task_executor=executor, _app=SimpleNamespace(start_controller=controller))
        control = install_run_control(app)
        self.assertIs(app._app.run_control, control)
        self.assertTrue(controller._do_start(first))
        self.assertFalse(controller._do_start(second))
        self.assertFalse(second.enabled)
        first.run()
        self.assertFalse(control.busy)
        self.assertEqual(calls[-2:], ['run', 'release'])
        self.assertTrue(controller._do_start(second))

    def test_failed_task_before_run_is_reconciled_and_stop_wakes_launcher_sleep(self):
        import threading
        from nuannuan.core.startup import LaunchRuntime
        from nuannuan.core.errors import AutomationError
        control, executor, events = self.make()
        task = Task()
        control.reserve(task)
        control.starting = True
        control.reconcile()
        self.assertTrue(control.busy)
        control.starting = False
        control.reconcile()
        self.assertFalse(control.busy)
        control.reserve(task)
        runtime = LaunchRuntime(SimpleNamespace(run_control=control, exit_event=threading.Event()), task)
        control.stop()
        with self.assertRaisesRegex(AutomationError, '已停止'): runtime.sleep(60)

    def make(self):
        from nuannuan.core.run_control import RunControl
        events = []
        executor = SimpleNamespace(current_task=None, trigger_tasks=[], paused=False,
                                   interaction=SimpleNamespace(cancel=lambda: events.append('release')))
        app = SimpleNamespace(task_executor=executor)
        return RunControl(app), executor, events

    def test_single_owner_and_stop_during_launcher_wait(self):
        control, executor, events = self.make()
        first, second = Task(), Task()
        self.assertTrue(control.reserve(first))
        self.assertFalse(control.reserve(second))
        control.stop()
        self.assertTrue(control.cancel_event.is_set())
        self.assertEqual(first.disabled, 1)
        self.assertEqual(events, ['release'])
        self.assertTrue(control.busy)
        control.finish(first)
        self.assertFalse(control.busy)
        self.assertTrue(control.reserve(second))
        self.assertFalse(control.cancel_event.is_set())

    def test_stop_keeps_helper_preferences_and_cannot_finish_other_owner(self):
        control, executor, events = self.make()
        assist = SimpleNamespace(enabled=True)
        executor.trigger_tasks = [assist]
        first, second = Task(), Task()
        control.reserve(first)
        control.finish(second)
        self.assertTrue(control.busy)
        control.stop()
        self.assertTrue(assist.enabled)

    def test_helpers_are_suspended_while_busy_and_when_game_not_foreground(self):
        from nuannuan.core.run_control import assist_allowed
        control, executor, events = self.make()
        executor._nuannuan_run_control = control
        executor.interaction.hwnd_window = SimpleNamespace(is_foreground=lambda: True)
        self.assertTrue(assist_allowed(executor))
        control.reserve(Task())
        self.assertFalse(assist_allowed(executor))
        control.finish(control.task)
        executor.interaction.hwnd_window.is_foreground = lambda: False
        self.assertFalse(assist_allowed(executor))

    def test_device_migration_is_once_and_preserves_capture_and_other_fields(self):
        from nuannuan.core.run_control import migrate_runtime_file
        with tempfile.TemporaryDirectory(dir='.cache/tmp') as directory:
            path = Path(directory)/'devices.json'
            old = {'interaction': 'PostMessage', 'capture': 'WGC', 'selected_exe': 'game.exe'}
            path.write_text(json.dumps(old), encoding='utf-8')
            migrate_runtime_file(path)
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['interaction'], 'WhimboxInteraction')
            self.assertEqual(data['capture'], 'WGC')
            self.assertEqual(data['selected_exe'], 'game.exe')
            self.assertEqual(len(list((path.parent/'migrations').glob('*'))), 1)
            migrate_runtime_file(path)
            self.assertEqual(len(list((path.parent/'migrations').glob('*'))), 1)
