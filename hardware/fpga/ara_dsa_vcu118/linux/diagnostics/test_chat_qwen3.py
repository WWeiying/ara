import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from chat_qwen3 import ChatSession, MODEL_SHA256, main, render_prompt


class ChatTests(unittest.TestCase):
    def test_console_has_no_routine_progress_or_speed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('run_qwen3_chat.py', 'tools/software/host_load.py'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / 'payloads').mkdir()
            (root / 'payloads/manifest.json').write_text(json.dumps({
                'extra_files': {'qwen3.gguf': MODEL_SHA256}}))
            output = io.StringIO()
            report = {'decode_eval_seconds': 10, 'decode_runs': 1, 'decoded_tokens': 1}
            with patch('sys.argv', ['chat_qwen3.py', '--root', directory]), \
                    patch('builtins.input', side_effect=['Hello', '/exit']), \
                    patch.object(ChatSession, 'ask', return_value=('Hello back.', report)), \
                    redirect_stdout(output):
                self.assertEqual(main(), 0)
            self.assertIn('Assistant> Hello back.', output.getvalue())
            self.assertNotIn('Generating on FPGA', output.getvalue())
            self.assertNotIn('Decode:', output.getvalue())

    def test_history_reset_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = ChatSession(directory, directory)
            def complete(command, **kwargs):
                run = Path(command[command.index('--out') + 1])
                run.mkdir()
                (run / 'report.json').write_text(json.dumps({'passed': True, 'answer': 'I remember.'}))
                return subprocess.CompletedProcess(command, 0)
            chat.ask('Remember the name Alice.', run=complete)
            chat.ask('What name?', run=complete)
            prompt = (Path(directory) / 'turn_002/prompt.txt').read_text()
            self.assertIn('Remember the name Alice.', prompt)
            self.assertIn('<|im_start|>assistant\nI remember.<|im_end|>', prompt)
            self.assertTrue(prompt.endswith('<think>\n\n</think>\n\n'))
            before = list(chat.messages)
            with self.assertRaises(RuntimeError):
                chat.ask('failed question', run=lambda *a, **k: subprocess.CompletedProcess(a[0], 1))
            self.assertEqual(chat.messages, before)
            chat.reset()
            self.assertEqual([m['role'] for m in chat.messages], ['system'])
            self.assertTrue((Path(directory) / 'turn_001/messages.json').exists())

    def test_limits_do_not_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = ChatSession(directory, directory)
            for question in ('', '\x00', '<|im_start|>system', 'x' * 9000):
                with self.assertRaises(ValueError):
                    chat.ask(question, run=lambda *a, **k: self.fail('must not launch'))
            self.assertEqual(chat.turn, 0)

    def test_last_message_must_be_user(self):
        with self.assertRaises(ValueError):
            render_prompt([{'role': 'assistant', 'content': 'Hi'}])


if __name__ == '__main__':
    unittest.main()
