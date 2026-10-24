#!/usr/bin/env python3
"""Fresh host reference capture of real quantized KV; never measure RTL speed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import struct
import sys

sys.dont_write_bytecode = True
from layout import inspect, prefix_length, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import run_command


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def source_pins(root):
    names = subprocess.check_output(['git','-C',str(root),'ls-files','-c','-o','--exclude-standard','-z'])
    paths = set()
    for raw in names.split(b'\0'):
        if not raw:
            continue
        path = root/os.fsdecode(raw)
        if path.is_file() and (path.suffix.lower() in
                ('.c','.cc','.cpp','.cxx','.h','.hpp','.in','.cmake','.s') or path.name == 'CMakeLists.txt'):
            paths.add(path.resolve())
    require(root/'common/q4km-capture.cpp' in paths,'Missing original capture source')
    return {str(p):digest(p) for p in sorted(paths)}


def validate_capture(capture,kind):
    block = capture/'decode/block'
    files = {}
    for name in ('attn_q_input-0','attn_k_input-0','attn_v_input-0','attn_mask_input-0','kqv_out-0'):
        meta_path,binary = block/(name+'.json'),block/(name+'.bin')
        meta = json.loads(meta_path.read_text())
        require(binary.stat().st_size == meta['nbytes'],'Capture byte extent mismatch')
        files[name] = (meta,binary)
    q,qbin = files['attn_q_input-0']
    mask,mbin = files['attn_mask_input-0']
    golden,gbin = files['kqv_out-0']
    require(q['type'] == 'f32' and q['shape'] == [128,1,12,1] and qbin.stat().st_size == 6144,
            'Expected actual Qwen2.5 D128 Decode Query')
    require(golden['type'] == 'f32' and golden['shape'] == [1536,1,1,1] and gbin.stat().st_size == 6144,
            'Expected corresponding Attention result')
    require(all(math.isfinite(value) for binary in (qbin,gbin)
                for (value,) in struct.iter_unpack('<f',binary.read_bytes())),
            'Nonfinite captured Query or Attention output')
    require(mask['type'] == 'f16' and mask['shape'][1:] == [1,1,1], 'Mask type/axes')
    visible = prefix_length(mbin.read_bytes())
    views = {}
    for name,wanted in (('attn_k_input-0',kind),('attn_v_input-0','q8_0')):
        meta,binary = files[name]
        require(meta['type'] == wanted and meta['shape'][0] == 128 and meta['shape'][2:] == [2,1],
                'Actual cached type/head shape differs from requested configuration')
        require(meta['shape'][1] == mask['shape'][0] and mbin.stat().st_size == 2*meta['shape'][1],
                'Mask/cache capacity mismatch')
        views[name] = inspect(meta,binary.read_bytes(),visible)
    return dict(state='REAL_HOST_CAPTURE_LAYOUT_CHECKED',visible_tokens=visible,views=views,
        file_sha256={str(p):digest(p) for p in sorted(block.iterdir()) if p.is_file()},
        limits='Actual host model operands/output only; no RVV Query quantization bytes, native quantized-KV or RTL performance proof')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,default=Path('/home/wangwy/llama/llama-q4km-extract'))
    p.add_argument('--model',type=Path,default=Path('/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf'))
    p.add_argument('--prompt',type=Path,default=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128/prompt.txt'))
    p.add_argument('--jobs',type=int,default=16)
    a = p.parse_args()
    require(1 <= a.jobs <= 32,'Jobs must be 1..32')
    root,model,prompt = (p.resolve(strict=True) for p in (a.source,a.model,a.prompt))
    out = a.output.resolve()
    require(not out.is_relative_to(root),'Use independent build/capture directory')
    out.mkdir(parents=True,exist_ok=False)
    state = dict(state='PREPARING',pid=os.getpid(),child_pid=None,started=datetime.now(timezone.utc).isoformat())
    def save(name,value):
        temp = out/(name+'.partial')
        temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
        temp.replace(out/name)
    def started(pid):
        state['child_pid'] = pid
        save('status.json',state)
    def interrupted(signum,_frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for name in list(env):
        if name.startswith(('LLAMA_Q4KM_CAPTURE','GGML_RISCV_','AKV_')) or name == 'LD_PRELOAD':
            env.pop(name,None)
    commands = []
    def execute(argv,phase,timeout,extra=None):
        state['state'] = phase
        command = list(map(str,argv))
        commands.append(dict(argv=command,phase=phase,explicit_environment=extra or {},timeout=timeout))
        save('commands.json',commands)
        try:
            code = run_command(command,out/(phase.lower()+'.log'),timeout,dict(env,**(extra or {})),started)
            require(code == 0,f'{phase} returned {code}')
        finally:
            state['child_pid'] = None
            save('status.json',state)
    save('status.json',state)
    try:
        source_before = source_pins(root)
        pins = dict(source_before)
        pins.update({str(p):digest(p) for p in (model,prompt,Path(__file__).resolve(),HERE/'layout.py')})
        pins.update({str(p):digest(p) for p in (Path('/usr/bin/cmake'),Path('/usr/bin/gcc'),Path('/usr/bin/g++'))})
        save('source-pins.json',pins)
        revision = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        dirty = subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True)
        save('source-provenance.json',dict(root=str(root),commit=revision,dirty_tracked=dirty,
            contract='Fresh build of exact observed source bytes; no clean-tree claim'))
        build = out/'build'
        execute(['/usr/bin/cmake','-S',root,'-B',build,'-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_C_COMPILER=/usr/bin/gcc','-DCMAKE_CXX_COMPILER=/usr/bin/g++',
            '-DGGML_NATIVE=ON','-DGGML_OPENMP=OFF','-DGGML_BLAS=OFF','-DGGML_BACKEND_DL=OFF',
            '-DLLAMA_BUILD_TESTS=OFF','-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_SERVER=OFF',
            '-DLLAMA_BUILD_MTMD=OFF','-DLLAMA_BUILD_UI=OFF','-DLLAMA_BUILD_TOOLS=ON',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'],'CONFIGURING',300)
        execute(['/usr/bin/cmake','--build',build,'--target','llama-completion','--parallel',a.jobs],
                'BUILDING',1800)
        require(all(digest(p) == h for p,h in pins.items()) and source_pins(root) == source_before,
                'Source changed during build')
        binary = build/'bin/llama-completion'
        binary_hash = digest(binary)
        artifacts = {str(path):digest(path) for path in build.rglob('*.so*') if path.is_file()}
        artifacts.update({str(path):digest(path) for path in
            (binary,build/'CMakeCache.txt',build/'compile_commands.json')})
        save('build-artifacts.json',artifacts)
        results = {}
        for kind in ('q8_0','q4_0'):
            capture = out/('capture-k-'+kind+'-v-q8_0')
            capture.mkdir()
            execute([binary,'-m',model,'-f',prompt,'-n','2','-c','256','-t','8','-tb','8',
                '-no-cnv','--load-mode','mmap','--no-warmup','--no-display-prompt',
                '--seed','1','--temp','0','-fa','on','-ctk',kind,'-ctv','q8_0'],
                'CAPTURING_'+kind.upper(),600,dict(LLAMA_Q4KM_CAPTURE_DIR=str(capture),
                    LLAMA_Q4KM_CAPTURE_LAYER='0',LLAMA_Q4KM_CAPTURE_PHASE='decode',
                    LLAMA_Q4KM_CAPTURE_PROFILE='attention_core'))
            results[kind] = validate_capture(capture,kind)
            save('captures.json',results)
        require(digest(binary) == binary_hash and all(digest(p) == h for p,h in pins.items()) and
                all(digest(p) == h for p,h in artifacts.items()) and source_pins(root) == source_before,
                'Capture source/model/binary drift')
        save('result.json',dict(state='REAL_HOST_QUANTIZED_KV_CAPTURED',captures=results,
            binary=str(binary),binary_sha256=binary_hash,source_pins_sha256=digest(out/'source-pins.json'),
            build_artifacts_sha256=digest(out/'build-artifacts.json'),
            source_unchanged=True,rtl_performance=False,native_qbs_akv_accepted=False,
            scope='Reference capture only; not QBS/AKV native execution or RVV numerical acceptance'))
        state['state'] = 'REAL_HOST_QUANTIZED_KV_CAPTURED'
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc))
        save('result.json',dict(state='FAIL',error=repr(exc)))
        raise
    finally:
        state.update(child_pid=None,finished=datetime.now(timezone.utc).isoformat())
        save('status.json',state)


if __name__ == '__main__':
    main()
