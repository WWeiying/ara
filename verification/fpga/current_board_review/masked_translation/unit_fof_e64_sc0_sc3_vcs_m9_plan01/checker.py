"""Two e64 sc0/sc3 singles: M9-only identity and artifact gates."""
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
REF = HERE.parent / 'unit_fof_e64_sc0_sc3_prepare01'
READY_SHA = '8c2f89e677e1cf6148ad3d1013f1598a91ed77506a73266603d956ffe9672e1e'
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
SHAPES = (0, 3)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

source = load('observer', REF / 'observer.py')
csv_source = load('csv_check', REF / 'csv_check.py')
source_owners = load('source_owners', REF / 'source_owners.py')
sys.path.insert(0, str(G / 'gather_repair05'))
import regression as common
read, require = common.read, source.require
def sha(path):
    return common.sha(Path(path))
VETO = re.compile(common.BAD.pattern + r'|UNIT_FOF_E64_SC0_SC3_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b', re.I)
def specification(scenario):
    require(scenario in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Scope/READY drift')
    ready = read(REF / 'READY.json')
    require(sha(ready['input_pins']) == ready['input_pins_sha256'], 'Reference pin manifest drift')
    spec = read(REF / 'software01' / f'scenario{scenario}' / 'soc.spec.json')
    expected = next(v for v in ready['cases'] if v['scenario'] == scenario)
    require(spec['backend']=='soc' and spec['scenario']==scenario and spec['sew']==64
            and sha(spec['elf'])==spec['elf_sha256']==expected['soc_sha256'], 'Actual SoC ELF/spec')
    require('tohost' not in spec['symbols'] and 'replay_log' not in spec['symbols'], 'Actual CTRL-only SoC')
    return spec

def scope():
    return [dict(id=f'unit_fof_e64_scenario{n}',original_name=f'rvv_small_exceptions_e64_scenario{n}',
        scenario=n,sew=64,elf=specification(n)['elf'],sha256=specification(n)['elf_sha256'],
        timeout_s=1800,pass_markers=['UNIT_FOF_E64_SC0_SC3_PASS']) for n in SHAPES]

def runtime_case(case):
    require(case in scope(), 'Historical/runtime source membership')
    return dict(case, original_name=case['id'])

def console_gate(text):
    require(not VETO.search(text), 'Raw failure marker')
    require(text.splitlines().count('UNIT_FOF_E64_SC0_SC3_PASS') == 1, 'Missing/duplicate original oracle')
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text, 'Missing actual successful finish')

def artifacts(result, case, ledger, spec, validator):
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
    strict = source_owners.analyze(root / 'commit_trace.csv', spec)
    common.save(root / 'strict_csv.json', strict)
    require(strict['status'] == 'PASS_UNIT_FOF_E64_SC0_SC3', str(strict))
    require(strict['lifecycle_successor']=='source-bound-four-memory-owners01'
            and strict['memory_owner_count']==4 and strict['helper_owner_count']==3,
            'Source-bound nonempty helper and target owners')
    require((strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']), 'CSV count disagreement')
    return dict(generic=generic, strict=strict, csv_sha256=sha(root / 'commit_trace.csv'),
                scope='Two selected e64 sc0/sc3 source-derived Sv39 singles; not Linux/full parents',
                zero_physical_MMU_activity_proved=False)
