import unittest

from nuannuan.daily import AutomationError


class FishingPort:
    def __init__(self, states):
        self.states = list(states)
        self.index = 0
        self.events = []
        self.settings = {}
    def fishing_state(self):
        value = self.states[min(self.index, len(self.states)-1)]
        self.index += 1
        return value
    def fishing_pull(self): self.events.append('pull')
    def mouse_right(self): self.events.append('right')
    def key(self, key): self.events.append(key)
    def exists(self, name): return name == 'IconPageMainFeature'
    def wait(self, name, timeout=6): return self.exists(name)
    def text(self, region): return '笔刷鱼×1.6kg'
    def sleep(self, seconds): pass
    def release_inputs(self): self.events.append('release')
    def select_ability(self, ability): self.events.append(ability)
    def evidence(self, name): pass


class GatheringTests(unittest.TestCase):
    def test_fishing_observes_strike_pull_and_result(self):
        from nuannuan.gathering import FishingRunner
        port = FishingPort(['wait', 'strike', 'pull', 'reel', 'result'])
        result = FishingRunner(port).run(casts=1, already_cast=True)
        self.assertEqual(result['caught'], 1)
        self.assertIn('s', port.events)
        self.assertIn('pull', port.events)
        self.assertEqual(port.events[-1], 'release')

    def test_no_fish_does_not_report_a_catch(self):
        from nuannuan.gathering import FishingRunner
        port = FishingPort(['empty'])
        result = FishingRunner(port).run(casts=3, already_cast=True)
        self.assertEqual(result['caught'], 0)

    def test_unknown_fishing_state_stops_and_releases(self):
        from nuannuan.gathering import FishingRunner
        port = FishingPort(['unknown'])
        with self.assertRaises(AutomationError):
            FishingRunner(port).run(casts=1, already_cast=True)
        self.assertEqual(port.events[-1], 'release')

    def test_cancel_releases_fishing_inputs(self):
        from nuannuan.gathering import FishingRunner
        class Cancelled(Exception): pass
        port = FishingPort(['pull'])
        def cancel(): raise Cancelled()
        port.fishing_pull = cancel
        with self.assertRaises(Cancelled): FishingRunner(port).run(casts=1, already_cast=True)
        self.assertEqual(port.events[-1], 'release')

    def test_home_route_requires_star_collect_ability(self):
        from tests.test_routes import route_data
        from nuannuan.routes import Route
        from nuannuan.ability import required_abilities
        route = Route.from_dict(route_data('FISHING_STAR'))
        self.assertIn('采星', required_abilities(route, {})[0])
