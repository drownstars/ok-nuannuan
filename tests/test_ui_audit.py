import unittest


class UIAuditTests(unittest.TestCase):
    def test_visible_operations_and_script_entries_cover_every_registered_tool(self):
        from tools.ui_audit import audit_inventory
        from nuannuan.tasks.tool_runner import TOOLS
        inventory = audit_inventory()
        self.assertEqual(set(inventory['operations']+inventory['scripts']), set(TOOLS))
        self.assertEqual(inventory['unsupported_wishes'], ['升级祝福闪光', '制作服装', '流星 / 椰果 / 碎片 / 泡泡合影'])
