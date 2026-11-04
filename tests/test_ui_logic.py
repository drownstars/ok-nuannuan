import importlib
import unittest
from types import SimpleNamespace

from nuannuan.config import make_config


class UILogicTests(unittest.TestCase):
    def test_other_tools_card_is_removed_but_operations_have_internal_executor(self):
        config = make_config()
        visible = []
        for module, name in config['onetime_tasks']:
            task = getattr(importlib.import_module(module), name)(SimpleNamespace(scene=None), None)
            if task.visible: visible.append(task.name)
        self.assertNotIn('其他功能工具', visible)
        self.assertEqual(len(visible), 3)

    def test_routes_tab_is_after_tools_and_map_mask(self):
        names = [name for _, name in make_config()['custom_tabs']]
        self.assertIn('MapMaskTab', names)
        self.assertIn('ScriptTab', names)
        self.assertEqual(names[-1], 'RouteTab')

    def test_step_list_preserves_enabled_state_and_validates_dependencies(self):
        from nuannuan.ui.logic import FlowSteps
        steps = FlowSteps([{'type': 'path', 'script_name': '星海拾光_更改音乐', 'enabled': False}])
        steps.add('macro', '朝夕心愿_战斗宏')
        steps.move(1, -1)
        self.assertEqual(steps.items[0]['type'], 'macro')
        self.assertFalse(steps.items[1]['enabled'])
        steps.remove([0])
        self.assertEqual(len(steps.items), 1)

    def test_operation_groups_do_not_expose_scripts_or_unrelated_fields(self):
        from nuannuan.ui.logic import OPERATION_GROUPS, operation_fields
        values = [name for names in OPERATION_GROUPS.values() for name in names]
        self.assertNotIn('录制宏', values)
        self.assertNotIn('自定义流程', values)
        self.assertEqual(operation_fields('检查活跃能量'), ())
        self.assertEqual(operation_fields('页面跳转'), ('目标页面',))
