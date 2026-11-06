#!/usr/bin/env python3
"""One isolated VCS build: existing command checks plus independent port probes."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from audit import digest, require, verify_pins
from projection_resources import check

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = ROOT.parent / 'ara_dsa_signoff_integration'
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_tile_context_engine import run_command


def bench_source(text):
    for old, new in (
        ('module qbs_compute_engine_tb;', 'module projection_resource_tb;'),
        ('endmodule : qbs_compute_engine_tb', 'endmodule : projection_resource_tb'),
        ('  qbs_compute_engine dut (', '  `include "projection_resource_monitor.svh"\n\n  qbs_compute_engine dut ('),
        ('      total_errors += case_errors;', '      snapshot_resources(case_id);\n      total_errors += case_errors;'),
    ):
        require(text.count(old) == 1, 'Bench anchor drift: ' + old)
        text = text.replace(old, new, 1)
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--real-capture', type=Path)
    p.add_argument('--capture-pins', type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.is_relative_to(VERIFY / 'verification/out'), 'Use sole verification output area')
    require(bool(a.real_capture) == bool(a.capture_pins), 'Real capture requires an accepted pin inventory')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}; commands = []
    state = dict(state='PREPARING',pid=os.getpid(),child_pid=None,
                 hardware_changed=False,model_performance_measured=False)
    def save():
        (out / 'status.json').write_text(json.dumps(state, indent=2)+'\n')
    def pin(path):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(path not in pins or pins[path] == sha, 'Input drift: '+path)
        pins[path] = sha
    def started(pid):
        state['child_pid'] = pid; save()
    def run(argv, label, bound=120):
        argv = list(map(str, argv)); resolved = shutil.which(argv[0])
        require(resolved is not None, 'Missing tool: '+argv[0]); argv[0] = resolved; pin(resolved)
        verify_pins(pins)
        commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        state['state'] = label.upper(); save()
        try:
            require(run_command(argv,out/(label+'.log'),bound,os.environ.copy(),started) == 0,
                    label+' failed')
        finally:
            state['child_pid'] = None; save()
        return (out/(label+'.log')).read_text()
    try:
        directory = ROOT/'verification/qbs'
        template = directory/'qbs_compute_engine_tb.sv'
        for path in (Path(__file__),HERE/'projection_resources.py',HERE/'audit.py',
                     HERE/'projection_resource_monitor.svh',template,directory/'Makefile',
                     directory/'run_tile_context_engine.py',directory/'run_half_scale_soc.py'):
            pin(path)
        for path in (ROOT/'hardware/deps/common_cells/include').rglob('*.svh'): pin(path)
        for path in (ROOT/'hardware/deps/axi/include').rglob('*.svh'): pin(path)
        sources = run(['make','-s','--no-print-directory','-C',directory,
                       "--eval=resource-sources:;@printf '%s\\n' $(RTL_SOURCES)",
                       'resource-sources'],'sources').splitlines()
        require(sources and all(Path(x).is_file() for x in sources), 'Invalid RTL inventory')
        for path in sources: pin(path)
        bench = out/'projection_resource_tb.sv'; bench.write_text(bench_source(template.read_text())); pin(bench)
        compiler = shutil.which('gcc'); require(compiler is not None, 'GCC missing')
        cc = [compiler,'-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-frounding-math']
        inputs = [directory/'qbs_command_vectors.c',directory/'qbs_ref.c']
        for i,path in enumerate(inputs):
            deps = run([*cc,'-M','-MT','object',path],f'deps-{i}')
            for dep in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]): pin(out/dep if not Path(dep).is_absolute() else dep)
        generator = out/'generator'
        run([*cc,*inputs,'-lm','-o',generator],'generator-compile'); pin(generator)
        vectors = [out/'matrix.txt']; run([generator,vectors[0]],'matrix-generate'); pin(vectors[0])
        if a.real_capture:
            capture = a.real_capture.resolve(strict=True)
            old = json.loads(a.capture_pins.read_text()); pin(a.capture_pins)
            for name in ('weight_q4_K.json','weight_q4_K.bin','activation_f32.bin','output_f32.bin'):
                path = capture/name
                require(old.get(str(path)) == digest(path), 'Capture drift: '+str(path)); pin(path)
            shape = json.loads((capture/'weight_q4_K.json').read_text())['shape']
            require(len(shape) == 4 and shape[2:] == [1,1], 'Unexpected weight shape')
            for m in (1,4):
                path = out/f'real-m{m}.txt'
                run([generator,path,'--real','q4_K',capture,shape[1],shape[0],0,m,0,8],f'real-m{m}-generate')
                pin(path); vectors.append(path)
        includes = ['+incdir+'+str(ROOT/'hardware/include'),
                    '+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),
                    '+incdir+'+str(ROOT/'hardware/deps/axi/include'),'+incdir+'+str(HERE)]
        run(['vcs','-full64','-sverilog','-timescale=1ns/1ps','+lint=TFIPC-L',*includes,
             *sources,bench,'-top','projection_resource_tb','-o',out/'simv'],'compile',600)
        pin(out/'simv')
        libraries = list((out/'simv.daidir').rglob('*.so'))
        require(libraries, 'Missing simulator libraries')
        for path in libraries: pin(path)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        results = []
        for vector in vectors:
            text = run([out/'simv','+QBS_COMMAND_VECTOR_FILE='+str(vector)],'run-'+vector.stem,300)
            results.append(dict(vector=str(vector),cases=check(text,vector.read_text())))
        verify_pins(pins)
        state.update(state='RTL_PORT_AUDIT_PASS',results=results,
                     source_pins_sha256=digest(out/'source-pins.json'),
                     artifacts={str(x):digest(x) for x in out.iterdir()
                                if x.is_file() and x.name not in ('result.json','status.json')},
                     limitations=['Synthetic matrix and explicit real-data slices, not whole inference',
                                  'Hypothetical service bounds exclude memory, dependencies and pipeline overhead',
                                  'No wider datapath or extra correction lane has been implemented'])
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc)); raise
    finally:
        save(); (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__ == '__main__':
    main()
