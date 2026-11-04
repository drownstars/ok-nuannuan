import unittest

from nuannuan.core.errors import AutomationError
from nuannuan.daily.objectives import Objective, Snapshot, classify, parse_score
from nuannuan.daily.objective_runner import ObjectiveRunner


class ObjectiveTests(unittest.TestCase):
    def test_specific_rules_before_generic_photo_or_energy(self):
        self.assertEqual(classify('wish', '拍摄一张照片'), 'photo')
        self.assertEqual(classify('wish', '消耗150点活跃能量'), 'energy')
        self.assertEqual(classify('wish', '采集5株植物'), 'pickup')
        self.assertEqual(classify('starsea', '和漂流瓶合影留念'), 'bottle_photo')
        self.assertEqual(classify('starsea', '拍下你的存在'), 'photo')
        self.assertEqual(classify('starsea', '与3次动物互动'), 'animal_three')
        self.assertEqual(classify('starsea', '对星绘图册中的照片点赞'), 'lookbook')

    def test_ocr_whitespace_unknown_and_empty_are_preserved(self):
        self.assertEqual(classify('wish', '采 集 3 株\n植 物'), 'pickup')
        self.assertEqual(classify('wish', '全新的活动要求'), 'unknown')
        self.assertEqual(classify('starsea', ''), 'unknown')

    def test_score_does_not_turn_unreadable_text_into_zero(self):
        for text in ['', 'O0O', '550', '50', '1000']:
            with self.assertRaises(AutomationError):
                parse_score(text)
        self.assertEqual(parse_score('300/500'), 300)
        self.assertEqual(parse_score('0'), 0)


class ObjectivePort:
    def __init__(self):
        self.items = [Objective(0, '拍摄照片', 'photo', False), Objective(1, '新活动', 'unknown', False)]
        self.score = 0
        self.effect = True
        self.actions = []

    def scan_objectives(self, board):
        return Snapshot(board, self.score, list(self.items))

    def supports_objective(self, board, item):
        return '' if item.kind == 'photo' else '此任务尚无执行流程'

    def perform_objective(self, board, item):
        self.actions.append(item.slot)
        if self.effect:
            self.items[0] = Objective(0, '拍摄照片', 'photo', True)
            self.score = 100

    def claim_objective_rewards(self, board):
        return 1

    def evidence(self, name):
        pass


class ObjectiveRunnerTests(unittest.TestCase):
    def test_confirmed_daily_score_can_finish_without_claiming_a_specific_card_finished(self):
        port = ObjectivePort()
        port.score = 300
        scans, messages = [], []
        original_scan = port.scan_objectives
        def scan(board):
            scans.append(board)
            return original_scan(board)
        port.scan_objectives = scan
        port.workflow_progress = lambda label, state, message='': messages.append((label, state, message))
        def reach_goal(board, item):
            port.actions.append(item.slot)
            port.score = 500
            port.items = []  # score-first scanner skips card reads once the board is full
        port.perform_objective = reach_goal
        result = ObjectiveRunner(port).run('wish')
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['attempts'][0]['status'], 'succeeded')
        self.assertEqual(result['attempts'][0]['confirmation'], 'daily_score')
        self.assertEqual(port.actions, [0])
        self.assertEqual(len(scans), 2)
        self.assertNotIn('识别 0 项', result['message'])
        self.assertTrue(any('拍摄照片' in message for _, _, message in messages))
        self.assertTrue(any('500/500' in message for _, _, message in messages))

    def test_already_full_board_only_checks_score_and_claims_rewards(self):
        port = ObjectivePort()
        port.score, port.items = 500, []
        calls = []
        scan = port.scan_objectives
        port.scan_objectives = lambda board: (calls.append(board), scan(board))[1]
        result = ObjectiveRunner(port).run('wish')
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(port.actions, [])
        self.assertEqual(calls, ['wish'])
        self.assertEqual(result['claimed'], 1)

    def test_official_priority_and_score_order_is_used_for_both_boards(self):
        for board, kinds, expected in [
            ('wish', ['fight', 'dig', 'insect', 'photo', 'pickup', 'realm', 'energy'],
             ['realm', 'energy', 'photo', 'pickup', 'insect', 'fight', 'dig']),
            ('starsea', ['crystal', 'music', 'bottle_delivery', 'photo', 'animal_three', 'bottle_pickup'],
             ['animal_three', 'photo', 'music', 'bottle_pickup', 'bottle_delivery', 'crystal']),
        ]:
            with self.subTest(board=board):
                port = ObjectivePort()
                port.items = [Objective(i, kind, kind, False) for i, kind in enumerate(kinds)]
                port.supports_objective = lambda *args: ''
                def complete(board, item):
                    port.actions.append(item.kind)
                    port.items = [Objective(i.slot, i.text, i.kind, i.completed or i.slot == item.slot)
                                  for i in port.items]
                port.perform_objective = complete
                ObjectiveRunner(port).run(board)
                self.assertEqual(port.actions, expected)

    def test_first_listed_realm_can_complete_the_later_energy_card(self):
        port = ObjectivePort()
        port.items = [Objective(0, '祝福闪光幻境', 'bless', False),
                      Objective(1, '消耗150点活跃能量', 'energy', False)]
        def complete_both(board, item):
            port.actions.append(item.kind)
            port.items = [Objective(i.slot, i.text, i.kind, True) for i in port.items]
            port.score = 200
        port.supports_objective = lambda *args: ''
        port.perform_objective = complete_both
        ObjectiveRunner(port).run('wish')
        self.assertEqual(port.actions, ['bless'])

    def test_recorded_300_point_board_uses_first_energy_card_and_skips_remaining_realms_at_goal(self):
        port = ObjectivePort()
        port.score = 300
        port.items = [Objective(0, '消耗150点活跃能量', 'energy', False),
                      Objective(1, '升级祝福闪光', 'upgrade_bless', False),
                      Objective(2, '魔物试炼', 'monster_realm', False)]
        port.supports_objective = lambda *args: ''
        def complete(board, item):
            port.actions.append(item.kind)
            port.score, port.items = 500, []
        port.perform_objective = complete
        result = ObjectiveRunner(port).run('wish')
        self.assertEqual(port.actions, ['energy'])
        self.assertEqual(result['status'], 'succeeded')

    def test_identification_only_never_executes(self):
        port = ObjectivePort()
        result = ObjectiveRunner(port).run('wish', execute=False)
        self.assertEqual(port.actions, [])
        self.assertEqual(result['snapshot']['score'], 0)
        self.assertEqual(len(result['snapshot']['objectives']), 2)

    def test_completion_requires_observed_card_and_does_not_infer_score(self):
        port = ObjectivePort()
        port.effect = False
        result = ObjectiveRunner(port).run('wish')
        self.assertEqual(result['snapshot']['score'], 0)
        self.assertEqual(result['attempts'][0]['status'], 'failed')
        self.assertEqual(result['status'], 'partial')

    def test_finished_cards_and_unknowns_are_not_executed(self):
        port = ObjectivePort()
        port.items[0] = Objective(0, '拍摄照片', 'photo', True)
        result = ObjectiveRunner(port).run('starsea')
        self.assertEqual(port.actions, [])
        self.assertTrue(result['unsupported'])

    def test_each_run_gets_a_fresh_snapshot(self):
        port = ObjectivePort()
        runner = ObjectiveRunner(port)
        runner.run('wish')
        result = runner.run('wish', execute=False)
        self.assertTrue(result['snapshot']['objectives'][0]['completed'])
        self.assertEqual(result['attempts'], [])

    def test_one_action_completing_another_card_does_not_execute_it_twice(self):
        port = ObjectivePort()
        port.items = [Objective(0, '拍摄照片', 'photo', False), Objective(1, '拍摄照片', 'photo', False)]
        def complete_both(board, item):
            port.actions.append(item.slot)
            port.items = [Objective(i, '拍摄照片', 'photo', True) for i in range(2)]
            port.score = 200
        port.perform_objective = complete_both
        ObjectiveRunner(port).run('wish')
        self.assertEqual(port.actions, [0])

    def test_cancellation_is_propagated(self):
        class Cancelled(Exception):
            pass
        port = ObjectivePort()
        def cancel(*args):
            raise Cancelled()
        port.perform_objective = cancel
        with self.assertRaises(Cancelled):
            ObjectiveRunner(port).run('wish')

    def test_daily_does_not_take_a_photo_when_no_unfinished_photo_card_exists(self):
        port = ObjectivePort()
        port.items = [Objective(0, '拍摄照片', 'photo', True), Objective(1, '全新任务', 'unknown', False)]
        ObjectiveRunner(port).run('wish')
        self.assertEqual(port.actions, [])
