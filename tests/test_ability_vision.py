import unittest

import cv2
import numpy as np

from nuannuan.routes.ability import ABILITY_ICONS, JUMP_ICONS
from nuannuan.routes.ability_runtime import AbilityVision
from nuannuan.config import ROOT


class AbilityVisionTests(unittest.TestCase):
    def test_all_local_ability_icons_can_be_read_in_a_wheel_slot(self):
        vision = AbilityVision()
        for name, icon in {**ABILITY_ICONS, **JUMP_ICONS}.items():
            with self.subTest(ability=name):
                source = cv2.imread(str(ROOT / 'assets/ability_icons' / f'{icon}.png'))
                canvas = np.zeros((100, 100, 3), dtype=np.uint8)
                h, w = source.shape[:2]
                canvas[(100-h)//2:(100-h)//2+h, (100-w)//2:(100-w)//2+w] = source
                candidates = JUMP_ICONS if name in JUMP_ICONS else ABILITY_ICONS
                self.assertEqual(vision.identify(canvas, candidates), name)

    def test_empty_slot_does_not_claim_an_ability(self):
        self.assertIsNone(AbilityVision().identify(np.zeros((100, 100, 3), dtype=np.uint8), ABILITY_ICONS))
