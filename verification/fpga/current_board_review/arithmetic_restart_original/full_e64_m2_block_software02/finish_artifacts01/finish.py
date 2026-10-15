"""Narrow constprop observer successor; consume old Host/SoC and compile only missing artifact."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
F=Path(__file__).resolve().parent
H=F.parent
OLD=H.parent/'full_e64_m2_block_software01'
s=importlib.util.spec_from_file_location('source02_utilities',H/'prepare.py');u=importlib.util.module_from_spec(s);s.loader.exec_module(u)
sha,require,save=u.sha,u.require,u.save
s=importlib.util.spec_from_file_location('sealed_inspection_readers',OLD/'inspect_compiled.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
def main():
    require(not (F/'preflight.json').exists(),'One completion, no retry')
    first=json.loads((H/'execution_receipt.json').read_text());compile_rc=json.loads((H/'soc/compile.log.exit.json').read_text())
    require(first['returncode']==1 and not first['timed_out'] and compile_rc['returncode']==0,'Actual old wrapper ERROR and successful compiler')
    require("Actual noninline FP helper" in (H/'execution.log').read_text(),'Exact first cause')
    pins=json.loads((H/'source_entry.json').read_text())['pins']
    for p,h in pins.items():require(sha(p)==h,'Frozen inputs '+p)
    for p in [F/'finish.py',F/'execute.py',H/'execution_receipt.json',H/'execution_terminal.json',H/'execution.log',H/'soc/program.elf',H/'soc/program.dis',H/'soc/symbols.json',H/'soc/compile.log.exit.json',OLD/'inspect_compiled.py']:pins[str(p)]=sha(p)
    host=[]
    for directory in sorted(H.glob('host_*')):
        if not directory.is_dir():continue
        for log in sorted(directory.glob('case*.log')):
            ex=json.loads(Path(str(log)+'.exit.json').read_text())
            require(type(ex['returncode']) is int and ex['returncode']==ex['expected_returncode'] and not ex['timed_out'],'Actual Host result '+str(log))
            host.append(dict(variant=directory.name[5:],log=str(log),sha256=sha(log),**ex))
        for p in directory.rglob('*'):
            if p.is_file():pins[str(p)]=sha(p)
    require(len(host)==35,'35 actual original/new/source-negative runs')
    for n in range(12):require((H/'host_original'/f'case{n}.log').read_bytes()==(H/'host_packed'/f'case{n}.log').read_bytes(),'Full oracle transcript equality')
    save(F/'preflight.json',dict(status='CONSTPROP_OBSERVER_ADAPT_ONLY',original_wrapper=first,pins=pins,already_completed_Host_runs=35,soc_compile_reused=True))
    require(not (H/'spike').exists(),'Missing compile was never dispatched')
    directory=H/'spike';directory.mkdir()
    u.emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
    command=json.loads((OLD/'spike/compile.log.command.json').read_text())['command']
    command=[x.replace(str(OLD),str(H)) for x in command]
    u.run(command,directory/'compile.log')
    u.base.disassemble(directory/'program.elf',directory/'program.dis')
    # Disassembler result is deterministically parsed by the same mature helper.
    _,symbols=u.base.disassemble(directory/'program.elf',F/'spike_symbols_disassembly.dis')
    save(directory/'symbols.json',symbols)
    code_original={pc:x['insn'] for pc,x in r.assembly(H/'original/program.dis').items()}
    proof=dict(status='HOST_COMPILED_CONSTPROP_OBSERVER_CORRECTED_COST_PENDING',original_wrapper_ERROR_preserved=True,first_wrapper=first,host=host,reference=False,DUT=False,backends={})
    for backend in ('soc','spike'):
        root=H/backend;symbols=r.read(root/'symbols.json');code={pc:x['insn'] for pc,x in r.assembly(root/'program.dis').items()}
        names=[n for n in symbols if n=='refresh_fp_period' or n=='refresh_fp_period.constprop.0']
        require(names==['refresh_fp_period.constprop.0'],'Only actual compiler clone identity, no wildcard')
        target=symbols[names[0]];body=r.assembly(root/'program.dis')
        calls=[pc for pc,x in body.items() if symbols['arithmetic_main']<=pc<symbols['capacity'] and x['op']=='jal' and int(x['args'].split()[0],16)==target]
        require(len(calls)==1,'Unique actual main-to-refresh call')
        helpers={n:u.base.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,window in helpers.items():u.base.archived_window(code_original,window);require(len(window)==(3 if n=='capacity' else 13),'Exact original helper')
        allowed={x['pc'] for w in helpers.values() for x in w}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra and sum(map(len,helpers.values()))==458,'No extraRVV/helper458')
        require(symbols['__stack_top']-symbols['__bss_end']>=65536,'Actual mapstack')
        fp=u.model.tables()[2];raw=(root/'program.elf').read_bytes();location=u.model.location(raw,fp,u.model.load_segments(raw))
        u.run([u.base.CC.with_name('riscv64-unknown-elf-size'),'-A',root/'program.elf'],root/'size.log')
        proof['backends'][backend]=dict(elf=str(root/'program.elf'),sha256=sha(root/'program.elf'),refresh_symbol=names[0],refresh_pc=target,refresh_main_call=calls[0],helpers=helpers,helper_instructions=458,extra_RVV=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'],FP640=location)
    save(F/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'All pre/post unchanged '+p)
    for p in H.rglob('*'):
        if p.is_file() and p.suffix!='.pyc' and not p.name.startswith('execution'):pins[str(p)]=sha(p)
    save(F/'pins.json',pins)
    print('ARTIFACTS_COMPLETE_ORIGINAL_ERROR_PRESERVED_NO_REFERENCE_NO_DUT',flush=True)
if __name__=='__main__':main()
