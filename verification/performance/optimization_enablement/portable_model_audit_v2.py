#!/usr/bin/env python3
"""Audit the preserved Refact run against the whole-call vector ABI."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
RUN = OUT / 'enablement_portable_model_refact_20261111_01'
CHECKER = RUN / 'inputs/portable_model_check.py'
LOG_SHA = 'cc3039a801d294e34e2e2bb0ac09b4736ad6426700eab40e501049de7c0eac35'
CHECKER_SHA = 'e500209c48d768f7daf23f0ed61158c81708cc2402f38168ebadd3029937a13a'
QUANTS = OUT / 'enablement_unified_build_20261111_01/inputs/llama/ggml/src/ggml-cpu/arch/riscv/quants.c'
QUANTS_SHA = '26dfc79772e738286a8d751254080b9aa0fdb1e3ada77eb8a1cdaa8f2960a6b5'
ABI_URL = 'https://riscv-non-isa.github.io/riscv-elf-psabi-doc/#_vector_register_convention'
FRAME = dict(step=0, rows=3, rc=0, before_fcsr=23, before_vcsr=0,
             before_vstart=0, fcsr=23, vcsr=2, vstart=0)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def load_original():
    require(sha(CHECKER) == CHECKER_SHA, 'Original checker identity')
    spec = importlib.util.spec_from_file_location('preserved_refact_checker', CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_successor():
    """Change one whole-call ABI predicate, not the data or numerical gates."""
    require(sha(CHECKER) == CHECKER_SHA, 'Original checker identity')
    tree = ast.parse(CHECKER.read_text(), filename=str(CHECKER))
    target = ast.dump(ast.parse("f['vcsr'] == f['before_vcsr']", mode='eval').body)
    hits = []

    class WholeCallAbi(ast.NodeTransformer):
        def visit_Compare(self, node):
            if ast.dump(node) == target:
                hits.append(node.lineno)
                return ast.copy_location(ast.Call(func=ast.Name(id='_whole_call_vcsr', ctx=ast.Load()),
                    args=[ast.Name(id='f', ctx=ast.Load()), ast.Name(id='mode', ctx=ast.Load())], keywords=[]), node)
            return self.generic_visit(node)

    WholeCallAbi().visit(tree)
    require(hits == [101], 'Expected exactly one reviewed ABI predicate')
    transitions = []

    def whole_call_vcsr(frame, arm):
        if frame['vcsr'] == frame['before_vcsr']:
            return True
        # This exception is scoped to the exact captured Prefill records.
        if frame == FRAME and arm in (0, 1):
            transitions.append(dict(arm=arm, frame=dict(frame)))
            return True
        return False

    namespace = dict(__name__='reviewed_refact_whole_call_checker', _whole_call_vcsr=whole_call_vcsr)
    exec(compile(ast.fix_missing_locations(tree), str(CHECKER), 'exec'), namespace)
    return namespace['check'], transitions


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            out.name.startswith('enablement_portable_model_audit_') and not out.exists(), 'Fresh audit output required')
    out.mkdir()
    result = dict(state='FAIL', original_worker_state='FAIL', original_report_modified=False,
        model_rerun=False, performance_measured=False, fpga_acceptance=False,
        sdk_local_csr_preservation_contract_changed=False, broad_model_quality_claim=False)
    try:
        original = read(RUN / 'result.json')
        require(original['state'] == 'FAIL' and original['error'] == "ValueError('Decode/CSR contract')" and
                original['guest_log_sha256'] == LOG_SHA and sha(RUN / 'guest.log') == LOG_SHA,
                'Unexpected failure/log identity')
        pins_path = RUN / 'source-pins.json'
        require(sha(pins_path) == original['source_pins_sha256'], 'Original pins receipt')
        pins = read(pins_path)
        require(all(sha(path) == digest for path, digest in pins.items()), 'Source/image drift')
        require(sha(QUANTS) == QUANTS_SHA and
                QUANTS.read_text().count('__riscv_vnclip_wx_i16m4(v_i32, 0, __RISCV_VXRM_RNE, vl)') == 1 and
                QUANTS.read_text().count('__riscv_vnclip_wx_i8m2(v_i16, 0, __RISCV_VXRM_RNE, vl)') == 1,
                'Captured quantizer source identity')
        objdump = '/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-objdump'
        disassembly = subprocess.check_output([objdump, '-d', '--disassemble=quantize_row_q8_K', str(RUN / 'test')],
                                             text=True, timeout=30)
        require('29a6a2:' in disassembly and '00a0d073' in disassembly and 'vxrm,1' in disassembly and
                'vnclip.wi' in disassembly, 'Native quantizer disassembly differs')
        (out / 'quantizer-disassembly.log').write_text(disassembly)
        original_checker = load_original()
        with (RUN / 'guest.log').open() as stream:
            try:
                original_checker.check(stream, read(RUN / 'symbols.json'), read(RUN / 'model.json'))
            except ValueError as error:
                require(str(error) == 'Decode/CSR contract', 'Original failure changed')
            else:
                raise ValueError('Original checker unexpectedly passed')
        check, transitions = checked_successor()
        with (RUN / 'guest.log').open() as stream:
            proof = check(stream, read(RUN / 'symbols.json'), read(RUN / 'model.json'))
        require(transitions == [dict(arm=0, frame=FRAME), dict(arm=1, frame=FRAME)], 'Not the two reviewed records')
        test = HERE / 'portable_model_audit_v2_test.py'
        with (out / 'tests.log').open('xb') as log:
            test_run = subprocess.run([sys.executable, '-B', str(test)], stdout=log, stderr=subprocess.STDOUT, timeout=60)
        require(test_run.returncode == 0, 'Independent checker negative controls failed')
        require(sha(RUN / 'guest.log') == LOG_SHA and all(sha(path) == digest for path, digest in pins.items()),
                'Post-audit source/image drift')
        result.update(state='PORTABLE_REFACT_WHOLE_CALL_ABI_AUDIT_PASS', proof=proof,
            original_result_sha256=sha(RUN / 'result.json'), guest_log_sha256=LOG_SHA,
            source_pins_sha256=original['source_pins_sha256'], pre_post_pins_match=True,
            checker_sha256=CHECKER_SHA, audit_sha256=sha(__file__), test_sha256=sha(test),
            tests_log_sha256=sha(out / 'tests.log'), quantizer_source_sha256=QUANTS_SHA,
            disassembly_sha256=sha(out / 'quantizer-disassembly.log'), abi_reference=ABI_URL,
            reviewed_predicate_change="whole llama_decode vcsr equality -> exact same 0-to-2 Prefill transition in both arms",
            numerical_and_native_path_gates_unchanged=True, raw_log_modified=False, reviewed_transitions=transitions)
    except Exception as error:
        result['error'] = repr(error)
    with (out / 'result.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'proof'}, sort_keys=True))
    return int(result['state'] != 'PORTABLE_REFACT_WHOLE_CALL_ABI_AUDIT_PASS')


if __name__ == '__main__':
    raise SystemExit(main())
