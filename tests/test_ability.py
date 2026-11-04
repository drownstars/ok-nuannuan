import unittest

from nuannuan.routes.ability import AbilityManager, required_abilities, allocate_slots
from nuannuan.routes.model import Route, RouteError
from test_routes import route_data


class AbilityPort:
    def __init__(self):
        self.events = []
        self.slots = {1: '钓鱼', 2: '捕虫'}
        self.jump = '悬羽'
        self.save_works = True
        self.settings = {}
    def open_ability_page(self):
        self.events.append('open')
    def choose_ability_plan(self, value):
        self.events.append(('plan', value))
    def read_ability_slots(self):
        return dict(self.slots)
    def read_jump_ability(self):
        return self.jump
    def set_ability_slot(self, slot, name):
        self.events.append(('set', slot, name))
        if self.save_works:
            if slot == 'jump': self.jump = name
            else: self.slots[slot] = name
    def save_abilities(self):
        self.events.append('save')
    def recover_home(self):
        self.events.append('home')
    def activate_ability(self, slot, name):
        self.events.append(('activate', slot, name))


class AbilityTests(unittest.TestCase):
    def test_route_actions_and_jump_requirements_are_combined_with_overrides(self):
        data = route_data('CATCH_INSECT')
        data['points'][1]['move_mode'] = 'JUMP'
        route = Route.from_dict(data)
        need = required_abilities(route, {'跳跃能力': '漂浮', '主能力': '化万相'})
        self.assertEqual(need, (('捕虫', '化万相'), '漂浮', '化万相'))

    def test_existing_required_slots_are_preserved(self):
        assignment = allocate_slots({1: '钓鱼', 2: '捕虫'}, ['捕虫', '化万相'])
        self.assertEqual(assignment['捕虫'], 2)
        self.assertNotEqual(assignment['化万相'], 2)

    def test_saved_abilities_are_verified_before_returning(self):
        port = AbilityPort()
        manager = AbilityManager(port)
        route = Route.from_dict(route_data('CATCH_INSECT'))
        result = manager.prepare(route, {'能力方案': 3, '主能力': '自动', '跳跃能力': '漂浮'})
        self.assertEqual(result['捕虫'], 2)
        self.assertNotIn('save', port.events)
        self.assertIn(('activate', 2, '捕虫'), port.events)

    def test_failed_save_stops_before_returning_to_world_or_activation(self):
        port = AbilityPort()
        port.save_works = False
        route = Route.from_dict(route_data('CATCH_INSECT'))
        with self.assertRaises(RouteError):
            AbilityManager(port).prepare(route, {'主能力': '化万相'})
        self.assertFalse(any(isinstance(e, tuple) and e[0] == 'activate' for e in port.events))
