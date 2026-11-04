import unittest

from nuannuan.core.errors import AutomationError


class TrackPort:
    def __init__(self, observations=None, loot=None):
        self.events = []
        self.observations = list(observations or [])
        self.loot = list(loot or [])
        self.held = False
    def stage(self, name): self.events.append(name)
    def select_ability(self, name): self.events.append(('ability', name))
    def enable_tracking(self, name): self.events.append(('track', name))
    def begin_capture(self): self.held = True; self.events.append('hold')
    def observe(self): return self.observations.pop(0) if self.observations else {'active': False, 'marker': None}
    def approach(self, marker): self.events.append(('approach', marker))
    def stop_forward(self): self.events.append('stop_forward')
    def release_capture(self): self.held = False; self.events.append('release')
    def reward_text(self): return self.loot.pop(0) if self.loot else ''
    def finish_capture(self): self.events.append('finish')
    def clear_marker(self): self.events.append('clear_marker')
    def sleep(self, seconds): pass
    def release_all(self): self.held = False; self.events.append('release_all')
    def evidence(self, name): pass


class MaterialTrackingTests(unittest.TestCase):
    def test_source_sequence_and_two_active_frames_before_catching(self):
        from nuannuan.map.material_tracking import MaterialTracker
        port = TrackPort([{'active': False, 'marker': (15, 0)}, {'active': True, 'marker': (10, 0)},
                          {'active': True, 'marker': (10, 0)}], ['', '珠链蝶×1'])
        result = MaterialTracker(port).run('珠链蝶', '捕虫', expected_count=1)
        self.assertEqual(result['materials'], {'珠链蝶': 1})
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(port.events[:5], ['切换能力', ('ability', '捕虫'), '开启材料追踪', ('track', '珠链蝶'), '开始前往采集'])
        self.assertIn(('approach', (15, 0)), port.events)
        self.assertLess(port.events.index('release'), port.events.index('finish'))
        self.assertEqual(port.events[-1], 'release_all')
        self.assertFalse(port.held)

    def test_six_consecutive_missing_targets_end_point_with_zero_not_success(self):
        from nuannuan.map.material_tracking import MaterialTracker
        port = TrackPort()
        result = MaterialTracker(port).run('暮暮蝶', '捕虫')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['materials'], {'暮暮蝶': 0})
        self.assertEqual(result['missing_frames'], 6)
        self.assertNotIn('finish', port.events)
        self.assertFalse(port.held)

    def test_old_or_wrong_material_toast_is_not_counted(self):
        from nuannuan.map.material_tracking import MaterialTracker
        for texts in [['珠链蝶×1', '珠链蝶×1'], ['', '暮暮蝶×1']]:
            with self.subTest(texts=texts):
                port = TrackPort([{'active': True, 'marker': None}]*2, texts)
                result = MaterialTracker(port).run('珠链蝶', '捕虫')
                self.assertEqual(result['materials']['珠链蝶'], 0)
                self.assertEqual(result['status'], 'partial')

    def test_transient_missing_marker_resets_on_observation(self):
        from nuannuan.map.material_tracking import MaterialTracker
        missing = {'active': False, 'marker': None}
        port = TrackPort([missing]*5+[{'active': False, 'marker': (10, 0)}]+[missing]*6)
        result = MaterialTracker(port).run('珠链蝶', '捕虫')
        self.assertIn(('approach', (10, 0)), port.events)
        self.assertEqual(result['missing_frames'], 6)

    def test_cancellation_releases_capture_without_more_actions(self):
        from nuannuan.map.material_tracking import MaterialTracker
        class Cancelled(Exception): pass
        port = TrackPort()
        def cancel(): raise Cancelled()
        port.observe = cancel
        with self.assertRaises(Cancelled): MaterialTracker(port).run('珠链蝶', '捕虫')
        self.assertEqual(port.events[-1], 'release_all')
        self.assertFalse(port.held)

    def test_invalid_count_fails_before_input(self):
        from nuannuan.map.material_tracking import MaterialTracker
        port = TrackPort()
        with self.assertRaises(AutomationError): MaterialTracker(port).run('珠链蝶', '捕虫', expected_count=0)
        self.assertFalse(port.events)
