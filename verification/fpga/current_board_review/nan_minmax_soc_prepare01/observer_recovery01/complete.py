"""One original-raw recovery, then one undispatched bounded reference; no DUT."""
import argparse
import copy
import importlib.util
import resource
import subprocess
import sys
import time
import traceback
from pathlib import Path

REC = Path(__file__).resolve().parent
sys.path.insert(0, str(REC.parent))
from common import *
from raw_mutations import insert_nv

spec_module = importlib.util.spec_from_file_location('reviewed_offline_checker', REC/'checker.py')
checker = importlib.util.module_from_spec(spec_module)
spec_module.loader.exec_module(checker)
OUT = REC/'complete01'
REVIEWED = {str(REC/'checker.py'):'783ca239cc93e90dc6579f75ed7f6cc92cd59bce9a1820dbf31ddd08d40f9958',
            str(REC/'host02.json'):'0956086ea83ac2562f8533f4b47f3e94d8d2879f3d1bc883a54305af2d1a3832'}


def decode(line, original):
    match = checker.LINE.fullmatch(line.rstrip('\n'))
    require(match is not None, 'raw witness syntax')
    pc, encoding, tail = int(match[1],16), match[2][2:], match[3]
    row = copy.deepcopy(original)
    row.update(pc=pc, insn=encoding,
               regs={k:int(v,16) for k,v in checker.REG.findall(tail)},
               csrs={k:int(v,16) for k,v in checker.CSR.findall(tail)},
               vectors={k:int(v,16).to_bytes(128,'little').hex() for k,v in checker.VECTOR.findall(tail)},
               memory=[[int(a,16),int(v,16) if v else None] for a,v in checker.MEM.findall(tail)])
    return row


def parse(shape):
    dest = HERE/shape
    out = OUT/shape
    s = checker.specification(dest)
    a = read(dest/'reference01/admission.json')
    checkpins(a['pins'])
    checkpins(REVIEWED)
    helper_lines = {}
    oracle_lines = []
    target_pcs = {f'0x{r[0]:016x}':i for i,r in enumerate(s['helper'])}
    lbu_pc = f"0x{s['output_lbu'][0]:016x}"
    def capture(line):
        # Capture authentic effect witnesses during the only full raw scan.
        for pc, index in target_pcs.items():
            if pc in line[:48]:
                require(index not in helper_lines, 'repeated helper capture')
                helper_lines[index] = line
                break
        if lbu_pc in line[:48]:
            oracle_lines.append(line)
        return line
    raw = dest/'reference01/commits.log'
    data = checker.extract(dest, raw, capture)
    checker.validate(s, data)
    require(data['terminal']['firmware_retired'] < read(dest/'static_cost.json')['upper_instructions'],
            'actual firmware cost exceeds static bound')
    require(len(helper_lines)==21 and len(oracle_lines)==144, 'complete authentic raw witnesses')
    baseline = checker.host_negatives(s,data)
    negatives = []
    for name,index,operation in [
        ('raw_inserted_NV',11,insert_nv),
        ('raw_wrong_result',11,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_wrong_mask',5,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('ff'*128),line,count=1)),
        ('raw_wrong_seed',1,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_wrong_input',4,lambda line:checker.VECTOR.sub(
            lambda m:f'v{m[1]} 0x'+('00'*128),line,count=1)),
        ('raw_nonzero_return_flags',13,lambda line:checker.REG.sub(
            lambda m:f'x{m[1]} 0x0000000000000010',line,count=1)),
        ('raw_missing_explicit_clear',10,lambda line:checker.CSR.sub('',line)),
        ('raw_wrong_opcode',11,lambda line:line.replace('0x1c881c57','0x14881c57')),
    ]:
        mutated = operation(helper_lines[index])
        require(mutated != helper_lines[index], 'raw mutation applied')
        bad = copy.deepcopy(data)
        bad['helper'][index] = decode(mutated,data['helper'][index])
        try:
            checker.validate(s,bad)
        except ValueError as error:
            negatives.append({'negative':name,'reason':str(error),'original_line':helper_lines[index],
                              'mutated_line':mutated})
        else:
            raise ValueError('actual raw witness negative accepted: '+name)
    for offset in (0,8,100,143):
        bad = copy.deepcopy(data)
        line = checker.REG.sub(lambda m:f'x{m[1]} 0x0000000000000000',oracle_lines[offset],count=1)
        match = checker.LINE.fullmatch(line.rstrip('\n'))
        values = checker.REG.findall(match[3])
        require(len(values)==1,'raw oracle GPR effect')
        bad['output_reads'][offset][1] = int(values[0][1],16)
        # Offset8 is already zero in canonical NaN: corrupt to a nonzero byte.
        if bad['output_reads'][offset][1] == data['output_reads'][offset][1]:
            bad['output_reads'][offset][1] ^= 1
            line = checker.REG.sub(lambda m:f'x{m[1]} 0x0000000000000001',line,count=1)
        try:
            checker.validate(s,bad)
        except ValueError as error:
            negatives.append({'negative':'raw_oracle_byte_'+str(offset),'reason':str(error),
                              'original_line':oracle_lines[offset],'mutated_line':line})
        else:
            raise ValueError('actual raw oracle negative accepted')
    save(out/'ledger.json',data)
    save(out/'raw_witness_host.json',{'status':'PASS_HOST_ACTUAL_RAW_WITNESSES','negatives':negatives,
         'baseline':baseline,'full_raw_passes':1,'witness_source':'captured in original full extraction',
         'scope':'raw-line effect decode + complete ledger validation; no repeated whole-stream extraction'})
    checkpins(a['pins'])
    checkpins(REVIEWED)
    save(out/'architectural_result.json',{'status':'ARCHITECTURAL_REFERENCE_ACCEPTED_BY_EXECUTOR_NOT_DUT',
         'shape':shape,'original_scope':config(shape),'target_calls':1,'helper_instructions':21,
         'full_output_oracle_bytes':144,'result':hex(config(shape)['expected']),'flags':0,'vstart':0,
         'firmware_retired':data['terminal']['firmware_retired'],'retired_total':data['retired_total'],
         'parking_retired':data['parking_retired'],'pins_pre_post_unchanged':True,
         'raw_sha256':sha(raw),'DUT_run':False,'original_worker_STOPPED_preserved':True})


def run_parse(shape):
    out = OUT/shape
    out.mkdir()
    command = [sys.executable,'-B',str(Path(__file__).resolve()),'parse',shape]
    save(out/'parser_command.json',command)
    started = time.monotonic()
    with (out/'parser.log').open('x') as stream:
        child = subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
        code = child.wait()
    # Persist the actual wait result before result/metadata/pin inspection.
    save(out/'parser_actual_exit_unvalidated.json',{'returncode':code,'child_pid':child.pid,
         'elapsed_s':time.monotonic()-started,'validated':False,'command_sha256':sha(out/'parser_command.json')})
    require(code==0,'offline parser failed: no retry/dispatch')
    require(read(out/'architectural_result.json')['pins_pre_post_unchanged'],'parser pins')
    return read(out/'architectural_result.json')


def dispatch_second():
    dest = HERE/'call1234'
    ref = dest/'reference01'
    a = read(ref/'admission.json')
    require(a['limits']==LIMITS and a['profile']==ISA,'original bounds unchanged')
    checkpins(a['pins'])
    checkpins(REVIEWED)
    require(not (ref/'ATTEMPT_STARTED.json').exists() and not (ref/'commits.log').exists(),
            'second case already attempted')
    save(ref/'ATTEMPT_STARTED.json',{'authority':'main explicit authorization after offline first recovery',
         'time':time.time(),'admission_sha256':sha(ref/'admission.json'),'retries':0,
         'successor_checker_sha256':sha(REC/'checker.py')})
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['raw_bytes'],LIMITS['raw_bytes']))
    started=time.monotonic()
    timed_out=False
    with (ref/'spike.log').open('x') as stream:
        child=subprocess.Popen(a['command'],stdout=stream,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:
            code=child.wait(timeout=LIMITS['seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True
            child.kill()
            code=child.wait()
    elapsed=time.monotonic()-started
    save(ref/'actual_exit_unvalidated.json',{'returncode':code,'child_pid':child.pid,
         'elapsed_s':elapsed,'timed_out':timed_out,'validated':False,
         'admission_sha256':sha(ref/'admission.json')})
    require(code==0 and not timed_out and elapsed<120,'second reference execution failed: no retry')
    raw_info={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}
              for p in (ref/'commits.log',ref/'spike.log')}
    save(ref/'execution.json',{'returncode':code,'child_pid':child.pid,'timed_out':timed_out,
         'elapsed_s':elapsed,'raw':raw_info,'validated':False})
    require(all(v['bytes']<=LIMITS['raw_bytes'] for v in raw_info.values()),'raw resource bound')
    checkpins(a['pins'])
    checkpins(REVIEWED)


def complete():
    OUT.mkdir()
    stopped=HERE/'STOPPED.json'
    original_receipt=HERE/'call1294/reference01/actual_exit_unvalidated.json'
    original_execution=HERE/'call1294/reference01/execution.json'
    pins=dict(REVIEWED)
    pins.update({str(p):sha(p) for p in (stopped,original_receipt,original_execution,
                HERE/'reference.py',HERE/'check_reference.py',Path(__file__).resolve(),REC/'raw_mutations.py')})
    for shape in SHAPES:
        pins.update(read(HERE/shape/'reference01/admission.json')['pins'])
    checkpins(pins)
    save(OUT/'pins_pre.json',pins)
    save(OUT/'AUTHORITY.json',{'scope':'once offline call1294, then once undispatched call1234 Spike only',
         'limits':LIMITS,'original_STOPPED_not_overwritten':True,'no_DUT_or_build':True})
    try:
        results=[run_parse('call1294')]
        dispatch_second()
        results.append(run_parse('call1234'))
        checkpins(pins)
        save(OUT/'pins_post.json',{p:sha(p) for p in pins})
        ready={'status':'TWO_SOURCE_SINGLE_ARCHITECTURAL_REFERENCES_READY_PENDING_INDEPENDENT_TERMINAL_REVIEW',
               'original_worker_status':'STOPPED_FIRST_ERROR_NO_RETRY_PRESERVED',
               'original_firstcause':'raw bitwise result/flags/vstart observer delta error',
               'results':results,'pins_pre_post_unchanged':True,'DUT_run':False,
               'new_min_reference_run':False,'source_scope':'two selected singles, not Linux/parent'}
        ready['result_pins']={str(p):sha(p) for p in OUT.rglob('*') if p.is_file()}
        save(OUT/'READY.json',ready)
        print('READY',sha(OUT/'READY.json'),flush=True)
    except BaseException as error:
        save(OUT/'STOPPED.json',{'status':'STOPPED_NEW_FIRST_ERROR_NO_RETRY','error':repr(error),
             'traceback':traceback.format_exc(),'original_STOPPED_preserved':True})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['complete','parse'])
    parser.add_argument('shape',nargs='?',choices=SHAPES)
    args=parser.parse_args()
    parse(args.shape) if args.action=='parse' else complete()
