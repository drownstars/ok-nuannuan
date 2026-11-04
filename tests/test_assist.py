import unittest

from nuannuan.tasks.assist import AssistGate


class AssistGateTests(unittest.TestCase):
    def test_pickup_requires_home_and_two_consecutive_frames(self):
        gate = AssistGate(cooldown=0.5)
        self.assertIsNone(gate.decide(False, True, False, 0))
        self.assertIsNone(gate.decide(True, True, False, 1))
        self.assertEqual(gate.decide(True, True, False, 1.2), 'pickup')

    def test_disappearance_resets_confirmation(self):
        gate = AssistGate()
        gate.decide(True, True, False, 0)
        gate.decide(True, False, False, 0.1)
        self.assertIsNone(gate.decide(True, True, False, 1))
        self.assertEqual(gate.decide(True, True, False, 1.1), 'pickup')

    def test_cooldown_and_dialogue_priority(self):
        gate = AssistGate(cooldown=0.5)
        gate.decide(True, True, True, 0)
        self.assertEqual(gate.decide(True, True, True, 0.1), 'dialogue')
        self.assertIsNone(gate.decide(True, True, True, 0.2))
        self.assertEqual(gate.decide(True, True, True, 0.7), 'dialogue')

    def test_disabled_actions_do_not_consume_confirmation(self):
        gate = AssistGate(pickup_enabled=False, dialogue_enabled=True)
        for tick in range(5):
            self.assertIsNone(gate.decide(True, True, False, tick))

    def test_reset_clears_stale_frames(self):
        gate = AssistGate()
        gate.decide(True, True, False, 0)
        gate.reset()
        self.assertIsNone(gate.decide(True, True, False, 1))
