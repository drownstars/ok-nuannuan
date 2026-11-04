import unittest
from nuannuan.core.errors import AutomationError
from nuannuan.daily.game_tools import GameTools


class EnterPort:
    def __init__(self, scene='main', effect=True):
        self.scene,self.effect,self.events,self.settings=scene,effect,[],{}
    def exists(self,name):
        return (name=='IconPageMainFeature' and self.scene in {'main','reward1','reward2'}
                or name=='IconPageLoginFeature' and self.scene=='login'
                or name=='IconDailyRewardFeature1' and self.scene=='reward1'
                or name=='IconDailyRewardFeature2' and self.scene=='reward2')
    def key(self,value):
        self.events.append(value)
        self.scene={'reward1':'reward2','reward2':'main'}.get(self.scene,self.scene)
    def click_text(self,*args):
        self.events.append('login_click')
        if self.effect:self.scene='main'
        return True
    def sleep(self,seconds):pass


class GameToolsEntryTests(unittest.TestCase):
    def test_loading_caption_takes_precedence_over_shared_login_artwork(self):
        from unittest.mock import patch
        class SharedLoginPort(LoadingPort):
            def exists(self, name):
                state = super().exists(name)
                return state or (self.scene == 'loading' and name in {'IconPageLoginFeature', 'game_loading'})
            def click_text(self, *args):
                assert self.seconds >= self.load_seconds, 'Loading page must not be clicked as a login page'
                return super().click_text(*args)
        port = SharedLoginPort(load_seconds=450)
        with patch('nuannuan.daily.game_tools.time.monotonic', side_effect=lambda: port.seconds):
            self.assertEqual(GameTools(port).enter()['status'], 'succeeded')
        self.assertEqual(port.events, ['login_click'])

    def test_observed_seven_minute_loading_is_allowed_without_repeated_input(self):
        from unittest.mock import patch
        port = LoadingPort(load_seconds=450)
        with patch('nuannuan.daily.game_tools.time.monotonic', side_effect=lambda: port.seconds):
            result = GameTools(port).enter()
        self.assertEqual(result['status'], 'succeeded')
        self.assertGreaterEqual(port.seconds, 450)
        self.assertEqual(port.events, ['login_click'])

    def test_recognized_loading_has_a_ten_minute_deadline(self):
        from unittest.mock import patch
        port = LoadingPort(load_seconds=700)
        with patch('nuannuan.daily.game_tools.time.monotonic', side_effect=lambda: port.seconds):
            with self.assertRaisesRegex(AutomationError, '超时'):
                GameTools(port).enter()
        self.assertEqual(port.seconds, 600)
        self.assertEqual(port.events, [])

    def test_short_unknown_transition_is_observed_without_guessing_a_click(self):
        from unittest.mock import patch
        port = LoadingPort(load_seconds=0, transition_seconds=3)
        with patch('nuannuan.daily.game_tools.time.monotonic', side_effect=lambda: port.seconds):
            result = GameTools(port).enter()
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(port.events, ['login_click'])

    def test_persistent_unknown_page_stops_without_input(self):
        from unittest.mock import patch
        port = LoadingPort(load_seconds=0, transition_seconds=100)
        with patch('nuannuan.daily.game_tools.time.monotonic', side_effect=lambda: port.seconds):
            with self.assertRaises(AutomationError):
                GameTools(port).enter()
        self.assertEqual(port.events, [])
        self.assertGreaterEqual(port.seconds, 15)
        self.assertLessEqual(port.seconds, 16)

    def test_launcher_close_never_guesses_an_unrelated_launcher_by_name(self):
        result=GameTools(EnterPort()).close_launcher()
        self.assertEqual(result['status'],'skipped')

    def test_reward_layers_are_closed_before_accepting_visible_hud(self):
        port=EnterPort('reward1')
        GameTools(port).enter(timeout=1)
        self.assertEqual(port.scene,'main')
        self.assertEqual(port.events,['f','f'])

    def test_ineffective_login_clicks_fail_bounded_instead_of_repeating_for_minutes(self):
        port=EnterPort('login',False)
        with self.assertRaisesRegex(AutomationError,'点击.*未.*变化|输入'):
            GameTools(port).enter(timeout=.1)
        self.assertLessEqual(port.events.count('login_click'),3)


class LoadingPort(EnterPort):
    def __init__(self, *, load_seconds, transition_seconds=0):
        super().__init__('loading')
        self.seconds = 0
        self.load_seconds = load_seconds
        self.transition_seconds = transition_seconds
    def exists(self, name):
        if self.scene != 'main':
            self.scene = ('loading' if self.seconds < self.load_seconds else
                          'unknown' if self.seconds < self.load_seconds+self.transition_seconds else 'login')
        return (name in {'IconUILoading', 'game_loading'} and self.scene == 'loading') or super().exists(name)
    def sleep(self, seconds):
        self.seconds += seconds
