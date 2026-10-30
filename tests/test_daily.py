import unittest

from nuannuan.daily import AutomationError, DailyRunner


class GamePort:
    """Small game state simulator; observes state transitions, not API call counts."""
    def __init__(self, scene='home', dig_ready=True):
        self.scene = scene
        self.dig_ready = dig_ready
        self.keys = []
        self.clicked = []
        self.photo_works = True
        self.dispatch_works = True
        self.stuck = False
        self.artifacts = []

    def exists(self, name):
        names = {
            'home': {'IconPageMainFeature'},
            'menu': {'menu_page'},
            'photo': {'IconPhotoFeature'},
            'photo_result': {'IconPhotoEdit'},
            'dig': {'dig_page'} | ({'ButtonDigGather'} if self.dig_ready else {'dig_active'}),
            'dig_result': {'ButtonDigAgain'},
            'calendar': {'calendar_page', 'ButtonZxxyEntrance'},
            'wish': {'IconZxxyFeature'},
        }
        return name in names.get(self.scene, set())

    def wait(self, name, timeout=5):
        return self.exists(name)

    def key(self, value):
        self.keys.append(value)
        if self.stuck:
            return
        if value == 'esc':
            self.scene = 'menu' if self.scene == 'home' else 'home'
        elif value == 'p' and self.scene == 'home':
            self.scene = 'photo'
        elif value == 'space' and self.scene == 'photo' and self.photo_works:
            self.scene = 'photo_result'
        elif value == 'l' and self.scene == 'home':
            self.scene = 'calendar'

    def click_feature(self, name):
        self.clicked.append(name)
        if name == 'ButtonDigGather' and self.exists(name):
            self.scene = 'dig_result'
        elif name == 'ButtonDigAgain' and self.dispatch_works:
            self.dig_ready = False
            self.scene = 'dig'
        elif name == 'ButtonZxxyEntrance':
            self.scene = 'wish'

    def click_text(self, value, region=None, scroll=False):
        if value == '美鸭梨挖掘' and self.scene == 'menu':
            self.scene = 'dig'
            return True
        return False

    def text(self, region):
        return {'AreaDigingNumText': '4/4', 'AreaZxxyScore': '300'}.get(region, '')

    def claim_wish_rewards(self):
        return 2

    def sleep(self, seconds):
        pass

    def evidence(self, name):
        self.artifacts.append(name)


class DailyTests(unittest.TestCase):
    def test_recovery_is_bounded_and_prevents_actions_when_unknown(self):
        port = GamePort('unknown')
        port.stuck = True
        with self.assertRaises(AutomationError):
            DailyRunner(port).run_one('photo')
        self.assertNotIn('p', port.keys)
        self.assertLessEqual(len(port.keys), 8)
        self.assertTrue(port.artifacts, 'Recovery failure must leave diagnostic evidence')

    def test_photo_requires_observed_result_and_returns_home(self):
        port = GamePort()
        result = DailyRunner(port).run_one('photo')
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(port.scene, 'home')
        port.photo_works = False
        with self.assertRaisesRegex(AutomationError, '拍照'):
            DailyRunner(port).run_one('photo')

    def test_dig_collects_and_verifies_new_dispatch(self):
        port = GamePort()
        result = DailyRunner(port).run_one('dig')
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(port.clicked, ['ButtonDigGather', 'ButtonDigAgain'])
        self.assertEqual(port.scene, 'home')

    def test_dig_in_progress_never_clicks_again(self):
        port = GamePort(dig_ready=False)
        result = DailyRunner(port).run_one('dig')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(port.clicked, [])

    def test_dispatch_without_positive_ui_confirmation_fails(self):
        port = GamePort()
        port.dispatch_works = False
        with self.assertRaisesRegex(AutomationError, '挖掘'):
            DailyRunner(port).run_one('dig')

    def test_wish_claim_does_not_pretend_all_wishes_are_completed(self):
        port = GamePort()
        result = DailyRunner(port).run_one('wish')
        self.assertEqual(result['claimed'], 2)
        self.assertEqual(result['score'], '300')
        self.assertIn('已有奖励', result['message'])

    def test_batch_records_partial_failure_and_next_run_is_fresh(self):
        port = GamePort()
        port.photo_works = False
        runner = DailyRunner(port)
        results = runner.run_many(['photo', 'wish'])
        self.assertEqual([r['status'] for r in results], ['failed', 'succeeded'])
        self.assertTrue(port.artifacts)
        self.assertEqual(len(runner.run_many(['wish'])), 1)

    def test_cancellation_is_not_swallowed_as_task_failure(self):
        class Cancelled(Exception):
            pass

        port = GamePort()
        def cancel(*args):
            raise Cancelled()
        port.key = cancel
        with self.assertRaises(Cancelled):
            DailyRunner(port).run_many(['photo', 'wish'])

    def test_pass_requires_reward_result_for_each_tab(self):
        class PassPort(GamePort):
            scene = 'home'
            claimed = 0

            def key(self, value):
                if value == 'j':
                    self.scene = 'pass'
                elif value == 'f' and self.scene == 'reward':
                    self.scene = 'pass'
                    self.claimed += 1
                else:
                    super().key(value)

            def exists(self, name):
                if name == 'pass_page':
                    return self.scene == 'pass'
                if name == 'reward_popup':
                    return self.scene == 'reward'
                if name == 'ButtonMonthlyPassAward':
                    return self.scene == 'pass' and self.claimed < 2
                return super().exists(name)

            def click_text(self, *args, **kwargs):
                return self.scene == 'pass'

            def click_feature(self, name):
                if name == 'ButtonMonthlyPassAward':
                    self.scene = 'reward'
                else:
                    super().click_feature(name)

        port = PassPort()
        result = DailyRunner(port).run_one('pass')
        self.assertEqual(result['claimed'], 2)
        self.assertEqual(port.scene, 'home')

    def test_unrecognized_wish_reward_is_not_counted(self):
        port = GamePort()
        def fail():
            raise AutomationError('未出现奖励结果')
        port.claim_wish_rewards = fail
        with self.assertRaisesRegex(AutomationError, '奖励结果'):
            DailyRunner(port).run_one('wish')


class JourneyGatePort(GamePort):
    def __init__(self, pending=(), unknown_tab=None):
        super().__init__()
        self.pending = set(pending)
        self.tab, self.unknown_tab, self.events = None, unknown_tab, []

    def key(self, value):
        if value == 'j': self.scene = 'pass'
        elif value == 'f' and self.scene == 'reward':
            self.pending.discard(self.tab)
            self.scene = 'pass'
        else: super().key(value)

    def exists(self, name):
        if name == 'pass_page': return self.scene == 'pass' and self.tab != self.unknown_tab if self.tab else self.scene == 'pass'
        if name == 'reward_popup': return self.scene == 'reward'
        if name == 'ButtonMonthlyPassAward': return self.scene == 'pass' and self.tab in self.pending
        return super().exists(name)

    def click_text(self, value, region=None, scroll=False):
        self.events.append(('tab', value))
        self.tab = value
        return self.scene == 'pass'

    def click_feature(self, name):
        self.events.append(('claim', self.tab))
        self.scene = 'reward'


class JourneyGateTests(unittest.TestCase):
    def test_both_tabs_are_checked_before_any_reward_is_claimed(self):
        port = JourneyGatePort(['旅行任务', '旅行秘宝'])
        result = DailyRunner(port).run_one('pass')
        first_claim = next(i for i, event in enumerate(port.events) if event[0] == 'claim')
        self.assertEqual(port.events[:2], [('tab', '旅行任务'), ('tab', '旅行秘宝')])
        self.assertGreaterEqual(first_claim, 2)
        self.assertEqual(result['claimed'], 2)

    def test_no_pending_rewards_skip_without_claiming_and_keep_check_evidence(self):
        port = JourneyGatePort()
        result = DailyRunner(port).run_one('pass')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['claimed'], 0)
        self.assertEqual(len(result['checked_tabs']), 2)
        self.assertFalse(any(item['pending'] for item in result['checked_tabs']))
        self.assertFalse(any(event[0] == 'claim' for event in port.events))

    def test_unknown_second_tab_prevents_claiming_even_when_first_has_rewards(self):
        port = JourneyGatePort(['旅行任务'], unknown_tab='旅行秘宝')
        result = DailyRunner(port).run_one('pass')
        self.assertEqual(result['status'], 'skipped')
        self.assertIn('未确认', result['message'])
        self.assertFalse(any(event[0] == 'claim' for event in port.events))
