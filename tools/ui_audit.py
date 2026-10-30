"""Exercise actual desktop controls with task dispatch and external actions intercepted."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def capture_desktop_window(window, output):
    """Capture this verified process's GUI through ok-script, including native chrome."""
    import os
    import sys
    import threading
    import cv2
    import win32process
    from PySide6.QtTest import QTest
    from ok.device.capture import HwndWindow, update_capture_method
    hwnd = int(window.winId())
    assert win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid()
    class Options(dict): pass
    options = Options({'Mute Game while in Background': False, 'Auto Resize Game Window': False})
    manager = SimpleNamespace(config={'selected_exe': sys.executable, 'selected_hwnd': hwnd},
                              capture_method=None, executor=None, get_preferred_device=lambda: None)
    stop = threading.Event()
    target = HwndWindow(stop, window.windowTitle(), sys.executable,
                        global_config=SimpleNamespace(get_config=lambda name: options), device_manager=manager)
    capture = None
    try:
        capture = update_capture_method({'capture_method': ['WGC']}, None, target, stop)
        manager.capture_method = capture
        assert capture is not None, 'GUI WGC capture unavailable'
        QTest.qWait(300)
        frame = capture.get_frame(busy_wait=.2)
        assert frame is not None and frame.shape[0] > 400
        assert cv2.imwrite(str(output), frame)
    finally:
        stop.set()
        if capture is not None: capture.close()
        target.stop()


def audit_inventory():
    from nuannuan.ui_logic import OPERATION_GROUPS
    return {
        'operations': [name for names in OPERATION_GROUPS.values() for name in names],
        'scripts': ['宏 / 乐谱', '自定义流程', '录制宏', '录制路线'],
        'unsupported_wishes': ['升级祝福闪光', '制作服装', '流星 / 椰果 / 碎片 / 泡泡合影'],
    }


def audit_pages(app, window):
    from PySide6.QtWidgets import QMessageBox, QDialog
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from qfluentwidgets import PushButton, SwitchButton
    from nuannuan.config import ROOT
    from nuannuan.home import HomeTab
    from nuannuan.feature_tab import FeatureTab
    from nuannuan.script_tab import ScriptTab
    from nuannuan.route_tab import RouteTab
    from nuannuan.route_store import RouteStore
    from nuannuan.route_editor import RouteEditor
    from nuannuan.map_mask_tab import MapMaskTab
    from nuannuan.tasks import OperationTask, DailyTask, CaptureCheckTask
    from nuannuan.ui_logic import FlowSteps

    home, features, scripts, routes, mask = [window.findChild(cls) for cls in
                                           [HomeTab, FeatureTab, ScriptTab, RouteTab, MapMaskTab]]
    inventory = audit_inventory()
    results = {'game_input_sent': False, 'external_program_started': False, 'pages': {},
               'operations': [], 'scripts': [], 'unsupported_wishes': inventory['unsupported_wishes']}
    task = app.task_executor.get_task_by_class(OperationTask)
    original_config = dict(task.config)
    original_pending = getattr(task, '_pending_options', None)
    original_model, original_dirty = copy.deepcopy(scripts.model), scripts._dirty
    original_account = features.account_edit.text()
    dispatched = []
    controller = app.app.start_controller
    original_start = controller.start
    original_store = routes.store
    home_timer_active = home.timer.isActive()
    home.timer.stop()

    def clear_pending():
        task._dispatch_until = 0
        task._pending_options = None

    def check_dispatch(name, callback):
        clear_pending()
        before = len(dispatched)
        callback()
        assert len(dispatched) == before+1, f'{name}: no dispatch'
        assert dispatched[-1] is task, f'{name}: wrong task'
        assert task._pending_options['工具功能'] == name, f'{name}: wrong operation'

    try:
        controller.start = lambda selected=None, **kwargs: dispatched.append(selected)
        with patch('nuannuan.ui_actions.psutil.process_iter', return_value=[SimpleNamespace(info={'name': 'X6Game-Win64-Shipping.exe'})]), \
             patch('nuannuan.feature_tab.QMessageBox.question', return_value=QMessageBox.Yes):
            # Every ordinary tool is clicked through its real signal handler.
            for name in inventory['operations']:
                if name == '页面跳转':
                    button = next(button for button in features.findChildren(PushButton) if button.text() == '前往页面')
                elif name == '切换账号':
                    features.account_edit.setText('界面审计测试账号')
                    button = next(button for button in features.findChildren(PushButton) if button.text() == '切换已保存账号')
                else: button = features.buttons[name]
                check_dispatch(name, button.click)
                results['operations'].append({'name': name, 'dispatch': 'passed'})
            results['pages']['常用操作'] = '22 个操作均连接到执行器；关闭 / 切换确认框已覆盖，未执行游戏动作'

            assert not home.findChildren(SwitchButton), 'Home duplicates the helper page switches'
            helper_cards = window.trigger_tab.card_widgets
            assert len(helper_cards) == 6
            assert {card.task for card in helper_cards} == set(app.task_executor.trigger_tasks)
            window.switchTo(window.trigger_tab)
            for card in helper_cards:
                helper, switch = card.task, card.enable_button
                saved_checked = helper.enabled
                with patch.object(helper, 'enable') as enable, patch.object(helper, 'disable') as disable:
                    switch.blockSignals(True)
                    switch.setChecked(False)
                    switch.blockSignals(False)
                    switch.setChecked(True)
                    QTest.qWait(40)
                    enable.assert_called_once()
                    switch.setChecked(False)
                    disable.assert_called_once()
                switch.blockSignals(True)
                switch.setChecked(saved_checked)
                switch.blockSignals(False)
            results['pages']['辅助任务'] = '六个辅助只在原生辅助页保留开关；逐个分派通过，偏好未改动'
            window.switchTo(home)
            home.refresh()
            home.daily_button.click()
            assert dispatched[-1].__class__ is DailyTask
            assert not any(hasattr(home, name) for name in ('capture_button', 'tools_button', 'mask_button', 'routes_button'))
            capture_card = next(card for card in window.onetime_tab.card_widgets if card.task.__class__ is CaptureCheckTask)
            capture_card.start_button.click()
            assert dispatched[-1].__class__ is CaptureCheckTask
            home.daily_settings_button.click()
            assert window.stackedWidget.currentWidget() is window.onetime_tab
            with patch('nuannuan.home.QDesktopServices.openUrl') as open_url:
                assert len(home.more_actions) == 2
                for action, target in zip(home.more_actions, [ROOT/'logs', ROOT/'README.md']):
                    action.trigger()
                    assert Path(open_url.call_args.args[0].toLocalFile()).resolve() == target.resolve()
            assert home.more_button.menu() is home.more_menu
            for page in (features, mask, routes, window.trigger_tab):
                navigation = window.navigationInterface.widget(page.objectName())
                assert navigation is not None
                # Fluent navigation wraps the clickable item in a tree widget;
                # the wrapper intentionally ignores mouse release events.
                QTest.mouseClick(navigation.itemWidget, Qt.LeftButton)
                assert window.stackedWidget.currentWidget() is page, page.objectName()
            with patch.object(app.run_control, 'last_task', SimpleNamespace(name='最近任务 · 界面验证', paused=False, info={})):
                home.refresh()
                home.progress_button.click()
                assert app.run_dialog.isVisible()
                app.run_dialog.hide()
            results['pages']['运行总览'] = '每日启动 / 调整计划、合并运行区及详情通过；画面检查留在任务页，辅助和三处页面从侧栏访问'

            check_dispatch('宏 / 乐谱', scripts.play_button.click)
            results['scripts'].append('宏 / 乐谱')
            scripts.model = FlowSteps([{'type': 'path', 'script_name': '星海拾光_更改音乐', 'enabled': True}])
            scripts.render_steps()
            check_dispatch('自定义流程', scripts.flow_run_button.click)
            results['scripts'].append('自定义流程')
            for kind, name in [('宏', '录制宏'), ('路线', '录制路线')]:
                scripts.record_kind.setCurrentText(kind)
                check_dispatch(name, scripts.record)
                assert 1 <= task._pending_options['录制秒数'] <= 120
                results['scripts'].append(name)

        # System launch is mocked; a dummy file is never executed.
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as directory:
            temporary = Path(directory)
            executable = temporary/'launcher.exe'
            executable.write_bytes(b'UI audit placeholder; never executed')
            with patch('nuannuan.feature_tab.QFileDialog.getOpenFileName', return_value=(str(executable), '')), \
                 patch('nuannuan.feature_tab.os.startfile') as startfile:
                features.launch_game(select_only=True)
                assert task.config['启动程序路径'] == str(executable)
                features.launch_game()
                startfile.assert_called_once_with(str(executable))
            export = temporary/'flow.json'
            with patch('nuannuan.script_tab.QFileDialog.getSaveFileName', return_value=(str(export), '')):
                scripts.export_flow()
            assert len(json.loads(export.read_text(encoding='utf-8'))) == 1
            with patch('nuannuan.script_tab.QFileDialog.getOpenFileName', return_value=(str(export), '')):
                scripts.import_flow()
            assert scripts.read_steps().items[0]['script_name'] == '星海拾光_更改音乐'
            results['pages']['脚本管理'] = '播放、流程执行、两种录制分派、流程导入导出通过'

            seed = original_store.get_data('星海拾光_更改音乐')
            source = temporary/'route.json'
            source.write_text(json.dumps(seed, ensure_ascii=False), encoding='utf-8')
            routes.store = RouteStore(temporary/'library')
            with patch('nuannuan.route_tab.QFileDialog.getOpenFileNames', return_value=([str(source)], '')):
                routes.import_button.click()
            assert len(routes.rows) == 1
            def edit(editor):
                editor.name_edit.setText('界面审计临时路线')
                editor.save()
                return int(QDialog.Accepted)
            with patch.object(RouteEditor, 'exec', edit): routes.edit_button.click()
            assert routes.rows[0]['name'] == '界面审计临时路线'
            with patch('nuannuan.route_tab.QMessageBox.question', return_value=QMessageBox.Yes):
                routes.delete_button.click()
            assert not routes.rows
            results['pages']['路线与跑图'] = '实际导入、编辑、删除按钮操作临时库通过；用户路线未修改'
        assert window.start_tab is not None and window.setting_tab is not None
        results['pages']['连接与设置'] = '页面存在；按键、跑图、扩展、遮罩设置组已加载；游戏连接效果待实机'
        results['pages']['地图遮罩'] = '点位导入、离线预览、渲染、点击穿透及任务启动关闭已由 GUI smoke 验证'
        results['passed'] = True
        return results
    finally:
        controller.start = original_start
        routes.store = original_store
        routes.reload_catalog()
        for key, value in original_config.items(): task.config[key] = value
        task._pending_options = original_pending
        task._dispatch_until = 0
        features.account_edit.setText(original_account)
        scripts.model, scripts._dirty = original_model, original_dirty
        scripts.render_steps()
        home.refresh()
        if home_timer_active: home.timer.start(1000)
