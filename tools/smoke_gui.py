"""Application-local GUI verification; no desktop automation or game input."""
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launch import build_app, prepare


def main():
    prepare(silent=True)
    from PySide6.QtCore import QTimer, Qt
    from nuannuan.home import HomeTab
    from nuannuan.route_tab import RouteTab
    from nuannuan.tasks import DailyTask, RouteTask, CaptureCheckTask, OperationTask
    from nuannuan.feature_tab import FeatureTab
    from nuannuan.script_tab import ScriptTab
    from nuannuan.map_mask_tab import MapMaskTab

    output = ROOT / 'logs/verification'
    output.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'game_input_sent': False}
    (output / 'gui.json').write_text(json.dumps(result), encoding='utf-8')
    app = build_app()

    def verify():
        try:
            window = app.app.main_window
            assert window is not None and window.isVisible(), 'Main window did not become visible'
            assert not window.windowIcon().isNull(), 'App icon did not load'
            assert window.windowIcon().pixmap(64, 64).save(str(output/'app-window-icon.png'))
            from nuannuan.desktop_ui import apply_desktop_layout
            apply_desktop_layout(app, window)
            home = window.findChild(HomeTab)
            assert home is not None, 'Home page was not created'
            home.refresh()
            assert not home.pause_button.isEnabled() and not home.stop_button.isEnabled()
            assert home.daily_button.isEnabled()
            window.switchTo(home)
            app.app.app.processEvents()
            assert window.grab().save(str(output / 'home.png'))
            assert len(app.task_executor.onetime_tasks) == 4
            assert len(app.task_executor.trigger_tasks) == 6
            assert app._mcp_server is None
            assert 'mcp' not in app.config
            assert 'Enable MCP Server' not in app.global_config.configs['Basic Options']
            assert 'Enable MCP Server' not in app.global_config.config_options['Basic Options'].default_config
            try:
                app.set_mcp_enabled(True)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Removed control interface can still be enabled')

            # Exercise the real task-card Start signal up to StartController.
            # Intercept dispatch so smoke verification never operates a game.
            tab = window.onetime_tab
            assert len(tab.card_widgets) == 3
            assert not any(card.task.__class__ is OperationTask for card in tab.card_widgets)
            controller = app.app.start_controller
            original_start = controller.start
            dispatched = []
            try:
                controller.start = lambda task=None, **kwargs: dispatched.append(task)
                for task_class in [DailyTask, RouteTask, CaptureCheckTask]:
                    card = next(card for card in tab.card_widgets if card.task.__class__ is task_class)
                    card.start_button.click()
                    assert dispatched[-1] is card.task, 'Task card did not dispatch its registered task'
                routes = window.findChild(RouteTab)
                assert routes is not None and routes.table.rowCount() == 24
                assert routes.route_combo.count() == 24
                routes.route_combo.setCurrentText('星海拾光_更改音乐')
                from types import SimpleNamespace
                from unittest.mock import patch
                routes.start_button.click()
                assert dispatched[-1].__class__ is RouteTask
                assert dispatched[-1].config['路线名称'] == '星海拾光_更改音乐'
                daily = app.task_executor.get_task_by_class(DailyTask)
                removed = {'检查活跃能量', '家园日常', '每周幻境', '奇迹之冠', '素材激化',
                           '祝福闪光幻境', '魔物试炼', '每日前自定义流程', '每日后自定义流程'}
                assert not removed.intersection(daily.config)
                assert not removed.intersection(daily.default_config)
                previous_follow = daily.config['每日结束后跑图'], daily.config['接续跑图路线']
                try:
                    routes.follow_button.click()
                    assert daily.config['每日结束后跑图'] and daily.config['接续跑图路线'] == '星海拾光_更改音乐'
                finally:
                    daily.config['每日结束后跑图'], daily.config['接续跑图路线'] = previous_follow
                # Exercise the editor against a separate temporary library, not user routes.
                import tempfile
                from nuannuan.route_store import RouteStore
                from nuannuan.route_editor import RouteEditor
                with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as directory:
                    store = RouteStore(directory)
                    store.import_records([routes.store.get_data('星海拾光_更改音乐')])
                    editor = RouteEditor(store, '星海拾光_更改音乐', window)
                    editor.show()
                    app.app.app.processEvents()
                    assert editor.grab().save(str(output / 'route-editor.png'))
                    editor.name_edit.setText('界面编辑验证')
                    editor.target_edit.setText('珠链蝶')
                    editor.count_spin.setValue(3)
                    editor.points.item(1, 1).setText('12345.5')
                    editor.add_point()
                    assert editor.points.rowCount() == 3
                    editor.points.selectRow(2)
                    editor.remove_points()
                    editor.save()
                    assert editor.saved_name == '界面编辑验证'
                    assert store.get_data(editor.saved_name)['points'][1]['position'][0] == 12345.5
                    assert store.get_data(editor.saved_name)['info']['target'] == '珠链蝶'
                    assert store.get_data(editor.saved_name)['info']['count'] == 3
                    store.delete(editor.saved_name)
                    from nuannuan.routes import RouteCatalog
                    assert not RouteCatalog(store.root).inventory()
                    editor.deleteLater()
            finally:
                controller.start = original_start
            window.switchTo(tab)
            daily_card = next(card for card in tab.card_widgets if card.task.__class__ is DailyTask)
            daily_card.setExpand(True)
            assert not removed.intersection(daily_card.config_keys)
            from PySide6.QtTest import QTest
            QTest.qWait(350)
            app.app.app.processEvents()
            assert window.grab().save(str(output / 'tasks.png'))
            window.switchTo(routes)
            app.app.app.processEvents()
            assert window.grab().save(str(output / 'routes.png'))
            features = window.findChild(FeatureTab)
            scripts = window.findChild(ScriptTab)
            mask = window.findChild(MapMaskTab)
            assert features is not None and scripts is not None and mask is not None
            # Exercise the unchanged upstream provider with fixtures, never live accounts.
            from tests.test_pearpal_original import FakePearPalClient, FakePearPalUserClient
            from nuannuan._pearpal.pearpal_provider import OfficialPearPalProvider
            mask.official.provider = OfficialPearPalProvider(enabled=True, client=FakePearPalClient(),
                user_client=FakePearPalUserClient(), background=False, auth_background=False, refresh_background=False)
            mask.official.load_button.click()
            assert len(mask.official.points()) == 4
            from nuannuan._pearpal.pearpal_auth import PearPalCredentials
            mask.official.provider.authenticate(PearPalCredentials('abcDEF0123456789', '12405094'))
            mask.official.poll()
            assert len(mask.official.points()) == 1
            mask.official.hide_collected.setChecked(False)
            assert len(mask.official.points()) == 4
            mask.official.disconnect_button.click()
            assert not mask.official.provider.get_user_status()['authenticated']
            mask.official.hide_collected.setChecked(True)
            # The real QtWebEngine login view is built against an empty test page,
            # isolated from the user's persistent profile and official accounts.
            from nuannuan.pearpal_login import PearPalLogin
            import tempfile
            with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as browser_dir:
                with patch('nuannuan.pearpal_login.ROOT', Path(browser_dir)), patch('nuannuan.pearpal_login.get_pearpal_region',
                    return_value=SimpleNamespace(page_url='about:blank')):
                    login_view = PearPalLogin(mask.official.provider, 'cn', window)
                    login_view.show()
                    QTest.qWait(300)
                    assert login_view.web.page() is not None
                    assert login_view.parentWidget() is None
                    assert not login_view.testAttribute(Qt.WA_TranslucentBackground)
                    login_view.dispose()
                    from PySide6.QtCore import QCoreApplication, QEvent
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                    QTest.qWait(300)
            # Validate the real running window without enabling any registered game task.
            from nuannuan.run_dialog import attach_run_dialog
            from types import SimpleNamespace
            dialog = attach_run_dialog(app, window)
            sample = SimpleNamespace(name='每日任务 · 界面验证', enabled=True, paused=False, running=True,
                                     info={'当前步骤': '开启材料追踪', '目标材料': '珠链蝶'})
            sample.disable = lambda: setattr(sample, 'enabled', False)
            sample.unpause = lambda: setattr(sample, 'paused', False)
            control = app.run_control
            previous_last = control.last_task
            mask.enable_switch.setChecked(True)
            assert control.reserve(sample)
            home.refresh()
            assert not home.daily_button.isEnabled() and not home.daily_settings_button.isEnabled()
            assert not home.pause_button.isEnabled() and home.stop_button.isEnabled()
            assert '开启材料追踪' in home.result_label.toPlainText()
            control.state = '执行中'
            control.record('切换能力', 'succeeded', '捕虫')
            control.record('开启材料追踪', 'running', '珠链蝶')
            dialog.refresh()
            home.refresh()
            assert dialog.isVisible() and home.stop_button.isEnabled()
            assert not mask.enable_switch.isChecked() and not mask.controller.enabled
            assert '珠链蝶' in dialog.log.toPlainText()
            assert dialog.grab().save(str(output/'running-window.png'))
            window.switchTo(home)
            app.app.app.processEvents()
            QTest.qWait(100)
            assert home.isVisible()
            assert window.grab().save(str(output/'home-running.png'))
            dialog.stop_button.click()
            assert control.cancel_event.is_set() and not sample.enabled
            dialog.refresh()
            assert not dialog.stop_button.isEnabled()
            home.refresh()
            assert not home.stop_button.isEnabled() and not home.daily_button.isEnabled()
            sample.running = False
            control.finish(sample)
            control.last_task = previous_last
            control.events.clear()
            dialog.hide()
            indexes = [window.stackedWidget.indexOf(page) for page in [tab, mask, features, scripts, routes]]
            assert indexes == sorted(indexes) and len(set(indexes)) == 5, indexes
            from nuannuan.ui_actions import open_extra_settings
            open_extra_settings(features)
            from PySide6.QtTest import QTest
            QTest.qWait(350)
            assert next(card for card in window.setting_tab.config_groups if card.has_key('活跃能量用途')).isExpand
            assert window.grab().save(str(output / 'extra-settings.png'))
            window.switchTo(features)
            app.app.app.processEvents()
            assert window.grab().save(str(output / 'features.png'))
            original_start = controller.start
            tool_task = app.task_executor.get_task_by_class(OperationTask)
            original_config = dict(tool_task.config)
            try:
                controller.start = lambda task=None, **kwargs: dispatched.append(task)
                from types import SimpleNamespace
                from unittest.mock import patch
                with patch('nuannuan.ui_actions.psutil.process_iter', return_value=[
                    SimpleNamespace(info={'name': 'X6Game-Win64-Shipping.exe'})
                ]):
                    features.buttons['检查活跃能量'].click()
                assert dispatched[-1] is tool_task
                assert tool_task.config['工具功能'] == '检查活跃能量'
                assert tool_task._pending_options['工具功能'] == '检查活跃能量'
                from nuannuan.ui_logic import FlowSteps
                assert not hasattr(scripts, 'flow_slot') and not hasattr(scripts, 'daily_switch')
                extra = app.global_config.get_config('扩展功能设置')
                assert '每日前流程JSON' not in extra and '每日后流程JSON' not in extra
                assert extra['活跃能量用途'] in {'素材激化', '祝福闪光幻境', '魔物试炼'}
                assert extra['每日结束操作'] in {'保持游戏', '关闭游戏', '关闭游戏和助手'}
                assert isinstance(extra['自动启动游戏'], bool)
                assert controller._nuannuan_launch_support
                scripts.section_combo.setCurrentText('流程编排')
                scripts.model = FlowSteps([{'type': 'path', 'script_name': '星海拾光_更改音乐', 'enabled': True}])
                scripts.render_steps()
                assert len(scripts.read_steps().validate()) == 1
                assert scripts.save_flow()
                assert len(json.loads(tool_task.config['流程JSON'])) == 1
                scripts.steps.selectRow(0)
                scripts.add_kind.setCurrentText('宏 / 乐谱')
                scripts.add_step()
                assert scripts.steps.rowCount() == 2
                scripts.steps.selectRow(1)
                scripts.move_step(-1)
                assert scripts.read_steps().items[0]['type'] == 'macro'
                scripts.steps.selectRow(0)
                scripts.remove_steps()
                assert scripts.steps.rowCount() == 1
                scripts._dirty = False
                window.switchTo(scripts)
                app.app.app.processEvents()
                assert window.grab().save(str(output / 'scripts.png'))
            finally:
                controller.start = original_start
                for key, value in original_config.items(): tool_task.config[key] = value
                tool_task._pending_options = None
                tool_task._dispatch_until = 0
            window.switchTo(mask)
            app.app.app.processEvents()
            assert mask.points and mask.table.rowCount() > 0
            mapped = mask.preview.transform().mapRect(mask.preview.scene().sceneRect())
            assert max(mapped.width(), mapped.height()) > min(mask.preview.viewport().width(), mask.preview.viewport().height())*.8
            assert not mask.controller.enabled
            assert window.grab().save(str(output / 'map-mask.png'))
            # Import into a temporary point library; real user data is preserved.
            from nuannuan.map_mask import PointLibrary, Marker
            import tempfile
            with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as directory:
                original_library = mask.library
                try:
                    mask.library = PointLibrary(Path(directory)/'saved-points.json')
                    source = Path(directory)/'points.json'
                    source.write_text(json.dumps([{'id': 'gui-test', 'name': '界面验证点', 'map_name': 'starsea',
                                                   'image_x': 1500, 'image_y': 2000}]), encoding='utf-8')
                    assert mask.import_points(source) == 1
                    assert len(mask.library.points()) == 1
                finally:
                    mask.library = original_library
                    mask.refresh_points()
            mask.enable_switch.setChecked(True)
            QTest.qWait(150)
            assert mask.controller.enabled and not mask.controller.overlay.isVisible()
            mask.enable_switch.setChecked(False)
            assert not mask.controller.enabled
            overlay = mask.controller.overlay
            assert overlay.testAttribute(Qt.WA_TransparentForMouseEvents)
            assert overlay.windowFlags() & Qt.WindowTransparentForInput
            overlay.resize(960, 540)
            overlay.set_markers([Marker('test', '遮罩渲染验证', 'route', 960, 540)])
            pixmap = overlay.grab()
            assert pixmap.save(str(output/'map-overlay-render.png'))
            rendered = pixmap.toImage()
            assert rendered.pixelColor(rendered.width()//2, rendered.height()//2).alpha() > 0
            assert rendered.pixelColor(0, 0).alpha() == 0
            window.switchTo(home)
            from tools.ui_audit import audit_pages
            audit = audit_pages(app, window)
            (output/'ui-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
            assert audit['passed']
            window.switchTo(home)
            app.app.app.processEvents()
            from qfluentwidgets import InfoBar
            for notification in window.findChildren(InfoBar):
                notification.close()
            QTest.qWait(150)
            home.refresh()
            assert window.grab().save(str(output/'home.png'))
            full_size = window.size()
            window.resize(1100, 760)
            app.app.app.processEvents()
            QTest.qWait(150)
            assert window.grab().save(str(output/'home-compact.png'))
            assert home.daily_button.isVisible() and home.daily_settings_button.isVisible()
            assert home.horizontalScrollBar().maximum() == 0
            home_scroll_range = home.verticalScrollBar().maximum()
            assert home_scroll_range == 0
            from qfluentwidgets import Theme, setTheme, qconfig
            original_theme = qconfig.themeMode.value
            try:
                setTheme(Theme.LIGHT, save=False)
                app.app.app.processEvents()
                QTest.qWait(200)
                light_color = home.view.grab().toImage().pixelColor(4, 4)
                assert light_color.lightness() > 200, 'Light theme lost its page background'
                assert qconfig.get(qconfig.themeColor).name() == '#9b6d99'
                assert home.view.grab().save(str(output/'home-preview-light.png'))
                assert window.grab().save(str(output/'home-light.png'))
                setTheme(Theme.DARK, save=False)
                app.app.app.processEvents()
                QTest.qWait(200)
                dark_color = home.view.grab().toImage().pixelColor(4, 4)
                assert dark_color.lightness() < 70, 'Dark theme left a white page background'
                assert qconfig.get(qconfig.themeColor).name() == '#9b6d99'
                assert home.view.grab().save(str(output/'home-preview-dark.png'))
                assert window.grab().save(str(output/'home-dark.png'))
                assert home.horizontalScrollBar().maximum() == 0
                assert home.verticalScrollBar().maximum() == 0
            finally:
                setTheme(original_theme, save=False)
                app.app.app.processEvents()
            window.resize(full_size)
            result.update({'passed': True, 'app_icon': True, 'task_cards': 3, 'registered_onetime': 4, 'assist_cards': 6,
                           'route_rows': 24, 'ready_routes': 24, 'route_panel_dispatch': True,
                           'operation_dispatch': True, 'flow_save': True, 'visual_flow_edit': True,
                           'navigation_order': indexes, 'map_point_import': True, 'map_overlay_render': True,
                           'map_overlay_click_through': True, 'map_overlay_hidden_without_game': True,
                           'route_editor_save': True, 'daily_follow_setting': True,
                           'task_start_dispatch': True, 'control_interface_removed': True,
                           'daily_options_simplified': True, 'daily_flow_options_removed': True,
                           'foreground_input_configured': app.config['windows']['interaction'][0].__name__ == 'WhimboxInteraction',
                           'all_operation_dispatches': len(audit['operations']), 'script_entries': len(audit['scripts']),
                           'running_window': True, 'stop_button': True, 'map_disabled_for_task': True,
                           'pearpal_original_provider': True, 'pearpal_login_window': True,
                           'pearpal_collected_filter': True, 'pearpal_disconnect': True,
                           'home_deduplicated': True, 'home_task_state_controls': True,
                           'home_compact_scroll_range': home_scroll_range,
                           'home_more_menu_actions': True, 'home_light_dark_themes': True,
                           'status': home.status_label.text(), 'actual_game_execution': 'not verified'})
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            (output / 'gui.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            app.app.app.quit()

    QTimer.singleShot(2500, verify)
    QTimer.singleShot(30000, app.app.app.quit)
    try:
        app.start()
    finally:
        app.quit()
    if not result['passed']:
        raise RuntimeError(result.get('error', 'GUI verification timed out'))


if __name__ == '__main__':
    main()
