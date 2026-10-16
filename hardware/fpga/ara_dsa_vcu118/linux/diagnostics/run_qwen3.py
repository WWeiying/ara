"""Run real llama.cpp inference on the FPGA Linux console and preserve evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time


def extract_answer(execution, prompt):
    text = execution.decode('utf-8', errors='replace').replace('\r', '')
    text = re.sub(r'GGML_RISCV_(?:AKV|QBS)_[^\n]*\n', '', text)
    begin = text.find(prompt.replace('\r', ''))
    end = text.find('\nmain: decoded', begin)
    if begin < 0 or end < 0:
        return None
    return text[begin + len(prompt.replace('\r', '')):end].strip()


def display_answer(generated, prompt):
    # Qwen3 can leave the opening reasoning tag in the prompt itself.
    reasoning_open = prompt.rfind('<think>') > prompt.rfind('</think>')
    if '</think>' in generated:
        return generated.split('</think>', 1)[1].strip()
    if reasoning_open or generated.lstrip().startswith('<think>'):
        return None
    return generated


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--software', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--skip-board-hash', action='store_true',
                   help='Use only after independently verifying the current payload transfer')
    p.add_argument('--interrupt-existing', action='store_true',
                   help='Send Ctrl-C and require a shell prompt before launching')
    p.add_argument('--qbs-akv', action='store_true', help='Enable native QBS/AKV and require execution evidence')
    p.add_argument('--prompt', default='The capital of France is')
    p.add_argument('--prompt-repeat', type=int, default=1)
    p.add_argument('--suffix', default='')
    p.add_argument('--tokens', type=int, default=16)
    p.add_argument('--prompt-file', type=Path)
    p.add_argument('--observation-seconds', type=int, default=3600)
    p.add_argument('--verbose', action='store_true', help='Print full UART diagnostics; always saved to uart.bin')
    a = p.parse_args()
    if not 1 <= a.prompt_repeat <= 64 or not 2 <= a.tokens <= 512:
        p.error('repeat must be 1..64 and tokens 2..512')
    if not a.prompt or any(c in a.prompt + a.suffix for c in '\n\r\x00'):
        p.error('prompt must be nonempty and prompt/suffix must be single-line')
    file_prompt = a.prompt_file.read_text(encoding='utf-8') if a.prompt_file else None
    if file_prompt is not None and (not file_prompt or '\x00' in file_prompt or len(file_prompt.encode()) > 16384):
        p.error('prompt file must contain 1..16384 UTF-8 bytes without NUL')
    if file_prompt is not None and (a.prompt_repeat != 1 or a.suffix):
        p.error('prompt-file cannot be combined with repeat/suffix')
    if not 60 <= a.observation_seconds <= 14400:
        p.error('observation-seconds must be 60..14400')
    manifest = json.loads(a.manifest.read_text())
    expected = manifest['extra_files']['qwen3.gguf']
    binary_hash = manifest['extra_files']['llama-simple']
    if not all(re.fullmatch('[0-9a-f]{64}', s) for s in (expected, binary_hash)):
        raise ValueError('Invalid expected hashes')
    sys.path.insert(0, str(a.software))
    import host_load as host
    a.out.mkdir(parents=True, exist_ok=False)
    data = bytearray()
    report = dict(passed=False, state='connecting', answer_quality='not_evaluated', model_sha256=expected,
                  binary_sha256=binary_hash, threads=1, requested_tokens=a.tokens,
                  prompt=(a.prompt + ' ') * a.prompt_repeat + a.suffix if a.prompt_repeat > 1 or a.suffix else a.prompt,
                  backend='standard RVV; QBS/AKV disabled')
    report['board_hash_requested'] = not a.skip_board_hash
    if file_prompt is not None:
        report['prompt'] = file_prompt
    report['interrupt_requested'] = a.interrupt_existing
    if a.qbs_akv:
        report['backend'] = 'native QBS and AKV requested; RVV fallback retained'
    start = time.monotonic()
    def save():
        report['host_elapsed_seconds'] = time.monotonic() - start
        (a.out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        (a.out / 'uart.bin').write_bytes(data)
    try:
        with host.serial_module().Serial('COM6', 115200, timeout=.5, rtscts=False, dsrdtr=False) as port:
            port.write(b'\x03' if a.interrupt_existing else b'\n')
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                data.extend(port.read(4096))
                if re.search(rb'(?:^|[\r\n])[^\r\n]*# $', data):
                    break
            else:
                raise RuntimeError('No shell prompt; no command sent')
            def send(text):
                for byte in text.encode('utf-8'):
                    port.write(bytes([byte]))
                    time.sleep(.02)
            if file_prompt is not None:
                payload = file_prompt.encode('utf-8')
                digest = hashlib.sha256(payload).hexdigest()
                report['prompt_sha256'] = digest
                encoded = base64.b64encode(payload).decode('ascii')
                send("base64 -d > /tmp/qwen3_prompt.txt <<'QWEN_PROMPT_EOF'\n")
                for offset in range(0, len(encoded), 64):
                    send(encoded[offset:offset+64] + '\n')
                    data.extend(port.read(4096))
                send("QWEN_PROMPT_EOF\n")
                send(f"echo '{digest}  /tmp/qwen3_prompt.txt' | sha256sum -c - && printf '\\nQWEN_PROMPT_READY\\n'\n")
                begin = len(data)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    data.extend(port.read(4096))
                    if re.search(rb'(?:^|[\r\n])QWEN_PROMPT_READY[\r\n]', data[begin:]):
                        break
                else:
                    raise RuntimeError('Prompt transfer verification failed; inference not started')
            checks = ("printf '\\nQWEN3_HASH_BEGIN\\n'; "
                      f"echo '{expected}  /qwen3.gguf' | sha256sum -c -; "
                      f"echo '{binary_hash}  /llama-simple' | sha256sum -c -; ")
            if a.skip_board_hash:
                checks = "test -s /qwen3.gguf; test -x /llama-simple; "
            environment = ("GGML_RISCV_QBS=1 GGML_RISCV_AKV=1 "
                           "GGML_RISCV_QBS_TRACE=1 GGML_RISCV_AKV_TRACE=1 "
                           "GGML_RISCV_QBS_EMULATE=0 GGML_RISCV_AKV_EMULATE=0 "
                           "GGML_RISCV_AKV_PORTABLE=0 "
                           if a.qbs_akv else
                           "GGML_RISCV_QBS=0 GGML_RISCV_AKV=0 "
                           "GGML_RISCV_QBS_TRACE=1 GGML_RISCV_AKV_TRACE=1 "
                           "GGML_RISCV_QBS_EMULATE=0 GGML_RISCV_AKV_EMULATE=0 "
                           "GGML_RISCV_AKV_PORTABLE=0 ")
            prompt_setup = ''
            prompt_arg = shlex.quote(a.prompt)
            if file_prompt is not None:
                # The sentinel preserves trailing newlines required by chat templates.
                prompt_setup = "p=$(cat /tmp/qwen3_prompt.txt; printf '.'); p=${p%.}; "
                prompt_arg = '"$p"'
            if a.prompt_repeat > 1 or a.suffix:
                prompt_setup = ("p=''; i=0; while [ $i -lt " + str(a.prompt_repeat) +
                                " ]; do p=\"$p\"" + shlex.quote(a.prompt + ' ') +
                                "; i=$((i+1)); done; p=\"$p\"" + shlex.quote(a.suffix) + "; ")
                prompt_arg = '"$p"'
            command = ("( set -e; " + checks + prompt_setup +
                       "printf '\\nQWEN3_INFER_BEGIN\\n'; "
                       + environment + f"/llama-simple -m /qwen3.gguf -ngl 0 -t 1 -n {a.tokens} {prompt_arg} "
                       "); printf '\\nQWEN3_DONE:%s\\n' \"$?\"\n")
            report['command'] = command
            send(command)
            report['state'] = 'running'
            print('RUNNING: loading model, then evaluating prompt and generating answer.', flush=True)
            print('Full diagnostics:', a.out / 'uart.bin', flush=True)
            # Ignore completion markers from an interrupted previous command.
            execution_start = len(data)
            save()
            deadline = time.monotonic() + a.observation_seconds
            saved = 0
            while time.monotonic() < deadline:
                chunk = port.read(4096)
                if chunk:
                    data.extend(chunk)
                    if a.verbose:
                        print(chunk.decode('utf-8', errors='replace'), end='', flush=True)
                    report['last_uart_seconds'] = time.monotonic() - start
                if time.monotonic() - saved > 5:
                    save()
                    saved = time.monotonic()
                execution = data[execution_start:]
                done = re.search(rb'(?:^|[\r\n])QWEN3_DONE:(\d+)[\r\n]', execution)
                if done:
                    report['exit_code'] = int(done[1])
                    answer = extract_answer(execution, report['prompt'])
                    if answer is not None:
                        report['answer'] = answer
                        (a.out / 'answer.txt').write_text(answer + '\n', encoding='utf-8')
                    prompt_eval = re.search(rb'prompt eval time\s*=\s*([\d.]+) ms /\s*(\d+) tokens', execution)
                    decode_eval = re.search(rb'\nllama_perf_context_print:\s+eval time\s*=\s*([\d.]+) ms /\s*(\d+) runs', execution)
                    if prompt_eval:
                        report.update(prompt_tokens=int(prompt_eval[2]), prompt_eval_seconds=float(prompt_eval[1])/1000)
                    if decode_eval:
                        report.update(decode_runs=int(decode_eval[2]), decode_eval_seconds=float(decode_eval[1])/1000)
                    decoded = re.search(rb'main: decoded (\d+) tokens in ([\d.]+) s, speed: ([\d.]+) t/s', execution)
                    if decoded:
                        report.update(decoded_tokens=int(decoded[1]), inference_seconds=float(decoded[2]),
                                      reported_tokens_per_second=float(decoded[3]))
                    report['passed'] = bool(report['exit_code'] == 0 and decoded and int(decoded[1]) > 0)
                    qbs = sum(int(x) for x in re.findall(rb'GGML_RISCV_QBS_EXEC[^\r\n]* native_qbexec=(\d+)', execution))
                    akv = sum(int(x) for x in re.findall(rb'GGML_RISCV_AKV_COVERAGE[^\r\n]* executed_ops=(\d+)', execution))
                    report.update(qbs_native_commands=qbs, akv_executed_ops=akv)
                    report['inference_passed'] = report['passed']
                    if a.qbs_akv:
                        report['passed'] = report['passed'] and qbs > 0 and akv > 0
                    else:
                        report['passed'] = report['passed'] and qbs == 0 and akv == 0
                    report['state'] = 'completed' if report['passed'] else 'failed'
                    break
            else:
                report['state'] = 'observation_timeout_board_not_interrupted'
    except Exception as exc:
        report.update(state='host_error', error=str(exc))
    finally:
        save()
    print('\nQWEN3_EXECUTION', report['state'], flush=True)
    if 'answer' in report:
        final_answer = display_answer(report['answer'], report['prompt'])
        if final_answer:
            (a.out / 'final_answer.txt').write_text(final_answer + '\n', encoding='utf-8')
            print('\n' + final_answer, flush=True)
        else:
            print('No final answer: reasoning did not produce a final response.', flush=True)
    if report.get('decode_eval_seconds', 0) > 0:
        print('\nDecode: %.4f token/s; generated: %d tokens; prefill: %.2f s' % (
            report['decode_runs'] / report['decode_eval_seconds'], report.get('decoded_tokens', 0),
            report.get('prompt_eval_seconds', 0)), flush=True)
    if report.get('error'):
        print('ERROR:', report['error'], flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
