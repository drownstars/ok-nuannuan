"""Desktop runtime with the framework's optional remote-control feature removed."""
from ok import OK


def remove_control_option(app):
    key = 'Enable MCP Server'
    configuration = app.global_config.configs['Basic Options']
    option = app.global_config.config_options['Basic Options']
    configuration.pop(key, None)
    configuration.default.pop(key, None)
    option.default_config.pop(key, None)
    for metadata in [option.config_type, option.config_description]:
        if metadata is not None:
            metadata.pop(key, None)


class LocalApp(OK):
    def __init__(self, config):
        super().__init__(config)
        remove_control_option(self)
        from nuannuan.core.startup import install_launch_support
        install_launch_support(self)
        from nuannuan.core.run_control import install_run_control
        install_run_control(self)

    def start_mcp_server(self):
        # OK.start invokes this hook for every app, including desktop-only apps.
        return None

    def set_mcp_enabled(self, enabled):
        if enabled:
            raise RuntimeError('此应用已移除开发控制接口')
