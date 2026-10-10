"""Offline closure: original gates, gated edges separated from global time."""
import argparse
import inspect
import json
import re
import shutil
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_akv_canonical_kfault as original

life, require = original.life, original.require
ORIGINAL_SHA = '8d6167119631ee3ac3fb5cd6e9b65c49e40db1cf896f0e56e7783884c71ba928'
WAVE_SHAS = ('5d97012851b29db83d61c25c34f65d114d2a2c645672e34b6fea35548d7663c1',
             'da0acddeb0229fc9466507695e7dd268ab040d103525ae097d2c614a6b19853a')
PERIOD = 10000  # VCD100fs units; frozen TB ClockPeriod=1ns.
EPOCH = 155000  # First post-reset rising edge; monitor prints pre-NBA cycle0.


def source_gate():
    require(life.digest(Path(original.__file__)) == ORIGINAL_SHA, 'Exact frozen collector')
    source = inspect.getsource(original.cycle_gate)
    require(source.count('last_cycle') == 2 and 'and ticks > last_cycle' in source,
        'Global-cycle argument used only by rejected final comparison')
    book = life.read_bound(original.p.BOOK,original.p.BOOK_SHA)
    paths = ['hardware/tb/ara_tb.sv','hardware/tb/ara_commit_monitor.sv',
        'hardware/tb/ara_testharness.sv','hardware/src/ara_soc.sv',
        'hardware/src/ara_system.sv','hardware/src/vlsu/vlsu.sv']
    pins = {str(life.ROOT/p):book[str(life.ROOT/p)] for p in paths}; life.check(pins)
    tb = (life.ROOT/paths[0]).read_text()
    require('localparam ClockPeriod  = 1ns;' in tb, 'Frozen 1ns global period')
    block = tb[tb.index('// Controlling the reset'):tb.index('begin : uvm_inflight_reset')]
    require(re.search(r"clk\s*=\s*1'b0;\s*rst_n\s*=\s*1'b0;",block)
        and 'repeat (10) #(ClockPeriod/2) clk = ~clk;' in block
        and block.count('repeat (5) #(ClockPeriod);') == 2
        and re.search(r"repeat \(5\) #\(ClockPeriod\);\s*rst_n = 1'b1;\s*repeat \(5\) #\(ClockPeriod\);",block)
        and 'forever #(ClockPeriod/2) clk = ~clk;' in block, 'Frozen reset and first post-reset edge schedule')
    monitor = (life.ROOT/paths[1]).read_text()
    require('always_ff @(posedge clk_i or negedge rst_ni)' in monitor
        and "cycle_q <= '0;" in monitor and 'cycle_q <= cycle_q + 1;' in monitor
        and 'cycle_q, next_order, port,' in monitor, 'Global pre-NBA monitor counter semantics')
    system = (life.ROOT/'hardware/src/ara_system.sv').read_text()
    bind = system[system.index(') i_ara_commit_monitor ('):]
    require(re.match(r'\) i_ara_commit_monitor \(\s*\.clk_i\s*\(clk_i\s*\),\s*\.rst_ni\s*\(rst_ni\s*\),',bind), 'Monitor ungated system clock/reset')
    vlsu = (life.ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
    require('.clk_i                         (akv_clk),' in vlsu
        and re.search(r'i_akv_clk_gate\s*\(.*?\.clk_i,.*?\.en_i\s*\(akv_clk_en\).*?\.clk_o\s*\(akv_clk\)',vlsu,re.S), 'Distinct AKV gated clock source')
    for file in ('hardware/tb/ara_testharness.sv','hardware/src/ara_soc.sv'):
        require(re.search(r'\.clk_i\s*\(clk_i\s*\)',(life.ROOT/file).read_text()), 'Clock chain source '+file)
    require(re.search(r'\.clk_i\s*\(clk\s*\)',tb), 'TB global clock feeds harness')
    return pins


def terminal_time(path, log, cycle):
    last = -1
    with path.open() as stream:
        require(stream.readline().strip() == '$timescale'
            and stream.readline().strip() == '100fs'
            and stream.readline().strip() == '$end', 'Exact VCD 100fs timescale')
        for raw in stream:
            line = raw.strip()
            if line.startswith('#'):
                require(re.fullmatch(r'#[0-9]+',line), 'Strict VCD timestamp token')
                value = int(line[1:]); require(value > last, 'Strict monotonic EOF timestamp')
                last = value
    finish = re.findall(r'(?m)^\$finish at simulation time\s+([0-9]+)\s*$',log)
    times = re.findall(r'(?m)^Time:\s*([0-9]+) fs\s*$',log)
    require(len(finish) == len(times) == 1 and int(times[0]) % 100 == 0
        and last == int(finish[0]) == int(times[0])//100, 'VCD EOF equals actual finish and VCS report time')
    require(type(cycle) is int and cycle > 0 and last == EPOCH+cycle*PERIOD,
        'Exact global monitor epoch/period/terminal binding')
    return last


def wave_gate(path,last_cycle,phase,log):
    endpoint = terminal_time(path,log,last_cycle)
    root = original.runner.SCOPE
    parser = FunctionType(original.prior.wave.vcd.__code__,dict(original.prior.wave.vcd.__globals__,ROOT=root,WIDTHS={'clk_i':1,'rst_ni':1}))
    iterator = iter(parser(path)); _,declarations = next(iterator)
    names = {k[len(root)+1:]:v for k,v in declarations.items() if k.startswith(root+'.')}
    for name in original.runner.PROBE_NAMES:
        require(name in names or any(k.startswith(name+'.') for k in names), 'All exact frozen probe objects')
    for name in ('mmu_exception_i','planner_fault_mmu_exception','fault_mmu_exception_o'):
        require(names.get(name+'.cause',{}).get('width') == 64 and names.get(name+'.tval',{}).get('width') == 64, 'Exact exception shape')
    reset_events = []; state = {}; edge_times = []; last_frame = -1; previous_reset = None
    def frames():
        nonlocal state,last_frame,previous_reset
        clock = names['clk_i']['code']; reset = names['rst_ni']['code']
        for time,before,after in iterator:
            last_frame = time; state = after
            current_reset = after.get(reset)
            require(current_reset in ('0','1'), 'Known reset throughout capture')
            if current_reset != previous_reset:
                reset_events.append((time,current_reset)); previous_reset = current_reset
            if before.get(clock) != '0' or after.get(clock) != '1': continue
            if before.get(reset) == '1':
                require(time >= EPOCH and (time-EPOCH) % PERIOD == 0, 'Every gated rise lies on global edge lattice')
                edge_times.append(time)
            sample = {}
            for name,item in names.items():
                bits = before.get(item['code'],'x'); sample[name] = int(bits,2) if set(bits) <= set('01') else None
            yield time,sample
    # Only the erroneous count-domain argument changes. All fault/owner/drain,
    # retry, physical-range, response and idle checks execute frozen bytecode.
    result = original.cycle_gate(frames(),last_cycle=0,addresses=(original.p.ADDRESSES[phase],))
    require(reset_events == [(0,'0'),(10*PERIOD,'1')], 'One exact initial reset epoch, no active reset')
    require(edge_times and last_frame <= endpoint and edge_times[-1] <= last_frame, 'Complete ordered waveform evidence')
    wanted = {'rst_ni':1,'clk_i':0,'plan_state_q':0,'fault_pending_q':0,'fault_valid_o':0,
        'axi_ar_valid_o':0,'burst_fifo_count_q':0,'range_fifo_count_q':0,
        'ar_stalled_q':0,'response_drain_q':0,'completion_valid_o':0,'mmu_req_o':0}
    for name,value in wanted.items():
        bits = state.get(names[name]['code'],'x')
        require(set(bits) <= set('01') and int(bits,2) == value, 'Held terminal state '+name)
    result['global_terminal_evidence'] = dict(VCD_units='100fs',VCD_EOF_timestamp=endpoint,
        last_change_frame=last_frame,last_gated_edge=edge_times[-1],global_last_commit_cycle=last_cycle,
        first_global_edge=EPOCH,global_period=PERIOD,reset_events=reset_events,
        held_idle_until_EOF=True,gated_edges_not_global_cycles=True)
    return result


def collect(run,seal,capture,output):
    require(output.parent == life.OUT and not output.exists() and capture != output,
        'Fresh independent closure output')
    pins = source_gate()
    manifest = life.read_bound(run.with_name(run.name+'.prepared.json'),seal); phase = manifest['phase']
    vcd = capture/'focused.vcd'; failure = capture/'failure.json'
    require(life.digest(vcd) == WAVE_SHAS[phase]
        and json.loads(failure.read_text()) == dict(reason='Complete two faults/retries/terminal waveform',coverage_admitted=False), 'Exact preserved HOLD conversion evidence')
    pins = life.merge_pins(pins,{str(vcd):WAVE_SHAS[phase],str(failure):life.digest(failure),
        str(Path(__file__)):life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_akv_canonical_kfault_epoch_offline.py')):life.digest(Path(__file__).with_name('test_akv_canonical_kfault_epoch_offline.py'))})
    log = (run/'run.vcs.log').read_text(); proof = {}
    def reuse_conversion(command,stdout,stderr,check,timeout):
        require(command == [str(original.prior.CONVERTER),'+splitpacked',str(run/'akv-canonical-kfault.vpd'),str(output/'focused.vcd')]
            and check is True and timeout == 120, 'Only exact conversion reuse allowed')
        life.check(pins); shutil.copyfile(vcd,output/'focused.vcd')
        require(life.digest(output/'focused.vcd') == WAVE_SHAS[phase], 'Reused conversion byte equality')
        stdout.write('READONLY REUSE OF PREVIOUS ACTUAL VPD CONVERSION; NO CONVERTER EXECUTED\n'+str(vcd)+'\n'+WAVE_SHAS[phase]+'\n')
    def wave(path,last_cycle,index):
        require(index == phase, 'Bound native phase')
        result = wave_gate(path,last_cycle,index,log); proof.update(result['global_terminal_evidence']); return result
    def save(path,value):
        if path == output/'qualification.json':
            require(proof and value['coverage_admitted'] is False, 'Complete offline clock closure only')
            value['input_pins'] = life.merge_pins(value['input_pins'],pins); life.check(value['input_pins'])
            value['offline_epoch_closure'] = dict(original_HOLD_preserved=str(failure),
                original_collector_sha=ORIGINAL_SHA,existing_conversion=str(vcd),
                native_VCS_reexecuted=False,converter_reexecuted=False,clock_proof=proof)
        life.save(path,value)
    private_life = SimpleNamespace(**dict(vars(life),save=save))
    namespace = dict(original.collect.__globals__,life=private_life,
        subprocess=SimpleNamespace(run=reuse_conversion,STDOUT=original.subprocess.STDOUT),cycle_wave=wave)
    FunctionType(original.collect.__code__,namespace,argdefs=original.collect.__defaults__)(run,seal,output)
    print(json.dumps(dict(qualification=str(output/'qualification.json'),seal=life.digest(output/'qualification.json'))),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--seal',required=True)
    parser.add_argument('--capture-output',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); collect(args.run.resolve(),args.seal,args.capture_output.resolve(),args.output.resolve())
