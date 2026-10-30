import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from nuannuan.runtime import RuntimePort, validate_frame


class RuntimeTests(unittest.TestCase):
    def test_real_recorded_loading_caption_distinguishes_loading_from_login(self):
        import cv2
        from rapidocr import RapidOCR
        from types import SimpleNamespace
        from nuannuan.config import ROOT, make_config
        engine = RapidOCR(params=make_config()['ocr']['params'])
        class Task:
            def __init__(self):
                self.frame = np.full((720, 1280, 3), 60, np.uint8)
                image = cv2.imread(str(ROOT / 'tests/fixtures/login_loading_caption.png'))
                self.frame[590:662, 320:1088] = image
            def next_frame(self): return self.frame
            def find_one(self, name, **kwargs):
                # The recording confirmed the same sound icon on both scenes.
                return name == 'IconPageLoginFeature'
            def ocr(self, box, frame, threshold):
                result = engine(frame[box.y:box.y+box.height, box.x:box.x+box.width])
                return [SimpleNamespace(name=text) for text, score in zip(result.txts or [], result.scores or [])
                        if score >= threshold]
        task = Task()
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as tmp:
            port = RuntimePort(task, Path(tmp), {})
            self.assertTrue(port.exists('game_loading'))
            task.frame[:] = 60
            self.assertFalse(port.exists('game_loading'))

    def test_live_step_events_are_saved_and_sent_to_task_info(self):
        from types import SimpleNamespace
        from nuannuan.config import ROOT
        info={}
        task=SimpleNamespace(info_set=lambda key,value:info.update({key:value}))
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as tmp:
            port=RuntimePort(task,Path(tmp),{})
            port.workflow_progress('切换能力','running','捕虫')
            port.workflow_progress('切换能力','succeeded','已确认')
            rows=[json.loads(line) for line in (Path(tmp)/'workflow.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['state'] for row in rows],['running','succeeded'])
            self.assertIn('当前步骤',info)
            self.assertIn('已确认',info['切换能力'])

    def test_real_calendar_fields_use_single_line_recognition_and_ignore_status_icons(self):
        import cv2
        from types import SimpleNamespace
        from rapidocr import RapidOCR
        from nuannuan.config import ROOT,make_config
        from nuannuan.extra_daily import read_fraction
        engine=RapidOCR(params=make_config()['ocr']['params'])
        class Task:
            executor=SimpleNamespace(ocr_lib=lambda name:engine)
            def ocr(self,**kwargs):return []
            def find_one(self,*args,**kwargs):return None
            def next_frame(self):return self.frame
        task=Task()
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as tmp:
            port=RuntimePort(task,Path(tmp),{})
            task.frame=np.full((1080,1920,3),30,np.uint8)
            for name in ['AreaPageTitleFeature','AreaZxxyEnergy','AreaWeeklyCountText','AreaMiraCrownOverview']:
                x,y,w,h=port.manifest['regions'][name]['bbox']
                task.frame[y:y+h,x:x+w]=cv2.imread(str(ROOT/f'tests/fixtures/{name}.png'))
            self.assertTrue(port.exists('calendar_page'))
            self.assertEqual(read_fraction(port.text('AreaZxxyEnergy')),(300,350))
            self.assertEqual(read_fraction(port.text('AreaWeeklyCountText')),(2,2))
            self.assertEqual(read_fraction(port.text('AreaMiraCrownOverview')),(23,24))

    def test_calendar_title_fallback_when_entrance_artwork_changed(self):
        from types import SimpleNamespace
        class Task:
            title = '奇想日历'
            def next_frame(self): return np.full((1080, 1920, 3), 100, np.uint8)
            def find_one(self, name, **kwargs): return None
            def ocr(self, **kwargs):
                self.ocr_box = kwargs['box']
                return [SimpleNamespace(name=self.title)]
        task = Task()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.cache/tmp') as tmp:
            port = RuntimePort(task, Path(tmp), {})
            self.assertTrue(port.exists('calendar_page'))
            self.assertEqual((task.ocr_box.x, task.ocr_box.y), (99, 22))
            task.title = '奇迹之旅'
            self.assertFalse(port.exists('calendar_page'))

    def test_objective_board_can_use_recognized_label_when_old_entry_icon_is_missing(self):
        class Port(RuntimePort):
            def __init__(self):
                self.settings, self.scene, self.clicked = {}, 'home', []
            def exists(self, name):
                return name in {'home': {'IconPageMainFeature'}, 'calendar': {'calendar_page'},
                                'wish': {'IconZxxyFeature'}, 'starsea': {'IconXhsgFeature'}}[self.scene]
            def wait(self, name, timeout=6): return self.exists(name)
            def key(self, value): self.scene = 'calendar' if value == 'l' else 'home'
            def click_feature(self, name): raise AssertionError('Missing old artwork must not be clicked')
            def click_text(self, text, region=None, scroll=False):
                self.clicked.append(text)
                self.scene = {'朝夕心愿': 'wish', '星海拾光': 'starsea'}[text]
                return True
            def sleep(self, seconds): pass
        for board in ['wish', 'starsea']:
            with self.subTest(board=board):
                port = Port()
                port.open_objective_board(board)
                self.assertEqual(port.scene, board)
                self.assertEqual(len(port.clicked), 1)

    def test_invalid_capture_cannot_be_used_for_input(self):
        for frame in [None, np.zeros((1080, 1920, 3), dtype=np.uint8),
                      np.ones((1080, 2560, 3), dtype=np.uint8) * 100]:
            with self.assertRaises(RuntimeError):
                validate_frame(frame)
        validate_frame(np.ones((720, 1280, 3), dtype=np.uint8) * 100)

    def test_region_scales_and_pickup_search_stays_in_its_region(self):
        class Task:
            frame = np.ones((720, 1280, 3), dtype=np.uint8) * 100
            def find_one(self, name, **kwargs):
                self.search = kwargs
                return None
        task = Task()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.cache/tmp') as tmp:
            port = RuntimePort(task, Path(tmp), {})
            box = port.region('AreaPickup', task.frame)
            port.match('IconPickupFeature', task.frame)
            self.assertEqual(task.search['box'].x, box.x)
            self.assertEqual(task.search['box'].width, box.width)
            self.assertLessEqual(box.x + box.width, 1280)

    def test_evidence_is_synchronous_and_has_actual_pixels(self):
        class Task:
            frame = np.ones((720, 1280, 3), dtype=np.uint8) * 100
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.cache/tmp') as tmp:
            port = RuntimePort(Task(), Path(tmp), {})
            port.evidence('result')
            self.assertTrue(list(Path(tmp).glob('result*.png')))

    def test_error_evidence_never_waits_on_pause_aware_frame_property(self):
        from types import SimpleNamespace
        pixels = np.ones((720, 1280, 3), dtype=np.uint8) * 100
        class Task:
            executor = SimpleNamespace(nullable_frame=lambda: pixels)
            @property
            def frame(self):
                raise AssertionError('Pause-aware capture was accessed during cleanup')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.cache/tmp') as tmp:
            RuntimePort(Task(), Path(tmp), {}).evidence('cancelled')
            self.assertTrue(list(Path(tmp).glob('cancelled*.png')))
