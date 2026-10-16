"""Precise unit, ordered-indexed and strided Linux vector page-fault replay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

LMULS={'mf8':(1,8,5),'mf4':(1,4,6),'mf2':(1,2,7),
       'm1':(1,1,0),'m2':(2,1,1),'m4':(4,1,2),'m8':(8,1,3)}

def replay_elements(sew,indexed,width,fields):
    return min(8,((1<<width)-1)//(fields*(sew//8))+1) if indexed else 8

def assembly(sew,indexed=False,index_sew=None,lmul='m1',fields=1,strided=False):
    if sew not in (8,16,32,64):
        raise ValueError('Unsupported SEW')
    if index_sew is not None and (not indexed or index_sew not in (8,16,32,64)):
        raise ValueError('Index EEW requires indexed replay and a supported width')
    width=index_sew or sew
    if indexed and strided:raise ValueError('Choose indexed or strided addressing')
    if fields not in range(1,9):
        raise ValueError('Invalid segment field count')
    if lmul not in LMULS:raise ValueError('Unsupported LMUL')
    num,den,_=LMULS[lmul]
    if fields*num>8*den:raise ValueError('Reserved segment EMUL times NFIELDS')
    if sew*den>64*num or indexed and not (sew*den<=8*width*num<=64*sew*den):
        raise ValueError('Reserved data or index EMUL')
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for store in (0,1):
        if fields==1:
            loads=[f'vle{sew}.v v24,('+('a1' if store else 'a2')+')']
            readback=[f'vse{sew}.v v24,(a2)']
        else:
            loads=[f'slli t2,a4,{(sew//8).bit_length()-1}',
                   'mv t1,'+('a1' if store else 'a2')]
            readback=[f'slli t2,a4,{(sew//8).bit_length()-1}','mv t1,a2']
            for field in range(fields):
                register=24+field*max(1,num//den)
                loads += [f'vle{sew}.v v{register},(t1)','add t1,t1,t2']
                readback += [f'vse{sew}.v v{register},(t1)','add t1,t1,t2']
        if strided:
            target=(f"{'vssseg' if store else 'vlsseg'}{fields}e{sew}.v v24,(a0),t3,v0.t"
                    if fields>1 else f"{'vsse' if store else 'vlse'}{sew}.v v24,(a0),t3,v0.t")
        elif fields>1 and indexed:
            target=f"{'vsoxseg' if store else 'vloxseg'}{fields}ei{width}.v v24,(a0),v16,v0.t"
        elif fields>1:
            target=f"{'vs' if store else 'vl'}seg{fields}e{sew}.v v24,(a0),v0.t"
        elif indexed:
            target=f"{'vsoxei' if store else 'vloxei'}{width}.v v24,(a0),v16,v0.t"
        else:target=f"{'vse' if store else 'vle'}{sew}.v v24,(a0),v0.t"
        lines += [f'.global replay_{store}',f'replay_{store}:',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  *loads,
                  *([f'vle{width}.v v16,(a5)'] if indexed else []),
                  *(['ld t3,0(a5)'] if strided else []),
                  'vlm.v v0,(a3)',f'vsetivli t0,{replay_elements(sew,indexed,width,fields)},e{sew},{lmul},tu,mu',
                  f'.global fault_{store}_pc',f'fault_{store}_pc:',
                  target,
                  'csrr a0,vstart',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  *readback,'ret']
    return '\n'.join(lines)+'\n'


def run(out,cross,trace=False,negative_restart=False,indexed=False,index_sew=None,lmul='m1',fields=1,strided=False,negative_stride=False,zero_stride=False,negative_skip=False):
    if indexed and strided:raise ValueError('Choose indexed or strided addressing')
    if negative_stride and not strided:raise ValueError('Negative stride requires strided replay')
    if zero_stride and (not strided or negative_stride or negative_restart):
        raise ValueError('Zero stride requires strided mode without negative stride or restart-from-zero control')
    if negative_skip and not zero_stride:raise ValueError('Skip control requires zero stride')
    if fields not in range(1,9):
        raise ValueError('Invalid segment field count')
    if index_sew is not None and (not indexed or index_sew not in (8,16,32,64)):
        raise ValueError('Index EEW requires indexed replay and a supported width')
    if lmul not in LMULS:raise ValueError('Unsupported LMUL')
    num,den,code=LMULS[lmul]
    if fields*num>8*den:raise ValueError('Reserved segment EMUL times NFIELDS')
    shapes=[sew for sew in (8,16,32,64) if index_sew!=sew
            and sew*den<=64*num
            and (not indexed or sew*den<=8*(index_sew or sew)*num<=64*sew*den)]
    if not shapes:raise ValueError('No legal unequal-width shapes for this release')
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('fault_replay_oracle.c')
    manifest=dict(scope='Unit-stride m1 page-fault replay; Linux vector signal frames; tu/mu',
                  cases=[],operations=['vle.v','vse.v'],restart_tested=True,
                  configurations_per_elf=48,fault_boundaries=[1,3,5],
                  mappings=['PROT_NONE','unmapped'],mask_patterns=['all','alternating','sparse','off'],
                  checks=['fault PC','si_addr/si_code','saved vstart/vl/vtype',
                          'completed prefix before signal','prefix not reexecuted',
                          'complete result and memory guards','completion vstart'],
                  exclusions=['Indexed and segmented replay','Source/index aliases',
                              'Other LMULs','Arbitrary fault boundaries'])
    manifest.update(trace=trace,negative_restart=negative_restart,
                    expected_numerical_failure=negative_restart,indexed=indexed,index_sew=index_sew)
    if indexed:
        manifest.update(scope='Ordered indexed m1 page-fault replay; same-EEW permuted indices; Linux signal frames',
                        operations=['vloxei.v','vsoxei.v'],
                        exclusions=['Segmented and unordered replay','Source/index aliases',
                                    'Other LMULs and independent index EEWs','Arbitrary fault boundaries'])
    if index_sew is not None:
        manifest.update(scope='Ordered indexed m1 page-fault replay; independent index EEW; Linux signal frames',
                        exclusions=['Segmented and unordered replay','Source/index aliases',
                                    'Other LMULs','Arbitrary fault boundaries'])
    manifest['scope']=manifest['scope'].replace('m1',lmul)
    manifest['lmul']=lmul
    manifest['fields']=fields
    if fields>1:
        manifest.update(scope=f'Unit-stride NF{fields} {lmul} segment page-fault replay; Linux signal frames; tu/mu',
                        operations=[f'vlseg{fields}e.v',f'vsseg{fields}e.v'],
                        configurations_per_elf=96,fault_field_splits=[0,fields//2],
                        exclusions=['Indexed and strided segment replay','Source/index aliases',
                                    'Other LMULs','Arbitrary fault boundaries'])
    if strided:
        manifest.update(scope=f'Positive strided NF{fields} {lmul} page-fault replay; Linux signal frames; tu/mu',
                        strided=True, stride_gaps=[1,3],
                        configurations_per_elf=192 if fields>1 else 96,
                        operations=[f'vlsseg{fields}e.v',f'vssseg{fields}e.v'] if fields>1 else ['vlse.v','vsse.v'],
                        exclusions=['Negative and zero strides','Overlapping memory addresses',
                                    'Indexed segment replay','Register aliases',
                                    'Arbitrary fault boundaries','Physical fractional tails'])
        manifest['negative_stride']=negative_stride
        if negative_stride:
            manifest['scope']=manifest['scope'].replace('Positive','Negative')
            manifest['exclusions'][0]='Zero strides'
    if fields>1 and indexed:
        manifest.update(scope=f'Ordered indexed NF{fields} {lmul} segment page-fault replay; Linux signal frames; tu/mu',
                        operations=[f'vloxseg{fields}ei.v',f'vsoxseg{fields}ei.v'],
                        exclusions=['Unordered indexed faults','Register/index aliases',
                                    'Arbitrary fault boundaries','Physical fractional tails'],
                        index_limit_policy='Reduce VL when byte offsets would exceed index EEW; no wrapping addresses')
    if zero_stride:
        manifest.update(scope=f'Zero-stride NF{fields} {lmul} protected-page replay; uniform duplicate store values; tu/mu',
                        zero_stride=True, negative_skip=negative_skip,
                        expected_numerical_failure=negative_skip,
                        configurations_per_elf=32 if fields>1 else 16,
                        fault_boundaries=[0], stride_gaps=[],
                        exclusions=['Completed active prefix poisoning', 'Different duplicate store values',
                                    'Non-idempotent memory access counts', 'Register aliases',
                                    'Arbitrary fault boundaries', 'Physical fractional tails'])
    for sew in shapes:
        vl=replay_elements(sew,indexed,index_sew or sew,fields)
        name=f'rvv_fault_replay'+(f'_segment_nf{fields}' if fields>1 else '')+('_strided' if strided else '')+('_negative_stride' if negative_stride else '')+('_zero_stride' if zero_stride else '')+('_indexed' if indexed else '')+(f'_idx{index_sew}' if index_sew else '')+('_negative_restart' if negative_restart else '')+('_negative_skip' if negative_skip else '')+('_trace' if trace else '')+f'_e{sew}_{lmul}';asm=out/(name+'.S')
        asm.write_text(assembly(sew,indexed,index_sew,lmul,fields,strided));binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d',
            '-nostdlib','-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
            '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
            f'-DSEW={sew}',f'-DTRACE_REPLAY={int(trace)}',
            f'-DNEGATIVE_RESTART={int(negative_restart)}',f'-DINDEXED_REPLAY={int(indexed)}',
            f'-DINDEX_SEW={index_sew or sew}',
            f'-DLMUL_NUM={num}',f'-DLMUL_DEN={den}',f'-DLMUL_CODE={code}',
            f'-DREPLAY_FIELDS={fields}',
            *(['-DSTRIDED_REPLAY=1'] if strided else []),
            *(['-DNEGATIVE_STRIDE=1'] if negative_stride else []),
            *(['-DZERO_STRIDE=1'] if zero_stride else []),
            *(['-DNEGATIVE_SKIP=1'] if negative_skip else []),
            *([f'-DREPLAY_ELEMENTS={vl}'] if fields>1 and indexed else []),
            str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,fields=fields,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_FAULT_REPLAY_PASS',timeout_seconds=180))
        if zero_stride:
            manifest['cases'][-1].update(configurations=32 if fields>1 else 16,
                                        expected_signals=24 if fields>1 else 12)
        if fields>1 and indexed:
            boundaries=[b for b in (1,3,5) if b<vl]
            manifest['cases'][-1].update(vl=vl,index_sew=index_sew or sew,
                fault_boundaries=boundaries,configurations=32*len(boundaries),
                expected_signals=8*sum(sum(any((mask>>i)&1 for i in range(b,vl))
                    for mask in (255,0xaa,0x24,0)) for b in boundaries))
    if fields>1 and indexed:
        counts={c['name']:c['configurations'] for c in manifest['cases']}
        manifest['configuration_counts_by_case']=counts
        manifest['configurations_per_elf']=next(iter(counts.values())) if len(set(counts.values()))==1 else None
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
            input=('\n'.join(entries)+'\n').encode(),stdout=stream,
            cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--trace',action='store_true')
    p.add_argument('--negative-restart',action='store_true')
    p.add_argument('--indexed',action='store_true')
    p.add_argument('--strided',action='store_true')
    p.add_argument('--negative-stride',action='store_true')
    p.add_argument('--zero-stride',action='store_true')
    p.add_argument('--negative-skip',action='store_true')
    p.add_argument('--index-sew',type=int,choices=(8,16,32,64))
    p.add_argument('--lmul',choices=tuple(LMULS),default='m1')
    p.add_argument('--fields',type=int,choices=range(1,9),default=1)
    a=p.parse_args();run(a.out,a.cross,a.trace,a.negative_restart,a.indexed,a.index_sew,a.lmul,a.fields,a.strided,a.negative_stride,a.zero_stride,a.negative_skip)
