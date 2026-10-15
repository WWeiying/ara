"""Exact original e32 mf2; only proven frozen-M6 reset GPR knowledge changes."""
import csv
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
E8 = HERE.parent/'full_small2_reset_gpr_recovery01'
PROFILE_SHA = 'b0c5f3860c09ae2e63c661432f29ac0b31ced24e3a071656a8df8077178d6418'
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
_s = importlib.util.spec_from_file_location('e32_reviewed_reset_proof', E8/'checker.py')
proof = importlib.util.module_from_spec(_s)
_s.loader.exec_module(proof)
legacy = proof.legacy
REF, G, READY_SHA = legacy.REF, legacy.G, legacy.READY_SHA
read, require, common = legacy.read, legacy.require, legacy.common
SHAPE = 'rvv_matrix_e32_mf2'
SHAPES = (SHAPE,)
MASK64, VETO = legacy.MASK64, legacy.VETO
marker, console_gate = legacy.marker, legacy.console_gate
memory_op, loaded_value = legacy.memory_op, legacy.loaded_value


def specification(shape):
    require(shape == SHAPE, 'Only full original e32 mf2')
    return legacy.specification(shape)


class Strict(legacy.Strict):
    def __init__(self, spec, gold, *, profile=None):
        original, plan = proof.validate_profile()
        require(sha(HERE/'reset_profile.json') == PROFILE_SHA, 'E32 profile drift')
        expected = dict(original, allowed_shape=SHAPE, source_profile_sha256=proof.PROFILE_SHA,
                        original_soc_elf_sha256=legacy.ELFS[1])
        bound = read(HERE/'reset_profile.json')
        require(bound == expected and (profile is None or profile == expected), 'Mismatched e32 reset profile')
        require(spec == plan['specs'][SHAPE] == specification(SHAPE), 'Exact original e32 spec required')
        model = REF/SHAPE/'model.json'
        require(sha(model) == plan['pins'][str(model)] and gold == read(model), 'Full5985 original model required')
        elf = Path(spec['backend']['elf'])
        require(sha(elf) == bound['original_soc_elf_sha256'] == plan['pins'][str(elf)], 'Exact e32 ELF required')
        super().__init__(spec, gold)
        self.regs = dict(enumerate(bound['initial_gpr_values']))
        self.reset_profile_sha256 = PROFILE_SHA


def audit(path, spec, abort=None):
    state = Strict(spec, read(REF/SHAPE/'model.json'))
    with Path(path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            if state.rows % 4096 == 0:
                require(abort is None or not abort.is_set(), 'Cancelled strict e32 trace')
            state.consume(row)
    return state.finish()


def artifacts(result, case, ledger, spec, abort):
    common.check_artifacts(result, dict(case, original_name=case['id']), ledger)
    console_gate((result.artifact_dir/'console.log').read_text(), spec['config'])
    require(not VETO.search((result.artifact_dir/'work/run.vcs.log').read_text()), 'Raw VCS failure')
    return audit(result.artifact_dir/'commit_trace.csv', spec, abort)
