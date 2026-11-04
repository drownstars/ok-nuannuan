import importlib
import math
import unittest
from types import SimpleNamespace

from nuannuan.config import make_config


class TaskTests(unittest.TestCase):
    def test_registered_tasks_construct_before_capture_starts(self):
        config = make_config()
        registered = {name for _, name in config['onetime_tasks']}
        self.assertEqual(registered, {'DailyTask', 'RouteTask', 'CaptureCheckTask', 'OperationTask'})
        self.assertEqual(len(config['trigger_tasks']), 6)
        for module, name in config['onetime_tasks'] + config['trigger_tasks']:
            task_class = getattr(importlib.import_module(module), name)
            task = task_class(SimpleNamespace(scene=None), None)
            self.assertTrue(task.name)
            self.assertTrue(task.description)
        self.assertNotIn('mcp', config)

    def test_assist_interval_rejects_invalid_or_too_fast_values(self):
        from nuannuan.tasks.daily_tasks import AutoPickupTask
        task = AutoPickupTask(SimpleNamespace(scene=None), None)
        for value in [-1, 0, 0.01, math.nan, math.inf, 'invalid']:
            self.assertTrue(task.validate_config('操作间隔（秒）', value))
        self.assertFalse(task.validate_config('操作间隔（秒）', 0.7))

    def test_global_dropdown_defaults_are_visible_choices(self):
        for option in make_config()['global_configs']:
            for key, spec in (option.config_type or {}).items():
                if spec.get('type') == 'drop_down':
                    self.assertIn(option.default_config[key], spec['options'], (option.name, key))
