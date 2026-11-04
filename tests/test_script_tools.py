import tempfile
import unittest
from pathlib import Path

from nuannuan.config import ROOT
from nuannuan.routes.model import RouteError, validate_macro, RouteCatalog
from nuannuan.routes.store import RouteStore
from tests.test_routes import route_data


class ScriptToolTests(unittest.TestCase):
    def test_custom_flow_validates_all_steps_before_running_any(self):
        from nuannuan.routes.scripts import ScriptRunner
        events = []
        class Port:
            def execute_route(self, name): events.append(name)
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            store = RouteStore(folder)
            store.import_records([route_data()])
            runner = ScriptRunner(Port(), catalog=RouteCatalog(folder))
            with self.assertRaises(RouteError):
                runner.flow([{'type': 'path', 'script_name': 'test'}, {'type': 'macro', 'script_name': 'missing'}])
            self.assertFalse(events)

    def test_custom_flow_stops_at_failure_and_retains_results(self):
        from nuannuan.routes.scripts import ScriptRunner
        class Port:
            def execute_route(self, name): raise RouteError('blocked')
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            RouteStore(folder).import_records([route_data()])
            runner = ScriptRunner(Port(), catalog=RouteCatalog(folder))
            with self.assertRaises(RouteError): runner.flow([{'type': 'path', 'script_name': 'test'}])
            self.assertEqual(runner.results[0]['status'], 'failed')

    def test_macro_recorder_pairs_keys_and_closes_held_inputs_in_saved_data(self):
        from nuannuan.routes.scripts import MacroRecording
        recording = MacroRecording('我的宏')
        recording.feed('keyboard', 'w', 'press', 0)
        recording.feed('keyboard', 'w', 'press', .1)  # key-repeat is ignored
        recording.feed('keyboard', 'w', 'release', .2)
        recording.feed('keyboard', 'a', 'press', .3)
        data = recording.finish(.5)
        validate_macro(data)
        self.assertEqual(data['steps'][-1], {'type': 'keyboard', 'key': 'a', 'action': 'release'})
        self.assertAlmostEqual(sum(x.get('duration', 0) for x in data['steps']), .5)

    def test_macro_recorder_ignores_events_outside_game_and_no_shell_payload(self):
        from nuannuan.routes.scripts import MacroRecording
        recorder = MacroRecording('test')
        recorder.feed('keyboard', 'a', 'press', 0, in_game=False)
        with self.assertRaises(RouteError): recorder.feed('shell', 'cmd', 'press', .1)
        with self.assertRaises(RouteError): recorder.finish(.2)

    def test_route_recording_preserves_map_coordinates_and_imports_as_editable(self):
        from nuannuan.routes.scripts import RouteRecording
        from nuannuan.routes.model import game_to_map
        recorder = RouteRecording('我的路线', 'starsea')
        recorder.add(game_to_map([0, 0], 'starsea'), teleport=True)
        recorder.add(game_to_map([450, 90], 'starsea'))
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            store = RouteStore(folder)
            store.import_records([recorder.finish()])
            route = RouteCatalog(folder).get('我的路线')
            self.assertAlmostEqual(route.points[1].position[0], 450)
            self.assertAlmostEqual(route.points[1].position[1], 90)

    def test_minigame_requires_macro_and_explicit_fee_option(self):
        from nuannuan.daily.minigame import MinigameRunner
        class Port:
            extra_options = {'允许小游戏支付噗灵': False}
        with self.assertRaisesRegex(RouteError, '噗灵'):
            MinigameRunner(Port()).run({'steps': [{'type': 'gap', 'duration': 1}]})

    def test_macro_finite_loops_expand_and_unbounded_loops_fail(self):
        data = {'steps': [{'type': 'loop', 'loop_count': 3, 'loop_steps': 1},
                          {'type': 'gap', 'duration': .5}]}
        self.assertEqual(len(validate_macro(data)), 3)
        data['steps'][0]['loop_count'] = 0
        with self.assertRaises(RouteError): validate_macro(data)

    def test_macro_page_wait_is_validated_before_any_input(self):
        self.assertEqual(validate_macro({'steps': [{'type': 'wait_game_page', 'target_game_page': '主界面'}]})[0]['type'], 'wait_game_page')
        with self.assertRaises(RouteError):
            validate_macro({'steps': [{'type': 'goto_game_page', 'target_game_page': 'unknown'}]})

    def test_import_minigame_dependencies_follow_macro_conflicts_and_prevent_deletion(self):
        import copy
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/tmp') as folder:
            store = RouteStore(folder)
            macro = {'info': {'name': 'macro'}, 'steps': [{'type': 'gap', 'duration': .1}]}
            store.import_records([macro])
            different = copy.deepcopy(macro)
            different['steps'][0]['duration'] = .2
            route = route_data('MINIGAME')
            route['points'][1]['action_params'] = 'macro'
            names = store.import_records([route, different])
            actual = RouteCatalog(folder).get('test').points[1].params
            self.assertNotEqual(actual, 'macro')
            with self.assertRaises(RouteError): store.delete(actual)
