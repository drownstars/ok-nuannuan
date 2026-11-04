"""Real template matching plus the actual five-card capture adapter, with a simulated UI."""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from ok import Box
from ok.feature.FeatureSet import FeatureSet

from nuannuan.config import ROOT
from nuannuan.daily.objectives import WISH_CENTERS, STARSEA_CENTERS
from nuannuan.core.runtime import RuntimePort


class ObjectiveCaptureTests(unittest.TestCase):
    def test_full_board_score_is_checked_twice_without_clicking_cards(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            port = ScorePort(folder, [500, 500])
            snapshot = port.scan_objectives('wish')
            self.assertEqual(snapshot.score, 500)
            self.assertEqual(snapshot.objectives, [])
            self.assertEqual(port.card_clicks, [])
            self.assertEqual(port.score_reads, 2)
            self.assertTrue((Path(folder) / 'wish_snapshot.json').exists())

    def test_unstable_full_score_is_not_used_to_skip_tasks(self):
        from nuannuan.core.errors import AutomationError
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            port = ScorePort(folder, [500, 400])
            with self.assertRaisesRegex(AutomationError, '积分.*不稳定|分数.*不稳定'):
                port.scan_objectives('wish')
            self.assertEqual(port.card_clicks, [])

    def test_both_boards_read_five_distinct_cards_and_actual_completion_markers(self):
        manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))
        features = FeatureSet(False, None, .015, .015, template_folder=str(ROOT / 'assets/templates'))

        class Game:
            scene = 'home'
            slot = 0
            @property
            def frame(self):
                frame = np.full((1080, 1920, 3), 60, dtype=np.uint8)
                names = {'home': ['IconPageMainFeature'], 'calendar': ['ButtonZxxyEntrance', 'ButtonXhsgEntrance'],
                         'wish': ['IconZxxyFeature'], 'starsea': ['IconXhsgFeature']}[self.scene][:]
                if self.scene in {'wish', 'starsea'} and self.slot == 2:
                    names.append('IconZxxyTaskFinished' if self.scene == 'wish' else 'IconXhsgTaskFinished')
                for name in names:
                    entry = manifest['features'][name]
                    original = cv2.imread(str(ROOT / entry['authoring']))
                    x, y, width, height = entry['bbox']
                    frame[y:y+height, x:x+width] = original[y:y+height, x:x+width]
                return frame
            def next_frame(self):
                return self.frame
            def find_one(self, name, **kwargs):
                frame = kwargs.pop('frame')
                matches = features.find_one_feature(frame, name, **kwargs)
                return matches[0] if matches else None
            def send_key(self, value, **kwargs):
                self.scene = 'calendar' if value == 'l' else 'home'
            def click_box(self, box, **kwargs):
                self.scene = 'wish' if box.name == 'ButtonZxxyEntrance' else 'starsea'
            def click(self, x, y, **kwargs):
                centers = WISH_CENTERS if self.scene == 'wish' else STARSEA_CENTERS
                self.slot = centers.index((x, y))
            def sleep(self, seconds):
                pass
            def wait_until(self, condition, **kwargs):
                return condition()
            def ocr(self, box, **kwargs):
                text = '200' if box.name.endswith('Score') else ['拍摄照片', '采集植物', '捕捉昆虫', '陌生任务', '美鸭梨挖掘'][self.slot]
                return [Box(0, 0, 20, 20, name=text)]

        for board in ['wish', 'starsea']:
            with self.subTest(board=board), tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
                game = Game()
                snapshot = RuntimePort(game, Path(folder), {}).scan_objectives(board)
                self.assertEqual(snapshot.score, 200)
                self.assertEqual(len(snapshot.objectives), 5)
                self.assertEqual(sum(item.completed for item in snapshot.objectives), 1)
                self.assertTrue(snapshot.objectives[2].completed)
                self.assertEqual(snapshot.objectives[3].kind, 'unknown')
                self.assertEqual(game.scene, 'home')
                self.assertTrue((Path(folder) / f'{board}_snapshot.json').exists())


class ScorePort(RuntimePort):
    def __init__(self, folder, scores):
        self.artifacts, self.settings = Path(folder), {}
        self.scores, self.score_reads, self.card_clicks = iter(scores), 0, []
        self.home = False
    def open_objective_board(self, board):
        self.home = False
    def text(self, region, frame=None):
        assert region.endswith('Score')
        self.score_reads += 1
        return str(next(self.scores))
    def exists(self, name):
        return self.home if name == 'IconPageMainFeature' else True
    def key(self, value):
        assert value == 'esc'
        self.home = True
    def click_reference(self, x, y):
        self.card_clicks.append((x, y))
        raise AssertionError('A full board must not scan any cards')
    def sleep(self, seconds):
        pass
