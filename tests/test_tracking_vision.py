import unittest
import cv2
import numpy as np


class TrackingVisionTests(unittest.TestCase):
    def frame(self, offset=(24, 0), radius=16):
        hsv = np.zeros((1080, 1920, 3), np.uint8)
        if offset is not None:
            cv2.circle(hsv, (181+offset[0], 122+offset[1]), radius, (14, 150, 235), 3)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    def test_tracking_circle_uses_near_player_limit_and_scaled_frame(self):
        from nuannuan.map.tracking_vision import TrackingVision
        for size in [(1920, 1080), (1280, 720)]:
            with self.subTest(size=size):
                marker = TrackingVision().marker(cv2.resize(self.frame(), size))
                self.assertIsNotNone(marker)
                self.assertLess(np.linalg.norm(np.array(marker)-(24, 0)), 3)
        self.assertIsNone(TrackingVision().marker(self.frame((60, 0))))
        self.assertIsNone(TrackingVision().marker(self.frame(None)))

    def test_center_arrow_and_wrong_colored_ring_are_not_targets(self):
        from nuannuan.map.tracking_vision import TrackingVision
        frame = self.frame(None)
        cv2.circle(frame, (181, 122), 9, (0, 200, 240), -1)
        cv2.circle(frame, (205, 122), 16, (200, 30, 30), 3)
        self.assertIsNone(TrackingVision().marker(frame))

    def test_ability_ready_requires_the_source_highlight_pixels(self):
        from nuannuan.map.tracking_vision import TrackingVision
        from nuannuan.config import ROOT
        import json
        x,y,w,h=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))['regions']['AreaAbilityButton']['bbox']
        hsv = np.zeros((1080,1920,3),np.uint8)
        self.assertFalse(TrackingVision().ability_ready(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)))
        hsv[y+3:y+23,x+3:x+23]=(15,95,240)
        self.assertTrue(TrackingVision().ability_ready(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)))
