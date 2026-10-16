"""Continuous Windows console chat using the existing single-turn FPGA runner.

History is carried in each prompt; model and KV cache are NOT resident across turns.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from run_qwen3_chat import display_answer
except ModuleNotFoundError:
    from run_qwen3 import display_answer


MODEL_SHA256 = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
SYSTEM = 'Answer the user directly and concisely. Use the conversation history when relevant. If unsure, say so.'


def render_prompt(messages):
    # Exact no-tools, non-thinking branch of the deployed Qwen3 GGUF template.
    if not messages or messages[-1]['role'] != 'user':
        raise ValueError('A turn must end with a user message')
    text = ''.join('<|im_start|>' + m['role'] + '\n' + m['content'] + '<|im_end|>\n'
                   for m in messages)
    return text + '<|im_start|>assistant\n<think>\n\n</think>\n\n'


class ChatSession:
    def __init__(self, root, output, tokens=128):
        self.root, self.output, self.tokens = Path(root), Path(output), tokens
        self.messages = [{'role': 'system', 'content': SYSTEM}]
        self.turn = 0
        self.events = []

    def save(self):
        (self.output / 'conversation.json').write_text(json.dumps({
            'resident_model': False, 'answer_quality': 'not_evaluated',
            'messages': self.messages, 'events': self.events,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def reset(self):
        self.messages = [{'role': 'system', 'content': SYSTEM}]
        self.events.append({'event': 'reset', 'after_turn': self.turn})
        self.save()

    def ask(self, question, run=subprocess.run):
        if not question.strip() or '\x00' in question or '<|im_' in question:
            raise ValueError('Empty question or reserved chat marker')
        candidate = self.messages + [{'role': 'user', 'content': question}]
        prompt = render_prompt(candidate)
        if len(prompt.encode('utf-8')) > 8192:
            raise ValueError('Conversation too long. Use /reset or shorten the question; no history was dropped.')
        self.turn += 1
        turn = self.output / ('turn_%03d' % self.turn)
        turn.mkdir()
        prompt_file = turn / 'prompt.txt'
        prompt_file.write_text(prompt, encoding='utf-8')
        (turn / 'messages.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
        command = [sys.executable, '-X', 'utf8', str(self.root / 'run_qwen3_chat.py'),
                   '--software', str(self.root / 'tools' / 'software'),
                   '--manifest', str(self.root / 'payloads' / 'manifest.json'),
                   '--out', str(turn / 'run'), '--prompt-file', str(prompt_file),
                   '--qbs-akv', '--skip-board-hash', '--tokens', str(self.tokens),
                   '--observation-seconds', '14400']
        with (turn / 'console.log').open('w', encoding='utf-8') as log:
            result = run(command, stdout=log, stderr=subprocess.STDOUT)
        report_path = turn / 'run' / 'report.json'
        if result.returncode or not report_path.exists():
            raise RuntimeError('Inference failed; chat stopped without retry. Inspect ' + str(turn))
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if not report.get('passed'):
            raise RuntimeError('Inference incomplete; chat stopped. Inspect ' + str(report_path))
        answer = display_answer(report.get('answer', ''), prompt)
        if not answer or '<|im_' in answer:
            raise RuntimeError('No usable final answer. Inspect ' + str(turn))
        self.messages = candidate + [{'role': 'assistant', 'content': answer}]
        self.events.append({'event': 'completed', 'turn': self.turn, 'path': str(turn)})
        self.save()
        return answer, report


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--tokens', type=int, default=128)
    a = p.parse_args()
    if not 2 <= a.tokens <= 512:
        p.error('--tokens must be 2..512')
    for relative in ('run_qwen3_chat.py', 'tools/software/host_load.py', 'payloads/manifest.json'):
        if not (a.root / relative).is_file():
            p.error('Missing ' + str(a.root / relative))
    manifest = json.loads((a.root / 'payloads/manifest.json').read_text(encoding='utf-8'))
    if manifest.get('extra_files', {}).get('qwen3.gguf') != MODEL_SHA256:
        p.error('This chat template is only verified for the deployed Qwen3 model')
    output = Path(tempfile.mkdtemp(prefix='chat_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_', dir=a.root))
    chat = ChatSession(a.root, output, a.tokens)
    chat.save()
    print('Ara FPGA Chat | /reset: new conversation | /exit: quit')
    print('History retained. Model reloads each turn; answers can take many minutes.')
    print('Close other COM6 clients. Use only with the existing verified board image/model.')
    print('Logs:', output)
    try:
        while True:
            question = input('\nYou> ').strip()
            if question == '/exit':
                return 0
            if question == '/reset':
                chat.reset()
                print('Conversation cleared.')
                continue
            if not question:
                continue
            try:
                answer, report = chat.ask(question)
            except ValueError as exc:
                print(exc)
                continue
            print('\nAssistant> ' + answer)
            if report.get('decoded_tokens', 0) >= a.tokens:
                print('Token limit reached; answer may be incomplete.')
    except EOFError:
        return 0
    except KeyboardInterrupt:
        print('\nWindow interrupted. FPGA inference may still be running; do not start a second client.')
        return 1
    except Exception as exc:
        print('\nERROR:', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
