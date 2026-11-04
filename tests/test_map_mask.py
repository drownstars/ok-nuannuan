import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from nuannuan.config import ROOT
from nuannuan.routes.model import RouteError, game_to_map


class MapMaskTests(unittest.TestCase):
    def test_original_point_format_and_game_coordinates_import(self):
        from nuannuan.map.mask import PointLibrary
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as folder:
            library = PointLibrary(Path(folder)/'points.json')
            imported = library.import_data([
                {'id': 'a', 'label_id': 'plant', 'name': '植物', 'map_name': 'starsea', 'image_x': 1000, 'image_y': 2000},
                {'id': 'b', 'label_id': 'fish', 'name': '钓鱼', 'map_name': 'starsea', 'game_x': 45, 'game_y': 90},
            ])
            self.assertEqual(imported, 2)
            points = library.points()
            self.assertEqual((points[1].x, points[1].y), game_to_map((45, 90), 'starsea'))
            self.assertEqual(len(PointLibrary(library.path).points()), 2)

    def test_invalid_point_batch_preserves_existing_library(self):
        from nuannuan.map.mask import PointLibrary
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as folder:
            library = PointLibrary(Path(folder)/'points.json')
            library.import_data([{'id': 'a', 'name': '原有', 'map_name': 'home', 'image_x': 1, 'image_y': 2}])
            before = library.path.read_bytes()
            with self.assertRaises(RouteError):
                library.import_data([{'id': 'b', 'map_name': 'home', 'image_x': 5, 'image_y': 5},
                                     {'id': 'bad', 'map_name': 'unknown', 'image_x': float('nan'), 'image_y': 0}])
            self.assertEqual(library.path.read_bytes(), before)

    def test_projection_clips_to_bigmap_and_minimap_circle(self):
        from nuannuan.map.mask import MaskPoint, Viewport, project_points
        points = [MaskPoint('a', '植物', 'plant', 'starsea', 1000, 1000),
                  MaskPoint('b', '植物', 'plant', 'starsea', 1062, 1000),
                  MaskPoint('other', '其他图', 'plant', 'home', 1000, 1000),
                  MaskPoint('outside', '远处', 'plant', 'starsea', 9999, 9999)]
        viewport = Viewport('starsea', 'bigmap', (1000, 1000), .62, (320, 156, 1280, 768))
        markers = project_points(points, viewport)
        self.assertEqual([m.id for m in markers], ['a', 'b'])
        self.assertEqual((markers[1].x, markers[1].y), (1060, 540))
        mini = Viewport('starsea', 'minimap', (1000, 1000), .8, (81, 22, 200, 200))
        corner = MaskPoint('corner', '角落', 'plant', 'starsea', 1076, 1076)
        self.assertEqual(project_points([corner], mini), [])

    def test_no_position_guess_is_drawn_on_unknown_or_unseeded_page(self):
        import numpy as np
        from nuannuan.map.mask import MapMaskEngine
        engine = MapMaskEngine(locator=SimpleNamespace())
        frame = np.full((1080, 1920, 3), 60, dtype=np.uint8)
        self.assertIsNone(engine.observe(frame, lambda name: False, 'starsea').viewport)
        result = engine.observe(frame, lambda name: name == 'IconPageMainFeature', 'starsea')
        self.assertIsNone(result.viewport)
        self.assertIn('大地图', result.message)

    def test_wrong_zoom_never_reuses_last_bigmap_projection(self):
        import numpy as np
        from nuannuan.map.mask import MapMaskEngine
        engine = MapMaskEngine(locator=SimpleNamespace())
        frame = np.full((1080, 1920, 3), 60, dtype=np.uint8)
        result = engine.observe(frame, lambda name: name == 'IconUIBigmap', 'starsea')
        self.assertIsNone(result.viewport)
        self.assertIn('最大', result.message)

    def test_dpi_conversion_preserves_monitor_origin(self):
        from nuannuan.map.mask import logical_rect
        self.assertEqual(logical_rect((-1800, 100, 1200, 800), (-1920, 0), (-1536, 0), 1.25),
                         (-1440, 80, 960, 640))

    def test_builtin_points_use_real_checkpoints_and_selected_route(self):
        from nuannuan.map.mask import builtin_points
        points = builtin_points('星海拾光_更改音乐')
        self.assertTrue(any(p.label == 'teleport' for p in points))
        self.assertTrue(any(p.label == 'route' for p in points))
        self.assertFalse(any(p.id.startswith('sample_') for p in points))

    def test_stable_bigmap_uses_real_map_match_before_projection(self):
        import cv2
        import numpy as np
        from nuannuan.map.mask import MapMaskEngine
        from nuannuan.map.vision import MapLocator
        rng = np.random.default_rng(11)
        atlas = rng.integers(20, 220, (400, 500), dtype=np.uint8)
        patch = atlas[170:230, 200:300]
        frame = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        image = cv2.resize(patch, (1280, 768), interpolation=cv2.INTER_NEAREST)
        frame[156:924, 320:1600] = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        engine = MapMaskEngine(MapLocator(images={'starsea': {'0125x': atlas}}))
        features = lambda name: name in {'IconUIBigmap', 'IconBigMapMaxScale'}
        self.assertIsNone(engine.observe(frame, features, 'starsea').viewport)
        observed = engine.observe(frame, features, 'starsea')
        self.assertIsNotNone(observed.viewport)
        self.assertLess(np.linalg.norm(np.array(observed.viewport.center)-(2000, 1600)), 12)

    def test_category_and_resource_filters_do_not_mix_labels(self):
        from nuannuan.map.mask import MaskPoint, filtered_points
        points = [MaskPoint(label, label, label, 'starsea', 1, 1) for label in ['teleport', 'route', '植物', '昆虫']]
        selected = list(filtered_points(points, {'显示流转之柱': False, '显示路线点位': False, '资源类型': '植物'}))
        self.assertEqual([p.label for p in selected], ['植物'])
        selected = list(filtered_points(points, {'显示导入点位': False}))
        self.assertEqual([p.label for p in selected], ['teleport', 'route'])
