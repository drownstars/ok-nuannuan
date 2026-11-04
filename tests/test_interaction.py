import unittest
from types import SimpleNamespace

from nuannuan.core.errors import AutomationError


class Driver:
    def __init__(self): self.events = []
    def key(self, key, down): self.events.append(('key', key, down))
    def button(self, key, down): self.events.append(('button', key, down))
    def move(self, x, y): self.events.append(('move', x, y))
    def scroll(self, amount): self.events.append(('scroll', amount))
    def position(self): return 5, 6
    def validate_key(self, key):
        if key == 'nonsense': raise AutomationError('未知按键')


class Window:
    hwnd = 123
    def __init__(self, foreground=False, succeeds=True):
        self.foreground, self.succeeds, self.focuses = foreground, succeeds, 0
    def is_foreground(self): return self.foreground
    def bring_to_front(self):
        self.focuses += 1
        self.foreground = self.succeeds
        return self.succeeds


class InteractionTests(unittest.TestCase):
    def make(self, **kwargs):
        from nuannuan.core.interaction import WhimboxInteraction
        driver, window = Driver(), Window(**kwargs)
        backend = WhimboxInteraction(SimpleNamespace(get_abs_cords=lambda x, y: (x+100, y+200)),
                                     window, driver=driver)
        return backend, driver, window

    def test_input_restores_focus_before_system_events(self):
        backend, driver, window = self.make()
        backend.send_key('f', down_time=0)
        self.assertEqual(window.focuses, 1)
        self.assertEqual(driver.events, [('key', 'f', True), ('key', 'f', False)])

    def test_failed_focus_does_not_inject_into_another_window(self):
        backend, driver, window = self.make(succeeds=False)
        with self.assertRaisesRegex(AutomationError, '前台'):
            backend.click(10, 20, down_time=0)
        self.assertEqual(driver.events, [])

    def test_cancel_releases_held_input_after_focus_loss_and_blocks_new_down(self):
        backend, driver, window = self.make(foreground=True)
        backend.send_key_down('w')
        backend.mouse_down(key='right')
        window.foreground = False
        backend.cancel()
        self.assertIn(('key', 'w', False), driver.events)
        self.assertIn(('button', 'right', False), driver.events)
        self.assertEqual(window.focuses, 0)
        with self.assertRaises(AutomationError): backend.send_key_down('w')
        backend.release_all()
        self.assertEqual(driver.events.count(('key', 'w', False)), 1)

    def test_click_uses_client_coordinates_and_releases_button(self):
        backend, driver, _ = self.make(foreground=True)
        backend.click(10, 20, down_time=0, key='right')
        self.assertEqual(driver.events, [('move', 110, 220), ('button', 'right', True),
                                         ('button', 'right', False)])

    def test_unknown_key_and_idle_should_capture_never_steal_focus(self):
        backend, driver, window = self.make()
        self.assertTrue(backend.should_capture())
        with self.assertRaises(AutomationError): backend.send_key('nonsense')
        self.assertEqual(window.focuses, 0)
        self.assertEqual(driver.events, [])
