"""ok-script input backend following Whimbox's Windows foreground operations."""
import threading
import time

from ok.device.interaction_methods.base import BaseInteraction
from nuannuan.core.errors import AutomationError


class WindowsEvents:
    def __init__(self):
        import ctypes
        self.scan = ctypes.windll.user32.VkKeyScanA

    def virtual_key(self, key):
        from ok.device.interaction_methods.keys import vk_key_dict
        aliases = {'right_control': 'RCTRL', 'left_control': 'LCTRL', 'escape': 'ESC',
                   'ctrlright': 'RCTRL', 'ctrlleft': 'LCTRL', 'shiftleft': 'LSHIFT',
                   'shiftright': 'RSHIFT'}
        if len(key) == 1:
            value = self.scan(ord(key))
            if value != -1: return value & 0xff
        else:
            value = vk_key_dict.get(aliases.get(key.lower(), key.upper()))
            if value is not None: return value
        raise AutomationError(f'未知按键：{key}')

    def validate_key(self, key): self.virtual_key(key)

    def key(self, key, down):
        import win32api, win32con
        vk = self.virtual_key(key)
        extended = key.lower() in {'right_control', 'rctrl', 'ctrlright'}
        scan = win32api.MapVirtualKey(vk, 0) if key.lower() == 'shift' or extended else 0
        flags = win32con.KEYEVENTF_EXTENDEDKEY if extended else 0
        if not down: flags |= win32con.KEYEVENTF_KEYUP
        win32api.keybd_event(vk, scan, flags, 0)

    def button(self, key, down):
        import win32api, win32con
        flag = getattr(win32con, f'MOUSEEVENTF_{key.upper()}{"DOWN" if down else "UP"}')
        win32api.mouse_event(flag, 0, 0, 0, 0)

    def move(self, x, y):
        import win32api
        win32api.SetCursorPos((round(x), round(y)))

    def scroll(self, amount):
        import win32api, win32con
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, int(amount)*120, 0)

    def position(self):
        import win32api
        return win32api.GetCursorPos()


class WhimboxInteraction(BaseInteraction):
    """Restore target focus for input; always allow owned key/button releases."""
    def __init__(self, capture, hwnd_window, *, driver=None):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.driver = driver or WindowsEvents()
        self.held_keys, self.held_buttons = set(), set()
        self.cancelled = False
        self.lock = threading.RLock()

    def _target(self):
        if self.cancelled: raise AutomationError('任务已停止，未发送新的游戏输入')
        if not self.hwnd_window.is_foreground():
            self.hwnd_window.bring_to_front()
        if not self.hwnd_window.is_foreground():
            raise AutomationError('未能恢复游戏前台，已停止输入；请手动切回游戏')

    def on_run(self):
        from nuannuan.core.startup import LaunchRuntime
        self.release_all()
        self.cancelled = False
        LaunchRuntime.check_privilege(self.hwnd_window.hwnd)
        self._target()

    def should_capture(self): return True

    def send_key_down(self, key):
        key = str(key).lower()
        self.driver.validate_key(key)
        with self.lock:
            self._target()
            self.driver.key(key, True)
            self.held_keys.add(key)

    def send_key_up(self, key):
        key = str(key).lower()
        with self.lock:
            if key in self.held_keys:
                self.driver.key(key, False)
                self.held_keys.discard(key)

    def send_key(self, key, down_time=.1):
        self.send_key_down(key)
        try: time.sleep(down_time)
        finally: self.send_key_up(key)

    def move(self, x, y):
        with self.lock:
            self._target()
            self.driver.move(*self.capture.get_abs_cords(x, y))

    def mouse_down(self, x=-1, y=-1, name=None, key='left'):
        if key not in {'left', 'right', 'middle'}: raise AutomationError('未知鼠标按键')
        with self.lock:
            self._target()
            if x != -1 and y != -1: self.move(x, y)
            self.driver.button(key, True)
            self.held_buttons.add(key)

    def mouse_up(self, key='left'):
        with self.lock:
            if key in self.held_buttons:
                self.driver.button(key, False)
                self.held_buttons.discard(key)

    def click(self, x=-1, y=-1, move_back=False, name=None, move=False, down_time=.1, key='left'):
        original = self.driver.position() if move_back else None
        self.mouse_down(x, y, name=name, key=key)
        try: time.sleep(down_time)
        finally:
            self.mouse_up(key)
            if original is not None and not self.cancelled and self.hwnd_window.is_foreground():
                self.driver.move(*original)

    def scroll(self, x, y, scroll_amount):
        with self.lock:
            self.move(x, y)
            self.driver.scroll(scroll_amount)

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        self.mouse_down(from_x, from_y)
        try:
            steps = max(2, int(duration/.02))
            for i in range(1, steps+1):
                self.move(from_x+(to_x-from_x)*i/steps, from_y+(to_y-from_y)*i/steps)
                time.sleep(duration/steps)
        finally: self.mouse_up()
        time.sleep(settle_time)

    def release_all(self):
        with self.lock:
            failures = []
            for key in list(self.held_keys):
                try: self.send_key_up(key)
                except Exception as error: failures.append(error)
            for key in list(self.held_buttons):
                try: self.mouse_up(key)
                except Exception as error: failures.append(error)
            if failures: raise AutomationError(f'释放游戏输入失败：{failures[0]}')

    def cancel(self):
        with self.lock:
            self.cancelled = True
            self.release_all()

    def resume_helpers(self):
        with self.lock:
            self.cancelled = False

    def on_destroy(self): self.cancel()
