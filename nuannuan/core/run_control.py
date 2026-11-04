"""Single foreground task ownership and cooperative stop, scoped to this app."""
import json
import os
import threading
import uuid
from pathlib import Path
from types import MethodType

from PySide6.QtCore import QObject, Signal
from nuannuan.core.errors import AutomationError


def migrate_runtime_file(path):
    path = Path(path)
    if not path.exists(): return
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('nuannuan_foreground_v1'): return
    backup = path.parent/'migrations'
    backup.mkdir(parents=True, exist_ok=True)
    (backup/f'devices-before-foreground-{uuid.uuid4().hex}.json').write_bytes(path.read_bytes())
    data.update(interaction='WhimboxInteraction', nuannuan_foreground_v1=True)
    temporary = path.with_suffix('.foreground.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def assist_allowed(executor):
    control = getattr(executor, '_nuannuan_run_control', None)
    if control is not None and control.busy: return False
    current = getattr(executor, 'current_task', None)
    if current is not None and current not in getattr(executor, 'trigger_tasks', []): return False
    window = getattr(getattr(executor, 'interaction', None), 'hwnd_window', None)
    return bool(window is not None and window.is_foreground())


class RunControl(QObject):
    show_requested = Signal()
    overlay_off = Signal()

    def __init__(self, app):
        super().__init__()
        self.app, self.task = app, None
        self.cancel_event = threading.Event()
        self.lock = threading.RLock()
        self.state = '待机'
        self.last_task = None
        self.listener = None
        self.events = []
        self.starting = False

    @property
    def busy(self): return self.task is not None

    def reserve(self, task):
        with self.lock:
            if self.busy: return False
            self.cancel_event.clear()
            self.task = self.last_task = task
            self.state = '准备启动'
            self.events.clear()
            self.record(task.name, 'running', '准备启动；按 / 可停止')
            self.overlay_off.emit()
            self.show_requested.emit()
            return True

    def stop(self):
        with self.lock:
            task = self.task
            if task is None: return
            self.cancel_event.set()
            self.state = '正在停止，等待释放输入'
            task.disable()
            task.unpause()
            backend = getattr(self.app.task_executor, 'interaction', None)
            if backend is not None and hasattr(backend, 'cancel'):
                try: backend.cancel()
                except Exception as error: task.info_set('输入释放错误', str(error))

    def finish(self, task, *, state=None):
        with self.lock:
            if self.task is not task: return
            self.state = state or ('已停止' if self.cancel_event.is_set() else '已结束')
            self.task = None

    def record(self, label, state, message=''):
        with self.lock:
            self.events.append((label, state, message))
            self.events[:] = self.events[-300:]

    def reconcile(self):
        task = self.task
        if task is not None and not self.starting and not task.enabled and not getattr(task, 'running', False):
            self.finish(task, state='已停止' if self.cancel_event.is_set() else '已结束')

    def pause_or_resume(self):
        executor = self.app.task_executor
        if executor.paused or (self.task is not None and self.task.paused):
            if self.task is not None: self.task.unpause()
            executor.start()
        else:
            executor.pause()
            backend = getattr(executor, 'interaction', None)
            if backend is not None and hasattr(backend, 'release_all'): backend.release_all()

    def close(self):
        self.stop()
        if self.listener is not None: self.listener.stop()

    def install_hotkey(self):
        from pynput import keyboard
        def pressed(key):
            if getattr(key, 'char', None) == '/': self.stop()
        self.listener = keyboard.Listener(on_press=pressed)
        self.listener.daemon = True
        self.listener.start()


def install_run_control(app):
    control = RunControl(app)
    app.run_control = control
    executor = app.task_executor
    executor._nuannuan_run_control = control
    for task in executor.onetime_tasks:
        original_run = task.run
        def run(self, original=original_run):
            if control.task is not self and not control.reserve(self):
                raise AutomationError('已有任务运行，请先停止当前任务')
            if control.cancel_event.is_set():
                control.finish(self)
                return
            control.state = '执行中'
            try: return original()
            finally:
                backend = getattr(executor, 'interaction', None)
                try:
                    if backend is not None and hasattr(backend, 'release_all'): backend.release_all()
                finally: control.finish(self)
        task.run = MethodType(run, task)
    for facade in [getattr(app, '_app', None), getattr(app, '_headless_app', None)]:
        if facade is None: continue
        facade.run_control = control
        controller = facade.start_controller
        original_start = controller._do_start
        def start(self, task=None, exit_after=False, original=original_start):
            if isinstance(task, int): task = executor.onetime_tasks[task]
            if task is None:
                if control.busy: return False
                return original(task, exit_after)
            if control.busy:
                if control.task is task and (task.paused or executor.paused):
                    task.unpause()
                    executor.start()
                    return True
                from ok.core.events import communicate
                communicate.starting_emulator.emit(True, '已有任务运行，请先停止当前任务', 0)
                control.show_requested.emit()
                return False
            if not control.reserve(task): return False
            control.starting = True
            try:
                success = original(task, exit_after)
                if not success or control.cancel_event.is_set():
                    task.disable()
                    control.finish(task, state='已停止' if control.cancel_event.is_set() else '启动失败')
                    return False
                return success
            except BaseException:
                control.finish(task, state='启动失败')
                raise
            finally: control.starting = False
        controller._do_start = MethodType(start, controller)
    return control
