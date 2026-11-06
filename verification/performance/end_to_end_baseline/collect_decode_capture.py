#!/usr/bin/env python3
"""Re-audit genuine Decode operands, original GGUF bytes and native QEMU identity."""
import argparse
import json
from pathlib import Path
import sys

from audit import digest, require, verify_pins
from decode_capture import check
from run_projection_capture_v3 import ROOT, HERE, MODEL_RUN, GRAPH, MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); run = args.run.resolve(strict=True); out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False); result = dict(state='CHECKING',performance_measured=False)
    try:
        audit_pins = {str(p):digest(p) for p in (Path(__file__),HERE/'audit.py',HERE/'decode_capture.py',run/'result.json')}
        report = json.loads((run/'result.json').read_text())
        require(report['state'] == 'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED' and report['post_pins_match'] and
                digest(run/'source-pins.json') == report['source_pins_sha256'],'Unaccepted Decode capture')
        pins = json.loads((run/'source-pins.json').read_text()); checked = verify_pins(pins); verify_pins(report['artifacts'])
        control = json.loads((ROOT/'verification/performance/evidence/qwen3_projection_capture_20261106_01/result.json').read_text())
        original = Path(control['run'])
        require(pins.get(str(original/'qemu.log')) == digest(original/'qemu.log'),'Control input drift')
        payloads, metadata = check((run/'qemu.log').read_text(),(original/'qemu.log').read_text())
        require(metadata == report['activation'] and all((run/(name+'_f32.bin')).read_bytes() == payload
                for name,payload in payloads.items()),'Raw Decode payload replay differs')
        sys.path.insert(0,str(GRAPH/'llama/gguf-py'))
        from gguf import GGUFReader
        reader = GGUFReader(str(MODEL)); require(len(report['weights']) == 7,'Weight inventory')
        for row in report['weights']:
            tensors = [t for t in reader.tensors if t.name == row['tensor']]
            require(len(tensors) == 1,'Original tensor identity'); tensor = tensors[0]
            require(list(map(int,tensor.shape)) == [row['k'],row['full_n']] and tensor.tensor_type.name == row['type'] and
                    row['captured_n'] == 128 and row['type'] in ('Q4_K','Q6_K'),'Original tensor geometry')
            size = 128*(row['k']//256)*(144 if row['type'] == 'Q4_K' else 210)
            path = run/row['file']
            require(path.parent == run and path.read_bytes() == tensor.data.view('uint8').reshape(-1)[:size].tobytes() and
                    digest(path) == row['sha256'],'Original weight prefix differs')
        commands = [r['argv'] for r in json.loads((run/'commands.json').read_text()) if r['label'] == 'qemu']
        require(len(commands) == 1 and 'xaraqbs=true' in commands[0][commands[0].index('-cpu')+1] and
                commands[0][commands[0].index('-initrd')+1] == str(run/'initramfs.cpio'),'Actual native guest configuration')
        accepted = json.loads((ROOT/'verification/performance/evidence/output_model_20261106_01/result.json').read_text())
        require(digest(MODEL_RUN/'source-pins.json') == accepted['source_pins_sha256'],'Accepted native provenance map')
        old = json.loads((MODEL_RUN/'source-pins.json').read_text())
        sys.path.insert(0,str(ROOT/'verification/qbs'))
        from run_ggml_segmented import verify_native_build
        for path in verify_native_build(Path(commands[0][0])):
            path = Path(path).resolve(strict=True)
            require(old.get(str(path)) == digest(path),'Native QEMU provenance drift: '+str(path))
        verify_pins(pins); verify_pins(report['artifacts']); verify_pins(audit_pins)
        result.update(state='REAL_QWEN3_DECODE_CAPTURE_REAUDITED',run=str(run),checked_inputs=checked,
                      activation=metadata,native_emulator_postchecked=True,weights_reextracted=True,
                      worker_result_sha256=digest(run/'result.json'),source_pins_sha256=digest(run/'source-pins.json'),
                      payload_sha256={name:digest(run/(name+'_f32.bin')) for name in payloads},
                      log_sha256=digest(run/'qemu.log'),audit_pins=audit_pins,
                      limitations=['Operand capture and actual routes, not RTL timing',
                                   'Prefill complete; Decode stops before vocabulary output',
                                   'Observer can split graph scheduling; context counts are capture-scope only'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':main()
