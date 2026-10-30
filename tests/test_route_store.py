import copy
import json
import tempfile
import unittest
from pathlib import Path

from nuannuan.config import ROOT
from nuannuan.route_store import RouteStore
from nuannuan.routes import RouteCatalog, RouteError
from test_routes import route_data


class RouteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp')
        self.root = Path(self.tmp.name)
        self.store = RouteStore(self.root)
    def tearDown(self):
        self.tmp.cleanup()

    def test_import_edit_rename_and_delete_preserve_history_and_aliases(self):
        self.store.import_records([route_data()])
        edited = self.store.get_data('test')
        edited['info']['name'] = 'renamed'
        edited['points'][1]['position'] = [500, 250]
        self.store.update('test', edited)
        self.assertEqual(RouteCatalog(self.root).get('test').name, 'renamed')
        self.assertEqual(RouteCatalog(self.root).get('test').origin_name, 'test')
        self.assertEqual(self.store.get_data('renamed')['points'][1]['position'], [500, 250])
        self.store.delete('renamed')
        self.assertEqual(RouteCatalog(self.root).inventory(), [])
        self.assertTrue(list((self.root / '.library/history').glob('*.json')))

    def test_invalid_import_batch_writes_nothing(self):
        invalid = route_data()
        invalid['info']['name'] = 'invalid'
        invalid['points'][1]['position'][0] = float('nan')
        with self.assertRaises(RouteError):
            self.store.import_records([route_data(), invalid])
        self.assertFalse(list(self.root.glob('*.json')))

    def test_different_content_with_same_name_is_imported_without_overwrite(self):
        self.store.import_records([route_data()])
        second = route_data()
        second['points'][1]['position'][0] = 900
        names = self.store.import_records([second])
        self.assertNotEqual(names[0], 'test')
        self.assertEqual(self.store.get_data('test')['points'][1]['position'][0], 450)

    def test_macro_dependencies_are_validated_in_same_import_batch(self):
        route = route_data('MACRO')
        route['points'][1]['action_params'] = 'macro'
        macro = {'info': {'name': 'macro'}, 'steps': [{'type': 'gap', 'duration': .1}]}
        self.store.import_records([route, macro])
        self.assertTrue(RouteCatalog(self.root).get('test'))
        with self.assertRaises(RouteError):
            self.store.delete('macro')

    def test_bad_edit_preserves_previous_file(self):
        self.store.import_records([route_data()])
        bad = self.store.get_data('test')
        bad['points'] = []
        with self.assertRaises(RouteError):
            self.store.update('test', bad)
        self.assertEqual(len(self.store.get_data('test')['points']), 2)

    def test_path_like_names_never_escape_the_library(self):
        data = route_data()
        data['info']['name'] = '../outside'
        self.store.import_records([data])
        self.assertTrue(self.store.get_data('../outside'))
        self.assertFalse((self.root.parent / 'outside.json').exists())

    def test_json_bundle_import_resolves_renamed_macro_dependencies(self):
        macro = {'info': {'name': 'macro'}, 'steps': [{'type': 'gap', 'duration': .1}]}
        self.store.import_records([macro])
        route = route_data('MACRO')
        route['points'][1]['action_params'] = 'macro'
        changed = copy.deepcopy(macro)
        changed['steps'][0]['duration'] = .2
        source = self.root / '.input'
        source.mkdir()
        path = source / 'bundle.json'
        path.write_text(json.dumps({'routes': [route], 'macros': [changed]}), encoding='utf-8')
        self.store.import_files([path])
        imported = RouteCatalog(self.root).get('test')
        self.assertNotEqual(imported.points[1].params, 'macro')
        self.assertEqual(imported.macros[imported.points[1].params]['steps'][0]['duration'], .2)
