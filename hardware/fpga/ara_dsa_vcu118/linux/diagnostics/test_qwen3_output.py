import unittest
from run_qwen3 import display_answer, extract_answer


class AnswerTests(unittest.TestCase):
    def test_interleaved_trace(self):
        raw = b'log\r\nQuestion: answerGGML_RISCV_AKV_EXEC native=1\r\n continued\r\nmain: decoded 2 tokens'
        self.assertEqual(extract_answer(raw, 'Question:'), 'answer continued')

    def test_multiline_chat(self):
        prompt = '<|im_start|>assistant\n<think>\n\n</think>'
        self.assertEqual(extract_answer((prompt + '\n\nHello.\nmain: decoded 2 tokens').encode(), prompt), 'Hello.')

    def test_incomplete(self):
        self.assertIsNone(extract_answer(b'Question: unfinished', 'Question:'))
        self.assertIsNone(extract_answer(b'log\nmain: decoded 2 tokens', 'Question:'))

    def test_final_answer_only(self):
        self.assertEqual(display_answer('reasoning\n</think>\n\nFinal answer.', '<think>\n'), 'Final answer.')
        self.assertEqual(display_answer('Final answer.', '<think>\n\n</think>\n\n'), 'Final answer.')

    def test_unfinished_reasoning(self):
        self.assertIsNone(display_answer('still reasoning', '<think>\n'))
        self.assertIsNone(display_answer('<think>still reasoning', 'Question:'))


if __name__ == '__main__':
    unittest.main()
