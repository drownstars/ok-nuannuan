import unittest
from pathlib import Path
from types import SimpleNamespace

from nuannuan.route_runtime import RouteRuntime
from nuannuan.routes import RouteCatalog, RouteError


class Interaction:
    def __init__(self):
        self.events = []
    def send_key_down(self, key):
        self.events.append(('down', key))
    def send_key_up(self, key):
        self.events.append(('up', key))


class RouteRuntimeTests(unittest.TestCase):
    def make_port(self):
        interaction = Interaction()
        executor = SimpleNamespace(interaction=interaction, paused=False, current_task=SimpleNamespace(paused=False),
                                   check_enabled=lambda **kwargs: None)
        task = SimpleNamespace(executor=executor, validate_key=lambda key: key,info_set=lambda *args:None)
        return SimpleNamespace(task=task, settings={}, fresh=lambda: None,
                               sleep=lambda seconds: interaction.events.append(('sleep', seconds)))

    def test_route_tracking_action_records_only_observed_material_count(self):
        from unittest.mock import patch
        from test_material_tracking import TrackPort
        from test_routes import route_data
        from nuannuan.routes import Route
        port=self.make_port()
        runtime=RouteRuntime(port)
        data=route_data('CATCH_INSECT')
        data['info']['target']='珠链蝶'
        route=Route.from_dict(data)
        adapter=TrackPort([{'active':True,'marker':None}]*2,['','珠链蝶×1'])
        with patch('nuannuan.tracking_runtime.TrackingRuntime',return_value=adapter):
            runtime.action(route.points[1],route)
        self.assertEqual(runtime.material_counts,{'珠链蝶':1})

    def test_interruption_releases_before_wait_and_relocalizes(self):
        from test_routes import route_data
        from nuannuan.routes import Route
        port=self.make_port()
        events=[]
        states=iter([False,False,True,True])
        port.exists=lambda name:next(states,True)
        port.sleep=lambda seconds:events.append('wait')
        runtime=RouteRuntime(port)
        runtime.held_keys.add('w')
        runtime.locate=lambda *args:events.append('locate') or (1,2)
        result=runtime.check_interruption(Route.from_dict(route_data()),(1,2),(0,0))
        self.assertEqual(result,(1,2))
        self.assertEqual(port.task.executor.interaction.events[0],('up','w'))
        self.assertEqual(events[-1],'locate')
        self.assertFalse(runtime.held_keys)

    def test_interruption_wait_is_bounded_and_preserves_unknown_modal(self):
        from test_routes import route_data
        from nuannuan.routes import Route
        port=self.make_port()
        port.exists=lambda name:False
        runtime=RouteRuntime(port)
        with self.assertRaisesRegex(RouteError,'主界面|中断'):
            runtime.check_interruption(Route.from_dict(route_data()),(1,2),(0,0))
        self.assertFalse(any(event[0]=='down' for event in port.task.executor.interaction.events))

    def test_pause_releases_key_before_pause_aware_wait(self):
        port = self.make_port()
        runtime = RouteRuntime(port)
        original_down = port.task.executor.interaction.send_key_down
        def pause_on_down(key):
            original_down(key)
            port.task.executor.current_task.paused = True
        port.task.executor.interaction.send_key_down = pause_on_down
        completed = runtime.hold('w', 1)
        self.assertFalse(completed)
        self.assertEqual(port.task.executor.interaction.events[:2], [('down', 'w'), ('up', 'w')])
        self.assertFalse(runtime.held_keys)

    def test_cancelled_macro_releases_held_keys(self):
        class Cancelled(Exception):
            pass
        port = self.make_port()
        runtime = RouteRuntime(port)
        calls = []
        def cancel(**kwargs):
            calls.append(1)
            if len(calls) >= 2:
                raise Cancelled()
        port.task.executor.check_enabled = cancel
        macro = {'steps': [{'type': 'keyboard', 'key': 'w', 'action': 'press'},
                           {'type': 'gap', 'duration': 1},
                           {'type': 'keyboard', 'key': 'w', 'action': 'release'}]}
        with self.assertRaises(Cancelled):
            runtime.macro(macro)
        self.assertEqual(port.task.executor.interaction.events, [('down', 'w'), ('up', 'w')])
        self.assertFalse(runtime.held_keys)

    def test_macro_mouse_release_uses_its_recorded_position(self):
        port = self.make_port()
        interaction = port.task.executor.interaction
        port.task.executor.nullable_frame = lambda: SimpleNamespace(shape=(1080, 1920, 3))
        interaction.mouse_down = lambda x, y, key: interaction.events.append(('mouse_down', x, y, key))
        interaction.mouse_up = lambda key: interaction.events.append(('mouse_up', key))
        interaction.move = lambda x, y: interaction.events.append(('move', x, y))
        RouteRuntime(port).macro({'steps': [
            {'type': 'mouse', 'key': 'mouse_left', 'action': 'press', 'position': [100, 100]},
            {'type': 'mouse', 'key': 'mouse_left', 'action': 'release', 'position': [200, 200]}]})
        self.assertEqual(interaction.events[1:3], [('move', 200, 200), ('mouse_up', 'left')])

    def test_reference_routes_pass_teleporter_preflight_and_chat_is_explicit(self):
        port = self.make_port()
        catalog = RouteCatalog()
        ready = [row for row in catalog.inventory() if row['ready']]
        self.assertEqual(len(ready), 24)
        port.extra_options = {'允许小游戏支付噗灵': True}
        runtime = RouteRuntime(port, allow_chat=True)
        for row in ready:
            runtime.preflight(catalog.get(row['name']))
        with self.assertRaisesRegex(RouteError, '聚会聊天'):
            RouteRuntime(port).preflight(catalog.get('星海拾光_聚会聊天'))
        port.extra_options['允许小游戏支付噗灵'] = False
        with self.assertRaisesRegex(RouteError, '噗灵'):
            RouteRuntime(port).preflight(catalog.get('朝夕心愿_小游戏'))

    def test_animal_reference_migration_preserves_original_and_adds_action(self):
        from nuannuan.config import ROOT
        import json
        original = json.loads((ROOT / 'tests/fixtures/original-animal-route.json').read_text(encoding='utf-8'))
        self.assertGreater(len(original['points']), len({p['id'] for p in original['points']}))
        route = RouteCatalog().get('星海拾光_化身动物')
        self.assertEqual(route.points[-1].action, 'TRANS_ANIMAL')
        self.assertEqual(route.points[-1].params, '3')
