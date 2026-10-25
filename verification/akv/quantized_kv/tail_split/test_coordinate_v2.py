import selectors
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from verification.akv.quantized_kv.tail_split import coordinate_v2 as successor


class SuccessorWaitTests(unittest.TestCase):
    def test_manual_stop_is_not_selector_interrupted_error(self):
        with self.assertRaises(successor.StopRequested):
            successor.interrupted(signal.SIGTERM, None)
        self.assertFalse(issubclass(successor.StopRequested, InterruptedError))

    def test_empty_event_before_deadline_is_not_timeout(self):
        selector = Mock()
        selector.__enter__ = Mock(return_value=selector)
        selector.__exit__ = Mock(return_value=False)
        selector.get_map.side_effect = [{8: 'waiting'}, {8: 'waiting'}, {}]
        key = SimpleNamespace(fd=8, data={'worker_pid': 123})
        selector.select.side_effect = [[], [(key, selectors.EVENT_READ)]]
        done = Mock()
        with patch.object(successor.selectors, 'DefaultSelector', return_value=selector), \
             patch.object(successor.time, 'monotonic', side_effect=[0, 1, 2]), \
             patch.object(successor.original, 'terminal_pass') as terminal:
            successor.wait_all([(8, key.data)], 30, done)
        terminal.assert_called_once_with(key.data)
        done.assert_called_once_with(key.data)
        selector.unregister.assert_called_once_with(8)

    def test_real_deadline_remains_bounded(self):
        selector = Mock()
        selector.__enter__ = Mock(return_value=selector)
        selector.__exit__ = Mock(return_value=False)
        selector.get_map.return_value = {8: 'waiting'}
        selector.select.return_value = []
        with patch.object(successor.selectors, 'DefaultSelector', return_value=selector), \
             patch.object(successor.time, 'monotonic', side_effect=[0, 1, 31]), \
             patch.object(successor.original, 'terminal_pass') as terminal:
            with self.assertRaises(TimeoutError):
                successor.wait_all([(8, {})], 30, Mock())
        terminal.assert_not_called()


if __name__ == '__main__':
    unittest.main()
