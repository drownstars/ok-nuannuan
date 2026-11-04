"""Home controls follow real task ownership, including pre-launch and stop."""
import threading
from types import SimpleNamespace
from unittest.mock import patch

from nuannuan.daily.workflow import DAILY_DEFAULTS
from nuannuan.ui.home import HomeTab
from nuannuan.tasks.daily_tasks import DailyTask


class Widget:
    def __init__(self):
        self.value, self.enabled, self.visible = '', True, True
        self.writes = 0
    def setText(self, value): self.value = value
    def text(self): return self.value
    def setPlainText(self, value):
        self.value = value
        self.writes += 1
    def toPlainText(self): return self.value
    def setEnabled(self, value): self.enabled = value
    def isEnabled(self): return self.enabled
    def setVisible(self, value): self.visible = value


def home_port(tmp_path, *, busy=False, state='待机'):
    task = SimpleNamespace(name='每日任务', paused=False, info={'启动状态': '正在等待官方启动器'})
    control = SimpleNamespace(busy=busy, state=state, task=task if busy else None,
                              last_task=task if busy else None, cancel_event=threading.Event())
    dispatched = []
    app = SimpleNamespace(run_control=control,
                          start_controller=SimpleNamespace(start=lambda task: dispatched.append(task)))
    home = SimpleNamespace(executor=SimpleNamespace(paused=True, current_task=None, trigger_tasks=[]),
                           game_running=False, _switches=[], _report_mtime=None, _rendered_text=None,
                           get_task=lambda cls: SimpleNamespace(config=dict(DAILY_DEFAULTS)))
    for name in ('pause_button', 'stop_button', 'daily_button', 'daily_settings_button',
                 'progress_button', 'status_label', 'plan_label', 'record_title', 'result_label',
                 'mode_label', 'run_state_label', 'empty_state'):
        setattr(home, name, Widget())
    home.render_result = lambda text: HomeTab.render_result(home, text)
    context = patch.multiple('nuannuan.ui.home', og=SimpleNamespace(app=app), ROOT=tmp_path)
    return home, control, dispatched, context


def test_idle_home_does_not_offer_resume_an_executor_with_no_task(tmp_path):
    home, _, _, context = home_port(tmp_path)
    with context, patch('nuannuan.ui.home.psutil.process_iter', return_value=[]):
        HomeTab.refresh(home)
    assert not home.pause_button.isEnabled()
    assert not home.stop_button.isEnabled()
    assert home.daily_button.isEnabled()


def test_pending_launch_owns_controls_and_displays_its_own_progress(tmp_path):
    home, _, _, context = home_port(tmp_path, busy=True, state='准备启动')
    with context, patch('nuannuan.ui.home.psutil.process_iter', return_value=[]):
        HomeTab.refresh(home)
    assert not home.daily_button.isEnabled()
    assert not home.daily_settings_button.isEnabled()
    assert not home.pause_button.isEnabled()
    assert home.stop_button.isEnabled()
    assert '正在等待官方启动器' in home.result_label.toPlainText()


def test_stop_request_keeps_start_locked_and_disables_repeated_stop(tmp_path):
    home, control, _, context = home_port(tmp_path, busy=True, state='正在停止，等待释放输入')
    control.cancel_event.set()
    with context, patch('nuannuan.ui.home.psutil.process_iter', return_value=[]):
        HomeTab.refresh(home)
    assert not home.stop_button.isEnabled()
    assert not home.daily_button.isEnabled()


def test_stale_start_button_cannot_dispatch_a_second_task(tmp_path):
    home, _, dispatched, context = home_port(tmp_path, busy=True, state='准备启动')
    with context:
        HomeTab.start_task(home, DailyTask)
    assert dispatched == []


def test_unchanged_running_text_does_not_reset_report_scroll_every_second(tmp_path):
    home, _, _, context = home_port(tmp_path, busy=True, state='执行中')
    with context, patch('nuannuan.ui.home.psutil.process_iter', return_value=[]):
        HomeTab.refresh(home)
        writes = home.result_label.writes
        assert writes > 0
        HomeTab.refresh(home)
    assert home.result_label.writes == writes
