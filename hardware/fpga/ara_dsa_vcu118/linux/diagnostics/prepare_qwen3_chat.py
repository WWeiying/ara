"""Render the model's own GGUF chat template and test it with native llama-simple."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--llama-root', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--thinking', action='store_true')
    p.add_argument('--tokens', type=int, default=192)
    p.add_argument('--chat-only', action='store_true')
    p.add_argument('--system', default='Answer the user directly using the supplied facts. Calculate carefully. Give a concise, complete answer, not a template or placeholders.')
    p.add_argument('--completion', action='store_true', help='Use llama-completion sampling instead of greedy llama-simple')
    p.add_argument('--seed', type=int, default=42)
    a = p.parse_args()
    if not 1 <= a.tokens <= 2048:
        p.error('--tokens must be between 1 and 2048')
    sys.path.insert(0, str(a.llama_root / 'gguf-py'))
    from gguf import GGUFReader
    from jinja2.sandbox import ImmutableSandboxedEnvironment
    a.out.mkdir(parents=True, exist_ok=False)
    template = GGUFReader(a.model).fields['tokenizer.chat_template'].contents()
    user = a.input.read_text(encoding='utf-8').rstrip()
    messages = [
        {'role': 'system', 'content': a.system},
        {'role': 'user', 'content': user},
    ]
    rendered = ImmutableSandboxedEnvironment().from_string(template).render(
        messages=messages, add_generation_prompt=True, enable_thinking=a.thinking)
    (a.out / 'prompt.txt').write_text(rendered, encoding='utf-8')
    (a.out / 'template.jinja').write_text(template, encoding='utf-8')
    (a.out / 'messages.json').write_text(json.dumps(messages, indent=2), encoding='utf-8')
    report = {'enable_thinking': a.thinking, 'requested_tokens': a.tokens,
              'model': str(a.model), 'binary': str(a.binary), 'answer_quality': 'not_evaluated',
              'template_sha256': hashlib.sha256(template.encode()).hexdigest()}
    cases = [('chat', rendered)] if a.chat_only else [('raw', user), ('chat', rendered)]
    for name, prompt in cases:
        command = [str(a.binary), '-m', str(a.model), '-ngl', '0', '-t', '4', '-n', str(a.tokens)]
        if a.completion:
            command += ['-no-cnv', '--no-display-prompt', '-c', '4096',
                        '--seed', str(a.seed), '--temp', '0.6' if a.thinking else '0.7',
                        '--top-p', '0.95' if a.thinking else '0.8', '--top-k', '20',
                        '--min-p', '0', '-p', prompt]
        else:
            command += [prompt]
        report[name + '_command'] = command
        with (a.out / (name + '.stdout')).open('wb') as stdout, (a.out / (name + '.stderr')).open('wb') as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=600)
        report[name + '_exit_code'] = result.returncode
        print(name, result.returncode, flush=True)
    (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
