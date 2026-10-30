import unittest

import cv2
import numpy as np

from nuannuan.map_vision import MapLocator
from nuannuan.routes import RouteError
from nuannuan.config import ROOT


class MapVisionTests(unittest.TestCase):
    def test_minimap_matches_known_position_and_scaled_capture(self):
        rng = np.random.default_rng(42)
        atlas = rng.integers(20, 220, (1200, 1600), dtype=np.uint8)
        center = (1000, 700)  # atlas pixels; full map coordinates are twice these.
        patch = atlas[660:740, 960:1040]
        minimap = cv2.resize(patch, (200, 200), interpolation=cv2.INTER_NEAREST)
        reference = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        reference[22:222, 81:281] = cv2.cvtColor(minimap, cv2.COLOR_GRAY2BGR)
        locator = MapLocator(images={'starsea': {'05x': atlas}})
        for size in [(1920, 1080), (1280, 720)]:
            with self.subTest(size=size):
                frame = cv2.resize(reference, size, interpolation=cv2.INTER_NEAREST)
                location = locator.minimap(frame, 'starsea', (2002, 1402))
                self.assertLess(np.linalg.norm(np.array(location) - (2000, 1400)), 4)

    def test_bigmap_matches_center_in_atlas_coordinates(self):
        rng = np.random.default_rng(11)
        atlas = rng.integers(20, 220, (400, 500), dtype=np.uint8)
        # Center crop at atlas position (250, 200), projected at the original 0.62 scale.
        patch = atlas[170:230, 200:300]
        frame = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        image = cv2.resize(patch, (1280, 768), interpolation=cv2.INTER_NEAREST)
        frame[156:924, 320:1600] = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        locator = MapLocator(images={'starsea': {'0125x': atlas}})
        center = locator.bigmap(frame, 'starsea')
        self.assertLess(np.linalg.norm(np.array(center) - (2000, 1600)), 12)

    def test_blank_and_unmatched_minimap_stop_navigation(self):
        locator = MapLocator(images={'starsea': {'05x': np.zeros((500, 500), dtype=np.uint8)}})
        with self.assertRaises(RouteError):
            locator.minimap(np.zeros((1080, 1920, 3), dtype=np.uint8), 'starsea', (300, 300))

    def test_local_starsea_atlas_can_relocalize_a_projected_minimap(self):
        atlas = cv2.imread(str(ROOT / 'assets/maps/w14000000_v2_luma_05x.png'), cv2.IMREAD_GRAYSCALE)
        patch = atlas[979:1059, 794:874]
        reference = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        reference[22:222, 81:281] = cv2.cvtColor(cv2.resize(patch, (200, 200)), cv2.COLOR_GRAY2BGR)
        position = MapLocator().minimap(reference, 'starsea', (1668, 2038))
        self.assertLess(np.linalg.norm(np.array(position) - (1668, 2038)), 4)
