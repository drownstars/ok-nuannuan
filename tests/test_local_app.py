import unittest
from types import SimpleNamespace

from nuannuan.config import make_config


class LocalAppTests(unittest.TestCase):
    def test_app_config_has_no_control_server_option(self):
        self.assertNotIn('mcp', make_config())
        with self.assertRaises(TypeError): make_config(mcp=True)

    def test_framework_control_option_is_removed_from_data_and_gui_metadata(self):
        from nuannuan.core.local_app import remove_control_option
        class Configuration(dict): pass
        config = Configuration({'Enable MCP Server': True, 'Start/Stop': 'F9'})
        config.default = dict(config)
        option = SimpleNamespace(default_config=dict(config), config_type={'Enable MCP Server': {'type': 'mcp_server'}},
                                 config_description={'Enable MCP Server': 'control'})
        app = SimpleNamespace(global_config=SimpleNamespace(configs={'Basic Options': config},
                                                           config_options={'Basic Options': option}))
        remove_control_option(app)
        self.assertNotIn('Enable MCP Server', config)
        self.assertNotIn('Enable MCP Server', config.default)
        self.assertNotIn('Enable MCP Server', option.default_config)
        self.assertNotIn('Enable MCP Server', option.config_type)
        self.assertNotIn('Enable MCP Server', option.config_description)
        self.assertEqual(config['Start/Stop'], 'F9')

    def test_runtime_cannot_start_or_enable_control_server(self):
        from nuannuan.core.local_app import LocalApp
        app = LocalApp.__new__(LocalApp)
        app.config = {'mcp': {'enabled': True}}
        app._mcp_server = None
        app.start_mcp_server()
        self.assertIsNone(app._mcp_server)
        with self.assertRaises(RuntimeError): app.set_mcp_enabled(True)
        self.assertIsNone(app._mcp_server)
