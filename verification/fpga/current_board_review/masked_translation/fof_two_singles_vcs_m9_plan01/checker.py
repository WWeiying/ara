"""Two authentic FOF singles: SoC-only identity and artifact gates."""
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
REF = HERE.parent / 'fof_original_two_singles01'
READY_SHA = '502c78d6d3466258f3452d28738c155eaa6c4701029f6a70ab677b2b58fa6f7d'
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
SHAPES = (8, 64)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

source = load('fof_immutable_reference_oracle', REF / 'recovery01/observer.py')
sys.path.insert(0, str(G / 'gather_repair05'))
import regression as common
read, require = common.read, source.require
def sha(path):
    return common.sha(Path(path))
VETO = re.compile(common.BAD.pattern + r'|FOF_ORIGINAL_SINGLE_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b', re.I)
REVIEW = HERE.parent / 'fof_two_adapter_review01'
REVIEW_PINS = {
    str(REVIEW / 'REVIEW.md'): 'cdaf718e5e31b3bad31a37369211e2fcc6f623a2ea9949622e8b816ed0ad2e9c',
    str(REVIEW / 'decision.json'): '3b51f0b43cc28b9ba7ebe732c84667e99421cc02acf59c049746ebc03b9f035c',
}

def accepted_review():
    common.base.verify_pins(REVIEW_PINS)
    r = read(REVIEW / 'decision.json')
    require(r['status'] == 'ACCEPTED_STATIC_SOURCE_ADAPTER_AND_REFERENCE_METADATA_ONLY_NOT_DUT'
            and r['decision'] == 'NO_STATIC_ADAPTER_BLOCKER' and r['blockers'] == []
            and r['ready_sha256'] == READY_SHA and r['verification']['ready_pin_count'] == 118
            and r['scope']['source_cases'] == 2 and r['dut_launch_authorized'] is False,
            'Actual independent static review contract')
    return dict(REVIEW_PINS)

def specification(sew):
    require(sew in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Scope/READY drift')
    root = REF / 'software01' / f'e{sew}'
    symbols = read(root / 'soc.symbols.json')
    code = source.disassemble((root / 'soc.dis').read_text())
    helper = source.window(code, symbols['load_1'], 11)
    unused = source.window(code, symbols['load_0'], 11)
    capacity = source.window(code, symbols['capacity'], 3)
    elf = root / 'soc.elf'
    require(sha(elf) == read(REF / 'READY.json')['pins'][str(elf)], 'SoC ELF drift')
    require('tohost' not in symbols and 'replay_log' not in symbols, 'Must use actual SoC symbols')
    exit_store, = [p for p, i in code.items() if symbols['replay_exit'] <= p < symbols['check'] and i & 0x707f == 0x3023]
    require(code[exit_store + 4] == 0xa001, 'Original SoC parking')
    require(code[helper[3]] == (0x01050c07 if sew == 8 else 0x01057c07), 'Actual FOF opcode')
    return dict(sew=sew, elf=str(elf), elf_sha256=sha(elf), symbols=symbols,
                code={str(k): v for k, v in code.items()}, helper=helper, unused=unused,
                capacity=capacity, exit_store=exit_store, park=exit_store + 4)

def scope():
    return [dict(id=f'fof_original_e{sew}_scenario{0 if sew == 8 else 5}',
                 original_name=f'rvv_small_exceptions_e{sew}_scenario{0 if sew == 8 else 5}',
                 sew=sew, elf=specification(sew)['elf'], sha256=specification(sew)['elf_sha256'],
                 timeout_s=1800, pass_markers=['FOF_ORIGINAL_SINGLE_PASS']) for sew in SHAPES]

def runtime_case(case):
    require(case in scope(), 'Historical/runtime source membership')
    return dict(case, original_name=case['id'])

def console_gate(text):
    require(not VETO.search(text), 'Raw failure marker')
    require(text.splitlines().count('FOF_ORIGINAL_SINGLE_PASS') == 1, 'Missing/duplicate original oracle')
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text, 'Missing actual successful finish')

def artifacts(result, case, ledger, spec, validator):
    import csv_check
    require(result.status == 'PASS' and type(result.returncode) is int and result.returncode == 0
            and result.name == case['id'] and not result.reason, 'Actual child PASS/0 required')
    common.check_artifacts(result, runtime_case(case), ledger)
    root = result.artifact_dir
    for name in ('child_outcome.unvalidated.json', 'monitor_outcome.unvalidated.json'):
        r = read(root / name)
        require(type(r['returncode']) is int and r['returncode'] == 0
                and r['architectural_acceptance'] is False and r['elapsed_s'] == result.elapsed_s
                and r['command_sha256'] == sha(root / 'command.json'), 'Durable actual numeric outcome')
        if name.startswith('monitor'):
            require(not r['timed_out'] and not r['failure_seen'] and not r['abort_set'], 'Monitor abort/failure')
        else:
            require(r['name'] == case['id'] and r['status'] == 'PASS', 'Durable child identity')
    for name in ('console.log', 'work/run.vcs.log'):
        console_gate((root / name).read_text())
    generic = validator(root / 'commit_trace.csv')
    require(generic['cvx_exception_count'] == 0 and generic['architecture_request_count'] > 0
            and generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0,
            'CVX/arch/uop protocol completion')
    strict = csv_check.analyze(root / 'commit_trace.csv', spec)
    common.save(root / 'strict_csv.json', strict)
    require(strict['status'] == 'PASS_FOF_ORIGINAL_SINGLE', str(strict))
    require(strict['memory_owner_count']==4 and strict['helper_owner_count']==3
            and strict['unchanged_business_oracle'] is True, 'Four nonempty source owners and exact ABI')
    require((strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']), 'CSV count disagreement')
    return dict(generic=generic, strict=strict, csv_sha256=sha(root / 'commit_trace.csv'),
                scope='Two selected source-derived Sv39 singles, not Linux/all eight historical ELFs',
                zero_physical_MMU_activity_proved=False)

# Load only the sealed oracle; the new known-GPR and lifecycle layers inherit it.
csv_source = load('fof_m6_csv_oracle', HERE.parent/'fof_two_singles_vcs_m6_plan01/csv_check.py')
import source_owners
