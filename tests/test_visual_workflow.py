"""Exercise real ok-script matching and the runtime adapter against UI scenes."""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from ok.feature.FeatureSet import FeatureSet

from nuannuan.config import ROOT
from nuannuan.daily import DailyRunner
from nuannuan.runtime import RuntimePort


class VisualWorkflowTests(unittest.TestCase):
    def test_photo_through_real_framework_matching_at_two_resolutions(self):
        manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))
        for size in [(1920, 1080), (1280, 720)]:
            with self.subTest(resolution=size):
                features = FeatureSet(False, None, 0.015, 0.015, template_folder=str(ROOT / 'assets/templates'))
                scenes = {}
                for scene, name in [('home', 'IconPageMainFeature'), ('photo', 'IconPhotoFeature'), ('result', 'IconPhotoEdit')]:
                    source = cv2.imread(str(ROOT / manifest['features'][name]['authoring']))
                    frame = np.full_like(source, 70)
                    x, y, w, h = manifest['features'][name]['bbox']
                    frame[y:y+h, x:x+w] = source[y:y+h, x:x+w]
                    scenes[scene] = cv2.resize(frame, size)

                class VisualGame:
                    scene = 'home'
                    @property
                    def frame(self):
                        return scenes[self.scene]
                    def next_frame(self):
                        return self.frame
                    def find_one(self, name, **kwargs):
                        frame = kwargs.pop('frame')
                        matches = features.find_one_feature(frame, name, **kwargs)
                        return matches[0] if matches else None
                    def send_key(self, value, **kwargs):
                        if value == 'p' and self.scene == 'home':
                            self.scene = 'photo'
                        elif value == 'space' and self.scene == 'photo':
                            self.scene = 'result'
                        elif value == 'esc':
                            self.scene = 'home'
                    def wait_until(self, condition, **kwargs):
                        return condition()
                    def sleep(self, seconds):
                        pass

                task = VisualGame()
                with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as directory:
                    result = DailyRunner(RuntimePort(task, Path(directory), {})).run_one('photo')
                    self.assertEqual(result['status'], 'succeeded')
                    self.assertEqual(task.scene, 'home')
                    self.assertTrue(list(Path(directory).glob('photo_result*.png')))
