"""Exact original e16 mf4; only proven frozen-M6 reset GPR knowledge changes."""
import csv
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
E8 = HERE.parent/'full_small2_reset_gpr_recovery01'
PROFILE_SHA = 'd9b51ce0d44c08fe96c72d921dbffb778346fa996dbd194fbfb08257502823c3'
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
_s = importlib.util.spec_from_file_location('e16_reviewed_reset_proof', E8/'checker.py')
proof = importlib.util.module_from_spec(_s)
_s.loader.exec_module(proof)
legacy = proof.legacy
REF = HERE.parent/'full_e16_mf4_prepare01'
G = legacy.G
READY_SHA = 'beac34d373d7dadaa1dda388417ec87905273b5541a654b793d42f16c493fd0a'
ELFS = ('509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6',)
is_csr = legacy.is_csr
read, require, common = legacy.read, legacy.require, legacy.common
SHAPE = 'rvv_matrix_e16_mf4'
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
    exit_store, = [pc for pc, insn in code.items() if symbols['replay_exit'] <= pc < symbols['selected'] and insn == 0x00a2b023]
    bss_store, = [pc for pc, insn in code.items() if symbols['_start'] <= pc < symbols['trap_entry'] and insn == 0x0002b023]
    require(code[exit_store + 4] == 0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,
            'Actual SoC CTRL exit/park, not Spike HTIF/log')
    return dict(config=proof['case'], backend=spec, csr_prelude=csr, exit_store=exit_store,
                park=exit_store + 4, bss_store=bss_store, ctrl=0xd0000000, uart=0xc0000000)



class Strict(legacy.Strict):
    def __init__(self, spec, gold, *, profile=None):
        original, plan = proof.validate_profile()
        require(sha(HERE/'reset_profile.json') == PROFILE_SHA, 'E16 profile drift')
        expected = dict(original, allowed_shape=SHAPE, source_profile_sha256=proof.PROFILE_SHA,
                        original_soc_elf_sha256=ELFS[0],
                        original_linux_elf_sha256='e538572bcf13bd7338647f5a7e5b7bfc8627f1ee04598d8fb0283a76926b998c',
                        reference_bound_sha256='7d1aff0edd00c583e6214b78b44eb3b1d8ba5a910a7f2de6056c9566255f6938')
        bound = read(HERE/'reset_profile.json')
        require(bound == expected and (profile is None or profile == expected), 'Mismatched e16 reset profile')
        require(spec == specification(SHAPE), 'Exact original e16 spec required')
        source_pins = read(REF/'READY.json')['evidence_pins']
        model = REF/SHAPE/'model.json'
        require(sha(model) == source_pins[str(model)] and gold == read(model), 'Full4095 original model required')
        elf = Path(spec['backend']['elf'])
        require(sha(elf) == bound['original_soc_elf_sha256'] == source_pins[str(elf)], 'Exact e16 ELF required')
        super().__init__(spec, gold)
        self.regs = dict(enumerate(bound['initial_gpr_values']))
        self.reset_profile_sha256 = PROFILE_SHA


def audit(path, spec, abort=None):
    state = Strict(spec, read(REF/SHAPE/'model.json'))
    with Path(path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            if state.rows % 4096 == 0:
                require(abort is None or not abort.is_set(), 'Cancelled strict e16 trace')
            state.consume(row)
    return state.finish()


def artifacts(result, case, ledger, spec, abort):
    common.check_artifacts(result, dict(case, original_name=case['id']), ledger)
    console_gate((result.artifact_dir/'console.log').read_text(), spec['config'])
    require(not VETO.search((result.artifact_dir/'work/run.vcs.log').read_text()), 'Raw VCS failure')
    return audit(result.artifact_dir/'commit_trace.csv', spec, abort)
