"""Exact original e64 m1; only proven frozen-M7 reset GPR knowledge changes."""
import csv
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
E8 = HERE.parent/'full_small2_reset_gpr_recovery01'
PROFILE_SHA = '4484d763f03b1ff245ae269f9eaa67cfced8f28210e411f512b38d5dcb67f0c2'
E8_CHECKER_SHA = '95f811703a8f13b75fc176cdc599ee30c7ead3007d54ed9ccf872c87b431478f'


def sha(path):
    import hashlib
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


if sha(E8/'checker.py') != E8_CHECKER_SHA:
    raise ValueError('Reviewed reset checker drift')
_s = importlib.util.spec_from_file_location('e64_reviewed_reset_proof', E8/'checker.py')
proof = importlib.util.module_from_spec(_s)
_s.loader.exec_module(proof)
legacy = proof.legacy
REF = HERE.parent/'full_e64_m1_optimized_compile01'
G = legacy.G
READY_SHA = 'fb00c9c6aee09d5de5fe7fab159151a6a278f8ac4cd113dbe5950389b8ea444f'
ELFS = ('19dfd4e46b871e53cce075263cc96a1ab77e28ea7b2ac20ecd0762830cf2b4ea',)
is_csr = legacy.is_csr
read, require, common = legacy.read, legacy.require, legacy.common
SHAPE = 'rvv_matrix_e64_m1'
SHAPES = (SHAPE,)
MASK64, VETO = legacy.MASK64, legacy.VETO
marker, console_gate = legacy.marker, legacy.console_gate
memory_op, loaded_value = legacy.memory_op, legacy.loaded_value


def specification(shape):
    require(shape in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Reference identity drift')
    proof = read(REF / shape / 'sourceproof.json')
    spec = proof['backends']['soc']
    require(spec['sha256'] == ELFS[SHAPES.index(shape)] and sha(spec['elf']) == spec['sha256'], 'Same SoC ELF required')
    require(proof['full_order_preserved'] and not proof['partitioned'] and
            spec['all_helper_instructions_equal_original'], 'Original continuous helper proof')
    code = {int(k): v for k, v in spec['code'].items()}
    symbols = spec['symbols']
    helpers = spec['helpers']
    helper_pcs = {r['pc'] for rows in helpers.values() for r in rows}
    csr = [pc for pc, insn in code.items() if is_csr(insn) and pc not in helper_pcs and
           (pc < symbols['trap_entry'] or symbols['main'] <= pc < symbols['replay_text'])]
    require([code[pc] for pc in csr[:5]] == [0x30401073, 0x30529073, 0x3002a073, 0x00305073, 0x00805073]
            and len(csr) == 6 and code[csr[5]] & ~0xf80 == 0xc2202073, 'Exact startup/main CSR image')
    exit_store, = [pc for pc, insn in code.items() if symbols['replay_exit'] <= pc < symbols['number'] and insn == 0x00a2b023]
    bss_store, = [pc for pc, insn in code.items() if symbols['_start'] <= pc < symbols['trap_entry'] and insn == 0x0002b023]
    require(code[exit_store + 4] == 0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,
            'Actual SoC CTRL exit/park, not Spike HTIF/log')
    return dict(config=proof['case'], backend=spec, csr_prelude=csr, exit_store=exit_store,
                park=exit_store + 4, bss_store=bss_store, ctrl=0xd0000000, uart=0xc0000000)



class Strict(legacy.Strict):
    def __init__(self, spec, gold, *, profile=None):
        original, _ = proof.validate_profile()
        require(sha(HERE/'reset_profile.json') == PROFILE_SHA, 'Exact M7 profile drift')
        bound = read(HERE/'reset_profile.json')
        require(profile is None or profile == bound, 'Mismatched M7 profile')
        require(bound['FpgaEn'] == 0 and bound['initial_gpr_values'] == original['initial_gpr_values']
                and bound['allowed_shape'] == SHAPE and bound['original_soc_elf_sha256'] == ELFS[0],
                'Proven reset/shape binding')
        require(bound['rtl_pins'] == {k.replace('candidate06','candidate07'):v
                    for k,v in original['rtl_pins'].items()}, 'Same reviewed reset RTL required')
        for path,digest in bound['rtl_pins'].items():
            require(sha(path) == digest, 'M7 reset RTL drift')
        image = Path(bound['image'])
        require(sha(image) == bound['image_sha256'], 'M7 image profile drift')
        ledger = read(image)
        require(ledger['snapshot_sha256'] == bound['snapshot_sha256'] and
                ledger['manifest_sha256'] == bound['compiled_manifest_sha256'] and
                ledger['configuration_sha256'] == bound['configuration_sha256'], 'M7 profile identities')
        require(spec == specification(SHAPE), 'Exact original e64 spec required')
        source_pins = read(REF/'READY.json')['evidence_pins']
        model = REF/SHAPE/'model.json'
        require(sha(model) == source_pins[str(model)] and gold == read(model), 'Full5985 original model required')
        elf = Path(spec['backend']['elf'])
        require(sha(elf) == bound['original_soc_elf_sha256'] == source_pins[str(elf)], 'Exact e64 ELF required')
        super().__init__(spec, gold)
        # Only adapt the compiler's outlined failure symbol name for legacy rejection.
        failures = [v for k,v in self.s.items() if k == 'failure' or k.startswith('failure.')]
        require(len(failures) == 1, 'Exact optimized failure entry')
        self.s = dict(self.s, failure=failures[0])
        self.regs = dict(enumerate(bound['initial_gpr_values']))
        self.reset_profile_sha256 = PROFILE_SHA


def audit(path, spec, abort=None):
    state = Strict(spec, read(REF/SHAPE/'model.json'))
    with Path(path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            if state.rows % 4096 == 0:
                require(abort is None or not abort.is_set(), 'Cancelled strict e64 trace')
            state.consume(row)
    return state.finish()


def artifacts(result, case, ledger, spec, abort):
    common.check_artifacts(result, dict(case, original_name=case['id']), ledger)
    console_gate((result.artifact_dir/'console.log').read_text(), spec['config'])
    require(not VETO.search((result.artifact_dir/'work/run.vcs.log').read_text()), 'Raw VCS failure')
    return audit(result.artifact_dir/'commit_trace.csv', spec, abort)
