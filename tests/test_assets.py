import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AssetTests(unittest.TestCase):
    def test_tracking_sprites_and_regions_have_local_provenance(self):
        manifest=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
        for name in ['IconMaterialTypeAnimal','IconMaterialTypeInsect','StarCrystal']:
            self.assertIn(name,manifest.get('game_icons',{}))
            entry=manifest['game_icons'][name]
            self.assertEqual(hashlib.sha256((ROOT/entry['local_icon']).read_bytes()).hexdigest(),entry['sha256'])
        for name in ['AreaBigMapMaterialTypeSelect','AreaBigMapMaterialSelect','AreaBigMapMaterialTrackConfirm']:
            self.assertIn(name,manifest['regions'])

    def test_supplied_assets_have_provenance_and_valid_bounds(self):
        manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(manifest['features']), 16)
        for entry in [*manifest['features'].values(), *manifest['regions'].values()]:
            self.assertEqual(hashlib.sha256((ROOT / entry['authoring']).read_bytes()).hexdigest(), entry['authoring_sha256'])
            self.assertEqual(len(entry['sha256']), 64)  # Original provenance survives removal of the distribution.
            x, y, width, height = entry['bbox']
            self.assertTrue(0 <= x < x + width <= 1920)
            self.assertTrue(0 <= y < y + height <= 1080)

    def test_framework_matches_exported_features_and_rejects_black(self):
        import cv2
        import numpy as np
        from ok.feature.FeatureSet import FeatureSet

        manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))
        features = FeatureSet(False, None, 0.01, 0.01, template_folder=str(ROOT / 'assets/templates'))
        for name, entry in manifest['features'].items():
            with self.subTest(feature=name):
                frame = cv2.imread(str(ROOT / entry['authoring']))
                matches = features.find_one_feature(frame, name, threshold=0.95)
                self.assertTrue(matches, name)
                self.assertFalse(features.find_one_feature(np.zeros_like(frame), name, threshold=0.85), name)
        # Check frame-size change / scaled template loading with the real framework.
        entry = manifest['features']['IconSkipDialog']
        frame = cv2.resize(cv2.imread(str(ROOT / entry['authoring'])), (1280, 720))
        self.assertTrue(features.find_one_feature(frame, 'IconSkipDialog', threshold=0.9))
