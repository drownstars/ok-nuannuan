"""Replay observed missed/late page transitions without injecting game input."""
import pytest

from nuannuan.ability_runtime import AbilityRuntime
from nuannuan.daily import AutomationError
from nuannuan.game_tools import GameTools
from nuannuan.runtime import RuntimePort


class PagePort:
    def __init__(self, failures=None, late=None):
        self.settings, self.scene, self.events = {}, 'home', []
        self.failures, self.late = dict(failures or {}), set(late or [])
        self.pending = None

    def exists(self, name):
        return name in {
            'home': {'IconPageMainFeature'}, 'map': {'bigmap_page'},
            'wardrobe': {'IconWardrobeFeature'}, 'ability': {'IconAbilityFeature'},
            'calendar': {'calendar_page', 'ButtonZxxyEntrance'}, 'wish': {'IconZxxyFeature'},
        }[self.scene]

    def key(self, value):
        self.events.append(('key', value))
        if value == 'esc':
            self.scene = 'home'
            return
        target = {'m': 'map', 'c': 'wardrobe', 'e': 'ability', 'l': 'calendar'}[value]
        if value == 'e':
            assert self.scene == 'wardrobe', 'Ability page must open from verified wardrobe'
        if self.failures.get(value, 0):
            self.failures[value] -= 1
            if value in self.late:
                self.pending = target
            return
        self.scene = target

    def wait(self, name, timeout=6):
        if self.pending:
            self.scene, self.pending = self.pending, None
            return False  # the page appeared at the timeout boundary
        return self.exists(name)

    def click_feature(self, name):
        assert name == 'ButtonZxxyEntrance' and self.scene == 'calendar'
        self.events.append(('click', name))
        if self.failures.get('entrance', 0):
            self.failures['entrance'] -= 1
        else:
            self.scene = 'wish'

    def evidence(self, name):
        self.events.append(('evidence', name))

    def workflow_progress(self, label, state, message=''):
        self.events.append(('progress', state))

    def sleep(self, seconds):
        pass


def test_map_hotkey_missed_once_recovers_and_reopens():
    port = PagePort({'m': 1})
    GameTools(port).goto('地图')
    assert port.scene == 'map'
    assert port.events.count(('key', 'm')) == 2
    assert any(event[0] == 'evidence' for event in port.events)


def test_late_map_page_is_not_toggled_closed_on_retry():
    port = PagePort({'m': 1}, late={'m'})
    GameTools(port).goto('地图')
    assert port.scene == 'map'
    assert port.events.count(('key', 'm')) == 1
    assert ('key', 'esc') not in port.events


def test_navigation_stops_after_two_failed_attempts():
    port = PagePort({'m': 100})
    with pytest.raises(AutomationError):
        GameTools(port).goto('地图')
    assert port.events.count(('key', 'm')) == 2


def test_second_attempt_late_page_is_confirmed_before_reporting_failure():
    port = PagePort({'m': 2})
    original_wait = port.wait
    attempts = 0
    def wait(name, timeout=6):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            port.scene = 'map'
            return False
        return original_wait(name, timeout)
    port.wait = wait
    GameTools(port).goto('地图')
    assert port.scene == 'map'
    assert port.events.count(('key', 'm')) == 2


def test_cancellation_propagates_without_a_second_navigation_attempt():
    class Cancelled(Exception):
        pass
    port = PagePort({'m': 1})
    def cancel(*args, **kwargs):
        raise Cancelled()
    port.wait = cancel
    with pytest.raises(Cancelled):
        GameTools(port).goto('地图')
    assert port.events.count(('key', 'm')) == 1


def test_ability_page_missed_once_recovers_through_wardrobe_again():
    port = PagePort({'e': 1})
    AbilityRuntime(port).open_ability_page()
    assert port.scene == 'ability'
    assert port.events.count(('key', 'c')) == 2
    assert port.events.count(('key', 'e')) == 2


def test_open_ability_page_is_reused_without_leaving_it():
    port = PagePort()
    port.scene = 'ability'
    AbilityRuntime(port).open_ability_page()
    assert port.events == []


def test_wish_entry_missed_once_reopens_board_without_running_a_task():
    port = PagePort({'entrance': 1})
    RuntimePort.open_objective_board(port, 'wish')
    assert port.scene == 'wish'
    assert port.events.count(('click', 'ButtonZxxyEntrance')) == 2
    assert port.events.count(('key', 'l')) == 2
