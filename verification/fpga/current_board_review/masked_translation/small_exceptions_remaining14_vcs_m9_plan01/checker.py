"""Fourteen exact original small-exception singles; M9-only gates."""
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
REF = HERE.parent / 'small_exceptions_remaining14_prepare01'
READY_SHA = '3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a'
IMAGE_SHA = '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
SHAPES = tuple((sew,sc) for sew in (8,16,32) for sc in ((1,2,3,5) if sew==8 else (0,1,2,3,5)))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

source = load('observer', REF / 'observer.py')
csv_source = load('csv_check', REF / 'csv_check.py')
source_owners = load('source_owners', REF / 'source_owners.py')
abi = load('abi_check', REF / 'abi_check.py')
diagnostics = load('diagnostics', REF / 'diagnostics.py')
sys.path.insert(0, str(G / 'gather_repair05'))
import regression as common
read, require = common.read, source.require
def sha(path):
    return common.sha(Path(path))
VETO = re.compile(common.BAD.pattern + r'|SMALL_EXCEPTIONS_14_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b', re.I)
def specification(pair):
    sew,scenario=pair
    require(pair in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Scope/READY drift')
    ready = read(REF / 'READY.json')
    require(sha(REF/'input_pins.json') == ready['pins_sha256'], 'Reference pin manifest drift')
    spec = read(REF / 'software01' / f'e{sew}_sc{scenario}' / 'soc.spec.json')
    expected = next(v for v in ready['members'] if (v['sew'],v['scenario']) == pair)
    require(spec['backend']=='soc' and spec['scenario']==scenario and spec['sew']==sew
            and sha(spec['elf'])==spec['elf_sha256']==expected['soc_elf_sha256'], 'Actual SoC ELF/spec')
    require('tohost' not in spec['symbols'] and 'replay_log' not in spec['symbols'], 'Actual CTRL-only SoC')
    return spec

def scope():
    return [dict(id=f'small_exceptions_e{sew}_sc{sc}',original_name=f'rvv_small_exceptions_e{sew}_scenario{sc}',
        scenario=sc,sew=sew,elf=specification((sew,sc))['elf'],sha256=specification((sew,sc))['elf_sha256'],
        timeout_s=1800,pass_markers=['SMALL_EXCEPTIONS_14_PASS']) for sew,sc in SHAPES]

def runtime_case(case):
    require(case in scope(), 'Historical/runtime source membership')
    return dict(case, original_name=case['id'])

def console_gate(text):
    require(not VETO.search(text), 'Raw failure marker')
    require(text.splitlines().count('SMALL_EXCEPTIONS_14_PASS') == 1, 'Missing/duplicate original oracle')
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
    strict = strict_csv(root / 'commit_trace.csv', spec)
    common.save(root / 'strict_csv.json', strict)
    require(strict['status'] == 'PASS_SMALL_EXCEPTIONS_14', str(strict))
    require(strict['lifecycle_successor']=='source-bound-four-memory-owners01'
            and strict['memory_owner_count']==4 and strict['helper_owner_count']==3,
            'Source-bound nonempty helper and target owners')
    require((strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']), 'CSV count disagreement')
    return dict(generic=generic, strict=strict, csv_sha256=sha(root / 'commit_trace.csv'),
                scope='Fourteen original source-derived Sv39 singles; not Linux/full parents',
                zero_physical_MMU_activity_proved=False)

def strict_csv(path,spec):
    import csv
    q=None;current=None;stage='SoC checker construction'
    try:
        q=abi.Checker(spec);stage='SoC owner/ABI/full source oracle'
        with Path(path).open() as stream:
            rows=csv.DictReader(stream)
            require(rows.fieldnames==csv_source.FIELDS,'Actual CSV header')
            for number,row in enumerate(rows,1):
                current=dict(row=number,**{k:row.get(k) for k in ('cycle','event','pc','insn')})
                q.row(row)
        stage='SoC complete oracle/owner/ABI terminal'
        return q.finish()
    except Exception as error:
        result=diagnostics.context(error,stage,current,f'e{spec["sew"]}_sc{spec["scenario"]}')
        result.update(status='NOT_ACCEPTED_FIRST_CHECKER_FAILURE',
                      checks=q.checks if q else None,actions=q.actions if q else None)
        return result
