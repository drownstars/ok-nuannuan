import math
import json
import tempfile
import unittest
from pathlib import Path

from nuannuan.routes import Route, RouteCatalog, RouteError, game_to_map, validate_macro
from nuannuan.navigation import RouteRunner
from nuannuan.config import ROOT


def route_data(action=None):
    return {'info': {'name': 'test', 'map': 'starsea', 'version': '2.0'}, 'points': [
        {'id': 0, 'position': [0, 0], 'move_mode': 'WALK', 'point_type': 'TARGET', 'action': 'TELEPORT'},
        {'id': 1, 'position': [450, 0], 'move_mode': 'WALK', 'point_type': 'TARGET', 'action': action},
    ]}


class RouteTests(unittest.TestCase):
    def test_material_target_and_expected_quantity_are_preserved(self):
        data = route_data('CATCH_INSECT')
        data['info'].update({'target': '暮暮蝶', 'count': '25'})
        route = Route.from_dict(data)
        self.assertEqual(route.material_target, '暮暮蝶')
        self.assertEqual(route.expected_count, 25)
        data['info']['count'] = 0
        self.assertIsNone(Route.from_dict(data).expected_count)

    def test_game_coordinates_do_not_truncate_decimals(self):
        self.assertAlmostEqual(game_to_map([45, 90], 'starsea')[0], 2449)
        self.assertAlmostEqual(game_to_map([45, 90], 'starsea')[1], 1053)

    def test_full_route_is_validated_before_input(self):
        for invalid in [float('nan'), float('inf'), 'x']:
            data = route_data()
            data['points'][1]['position'][0] = invalid
            with self.assertRaises(RouteError):
                Route.from_dict(data)
        for mutation in ['UNKNOWN_ACTION', 'UNSUPPORTED_ACTION']:
            with self.assertRaises(RouteError):
                Route.from_dict(route_data(mutation))
        data = route_data()
        data['points'][1]['id'] = 0
        with self.assertRaises(RouteError):
            Route.from_dict(data)

    def test_missing_macro_and_unbounded_loops_are_rejected(self):
        data = route_data('MACRO')
        data['points'][1]['action_params'] = 'missing'
        with self.assertRaises(RouteError):
            Route.from_dict(data, macros={})
        data = route_data()
        data['loops'] = [{'start_point_id': 0, 'end_point_id': 1, 'loop_count': 0}]
        with self.assertRaises(RouteError):
            Route.from_dict(data)

    def test_macro_rejects_unknown_steps_and_unreleased_inputs(self):
        for steps in [[{'type': 'shell', 'key': 'x'}],
                      [{'type': 'keyboard', 'key': 'w', 'action': 'press'}],
                      [{'type': 'gap', 'duration': 500}]]:
            with self.assertRaises(RouteError):
                validate_macro({'steps': steps})

    def test_malformed_route_files_do_not_break_the_catalog(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache/tmp') as folder:
            root = Path(folder)
            (root / 'array.json').write_text('[]', encoding='utf-8')
            (root / 'valid.json').write_text(json.dumps(route_data()), encoding='utf-8')
            catalog = RouteCatalog(root)
            self.assertEqual(len(catalog.errors), 1)
            self.assertEqual(len(catalog.inventory()), 1)

    def test_malformed_structures_have_route_errors(self):
        for data in [[], {'info': []}, {**route_data(), 'points': [None]},
                     {**route_data(), 'loops': [None]}]:
            with self.assertRaises(RouteError):
                Route.from_dict(data)


class NavigationPort:
    def __init__(self, stuck=False):
        self.pos = (2448., 1051.)
        self.stuck = stuck
        self.released = False
        self.moved = []
        self.acted = []

    def teleport(self, target, map_name):
        self.pos = target

    def locate(self, map_name, hint):
        return self.pos

    def pulse(self, key, duration, jump=False):
        self.moved.append(key)
        if not self.stuck:
            vectors = {'w': (30, 0), 'd': (0, 30), 's': (-30, 0), 'a': (0, -30)}
            delta = vectors[key]
            self.pos = (self.pos[0] + delta[0] * duration, self.pos[1] + delta[1] * duration)

    def release_all(self):
        self.released = True

    def action(self, point, route):
        self.acted.append(point.id)

    def evidence(self, name):
        pass

    def progress(self, *args):
        pass


class NavigationTests(unittest.TestCase):
    def test_route_attempts_one_unstuck_jump_before_failing(self):
        port=NavigationPort(stuck=True)
        attempts=[]
        port.unstuck=lambda:attempts.append('jump')
        with self.assertRaises(RouteError): RouteRunner(port).run(Route.from_dict(route_data()))
        self.assertEqual(attempts,['jump'])
        self.assertTrue(port.released)

    def test_crossed_path_point_is_not_chased_backwards(self):
        port=NavigationPort()
        data=route_data()
        data['points'][1]['point_type']='PATH'
        def overshoot(key,duration,jump=False):
            port.moved.append(key)
            port.pos=(port.pos[0]+20,port.pos[1])
        port.pulse=overshoot
        result=RouteRunner(port).run(Route.from_dict(data))
        self.assertTrue(result['reached_end'])
        self.assertEqual(port.moved,['w'])

    def test_zero_material_route_is_not_reported_as_collection_success(self):
        port = NavigationPort()
        port.material_counts = {'珠链蝶': 0}
        data = route_data('CATCH_INSECT')
        data['info']['target'] = '珠链蝶'
        result = RouteRunner(port).run(Route.from_dict(data))
        self.assertTrue(result['reached_end'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['materials'], {'珠链蝶': 0})

    def test_expected_observed_quantity_stops_before_later_points(self):
        port = NavigationPort()
        port.material_counts = {'珠链蝶': 0}
        def catch(point, route):
            port.acted.append(point.id)
            port.material_counts['珠链蝶'] += 1
        port.action = catch
        data = route_data('CATCH_INSECT')
        data['info'].update({'target': '珠链蝶', 'count': 1})
        data['points'].append({**data['points'][1], 'id': 2, 'position': [900, 0]})
        result = RouteRunner(port).run(Route.from_dict(data))
        self.assertEqual(port.acted, [1])
        self.assertTrue(result['expected_count_reached'])
        self.assertFalse(result['reached_end'])
    def test_route_reaches_final_point_using_observed_movement(self):
        port = NavigationPort()
        result = RouteRunner(port, tolerance=2).run(Route.from_dict(route_data('TAKE_PHOTO')))
        self.assertTrue(result['reached_end'])
        self.assertEqual(port.acted, [1])
        self.assertTrue(port.released)

    def test_stuck_stops_instead_of_recording_arrival(self):
        port = NavigationPort(stuck=True)
        with self.assertRaisesRegex(RouteError, '移动|卡住'):
            RouteRunner(port).run(Route.from_dict(route_data()))
        self.assertTrue(port.released)
        self.assertEqual(port.acted, [])

    def test_cancel_releases_inputs(self):
        class Cancelled(Exception):
            pass
        port = NavigationPort()
        def cancel(*args, **kwargs):
            raise Cancelled()
        port.pulse = cancel
        with self.assertRaises(Cancelled):
            RouteRunner(port).run(Route.from_dict(route_data()))
        self.assertTrue(port.released)

    def test_failed_ability_preparation_stops_before_teleport(self):
        port = NavigationPort()
        events = []
        def prepare(route):
            raise RouteError('能力未保存')
        port.prepare_abilities = prepare
        port.teleport = lambda *args: events.append('teleport')
        with self.assertRaisesRegex(RouteError, '能力未保存'):
            RouteRunner(port).run(Route.from_dict(route_data()))
        self.assertEqual(events, [])
        self.assertTrue(port.released)
