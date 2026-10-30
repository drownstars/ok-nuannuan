import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from nuannuan.config import ROOT
from nuannuan.route_store import RouteStore
from test_routes import route_data


class RouteInstallTests(unittest.TestCase):
    def test_reinstall_preserves_user_changes_and_deletions(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as directory:
            root = Path(directory)
            source = root / 'whimbox_app/python-embedded/Lib/site-packages/whimbox/assets'
            scripts = root / 'whimbox_app/scripts'
            scripts.mkdir(parents=True)
            maps = source / 'imgs/Maps'
            maps.mkdir(parents=True)
            import cv2
            import numpy as np
            for prefix in ['w01_v12', 'w14000000_v2', 'w8000001_v1', 'w4020034']:
                for scale in ['05x', '0125x']:
                    cv2.imwrite(str(maps / f'{prefix}_luma_{scale}.png'), np.zeros((8, 8), dtype=np.uint8))
            (source / 'checkpoints.json').write_text('{}', encoding='utf-8')
            (scripts / 'builtin.json').write_text(json.dumps(route_data()), encoding='utf-8')
            spec = importlib.util.spec_from_file_location('route_install_test', ROOT / 'tools/import_routes.py')
            importer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(importer)
            importer.ROOT = root
            importer.main()
            store = RouteStore(root / 'routes')
            edited = store.get_data('test')
            edited['points'][1]['position'][0] = 1000
            store.update('test', edited)
            importer.main()
            self.assertEqual(store.get_data('test')['points'][1]['position'][0], 1000)
            store.delete('test')
            importer.main()
            self.assertFalse((root / 'routes/builtin.json').exists())
