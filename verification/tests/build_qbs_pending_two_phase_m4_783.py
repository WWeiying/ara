"""Legal M4 ROW successor. Full descriptor audit precedes host build; no EDA."""
import argparse
import ast
from collections import Counter
import inspect
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import build_qbs_pending_two_phase783 as frozen
import prove_qbs_hit_congruence780 as mapping

common,ROOT=frozen.common,frozen.ROOT
APP=ROOT/'apps/qbs_pending_two_phase_m4_783'
WORDS=(0x06b5045b,0x06b5045b)
FROZEN_SHA='86e7a772ed52f395513e4d1f5095d994fe9d88abd2471f1e8a97ec759fa17fd9'
PROBE=frozen.PROBE
MUTATIONS=frozen.MUTATIONS


def fixture():
    first,second=frozen.fixture();w,a,old_gold,values=second
    activation=bytearray([0x5a]*len(a));activation[76:76+2336]=a[76:76+2336]
    image=bytearray(frozen.old.seed_bytes());image[1024:1536]=bytes(512)
    for ctx in range(4):image[1024+128*ctx:1024+128*ctx+32]=old_gold[1024+128*ctx:1024+128*ctx+32]
    return [first,(w,bytes(activation),bytes(image),values[:32])]


def header():
    function=FunctionType(frozen.header.__code__,dict(vars(frozen),fixture=fixture))
    text=function()
    old='{weight1,activation1,weight_expected1,activation_expected1,gold1,8,3360,4672,3520,4864,76}'
    common.require(text.count(old)==1,'Exact M4 header transformation')
    return text.replace(old,'{weight1,activation1,weight_expected1,activation_expected1,gold1,4,3360,2336,3520,4864,76}')


def static():
    common.require(common.sha(Path(frozen.__file__))==FROZEN_SHA,'Frozen rejected builder unchanged')
    paths=frozen.source_contract()
    decoder=(ROOT/'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv').read_text()
    pkg=(ROOT/'hardware/include/qbs_pkg.sv').read_text()
    errors=['DESCRIPTOR_ALIGNMENT','DESCRIPTOR_VERSION','DESCRIPTOR_RESERVED','WEIGHT_PROFILE',
        'ACTIVATION_PROFILE','WEIGHT_LAYOUT','ACTIVATION_LAYOUT','M_RANGE','N_RANGE','K_RANGE',
        'CONTEXT_ENCODING','CONTEXT_UNSUPPORTED','VD_ALIGNMENT','WEIGHT_ALIGNMENT',
        'ACTIVATION_ALIGNMENT','WEIGHT_RANGE_OVERFLOW','ACTIVATION_RANGE_OVERFLOW']
    common.require([line.strip().split('QBS_VALIDATION_')[1].split(';')[0] for line in decoder.splitlines()
        if 'error_o = QBS_VALIDATION_' in line and 'QBS_VALIDATION_OK' not in line]==errors,'Entire ordered RTL validation chain')
    for token in ('QbsMaxM = 8','QbsMaxN = 32','QbsMaxResults = 128','QbsWideMMin = 5',
        'QbsWideMMaxN = 16','QbsMaxKBlocks = 256','QbsActivationContextCount = 1',
        'QbsActivationContextMaxM = 1','QbsActivationContextMaxKBlocks = 16'):
        common.require(token in pkg,'Complete caps '+token)
    gates=dict(DESCRIPTOR_ALIGNMENT='64-aligned object; required8-byte alignment',
        DESCRIPTOR_VERSION='Version1',DESCRIPTOR_RESERVED='Bits63:47 zero',
        WEIGHT_PROFILE='Q2_K and Q6_K known block sizes84/210',
        ACTIVATION_PROFILE='Q8_K known292B, compatible with both weight profiles',
        WEIGHT_LAYOUT='ROW valid',ACTIVATION_LAYOUT='ROW valid because M4<5; M8/ROW rejected',
        M_RANGE='M4 within1..8',N_RANGE='N8 <= min(VLEN1024/32,32); M*N32 <=128',
        K_RANGE='K2 in1..256',CONTEXT_ENCODING='DIRECT context_id/generation both0',
        CONTEXT_UNSUPPORTED='Not selected for DIRECT; cached modes not claimed',
        VD_ALIGNMENT='vd8 group4-aligned,vd+4=12 <=32',WEIGHT_ALIGNMENT='Base+74 even',
        ACTIVATION_ALIGNMENT='Base+64/Base+76 both4-aligned',
        WEIGHT_RANGE_OVERFLOW='1344/3360 bytes fit unsigned64 and guarded L2',
        ACTIVATION_RANGE_OVERFLOW='2336 bytes fit unsigned64 and guarded L2')
    # Concrete descriptors are legal; only bank/pending arbitration is relaxed below.
    keys=set()
    for global_row in range(8):
        for k in range(2):
            addr=0x8002000a+(2*global_row+k)*210
            for start,first,take in mapping.even.compact_range(addr,210):
                for b in range(take):
                    plane,dest=mapping.m.weight_location(3,start+b)
                    for bank in (0,1):keys.add((bank,('weight',global_row%4,plane,dest%(20 if plane==2 else 16),b)))
    for ctx in range(4):
        for k in range(2):
            addr=0x8001000c+(2*ctx+k)*292
            for start,first,take in mapping.even.compact_range(addr,292):
                for b in range(take):
                    plane,dest=mapping.m.activation_location(start+b,4,256)
                    keys.add((0,('activation',ctx,plane,dest%32 if plane==0 else dest,b)))
    batch=ROOT/'verification/out/qbs-main-side-exact-batch780-agent-20261008-01.json'
    gain=ROOT/'verification/out/qbs-k2-row-pending-cycle782-agent-20261008-01/payload-gain.json'
    g=common.read(gain);common.require(common.sha(gain)=='d6ef72f28f975e8bc6805d7c5b4f53396188eaf443d11ab363a8cfc09c2a44ed','Measured after782 sample')
    counts=Counter();coordinates={s:[] for s in g['combined_rows']}
    for group in common.read(batch)['HOLD_groups']:
        raw=int(g['combined_rows'][group['scope']]['bits'],16)
        for bit,cs in group['bit_missing_coordinates'].items():
            key,slot,side=mapping.m.identity(group['signal'],int(bit))
            if (group['bank'],key) not in keys:continue
            missing=[c for c in cs if not raw>>(66339-c)&1]
            coordinates[group['scope']].extend(missing)
            counts[str((group['bank'],key[0],slot,side))]+=len(missing)
    common.require(all(len(cs)==len(set(cs)) for cs in coordinates.values()),'Unique revised intersection')
    return dict(status='LEGAL_M4_ROW_SOURCE_BOUND_STATIC_MAPPING_NOT_RUNTIME_GAIN',
        validation_order=errors,validation_witnesses=gates,phases=[dict(m=4,n=8,k=2,profile='Q2_K',ap=0,wp=10),
            dict(m=4,n=8,k=2,profile='Q6_K',ap=12,wp=10)],vd=8,VLEN=1024,VL=8,SEW=32,
        weight_layout='ROW',activation_layout='ROW',access='DIRECT',
        explicit_retraction='Previous4120 bound came from an illegal M8/ROW descriptor; withdrawn, not a legal testcase gain bound.',
        legal_mapping_upper_bound=sum(map(len,coordinates.values())),remaining_coordinates=coordinates,by_group=dict(counts),
        boundary='Concrete legal ROW beats; weight bank ownership and selected-word/pending arbitration relaxed. Activation onlybank0; no bank1 activation gain assumed. Not measured gain.',
        pins={str(p):common.sha(p) for p in [*paths,Path(mapping.__file__),Path(mapping.m.__file__),
            Path(mapping.even.__file__),batch,gain,Path(frozen.__file__)]},EDA_launched=False)


def build(out):
    proof=static();common.require(not out.exists(),'Fresh legal successor')
    # Exact small adaptations of the frozen build; no duplication of toolchain/link/UART/fit checks.
    tree=ast.parse(inspect.getsource(frozen.build));changed=Counter()
    class Adapt(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value=='test_qbs_pending_two_phase783.py':
                node.value='test_qbs_pending_two_phase_m4_783.py';changed['test']+=1
            elif node.value=='\nMATRIX_EXEC 0, 8, 0x06b5045b\nMATRIX_EXEC 1, 8, 0x0eb5045b\n':
                node.value='\nMATRIX_EXEC 0, 8, 0x06b5045b\nMATRIX_EXEC 1, 8, 0x06b5045b\n';changed['code']+=1
            return node
        def visit_Call(self,node):
            self.generic_visit(node)
            if isinstance(node.func,ast.Name) and node.func.id=='dict' and any(k.arg=='profile' and isinstance(k.value,ast.Constant) and k.value.value=='Q6_K' for k in node.keywords):
                for k in node.keywords:
                    if k.arg=='m':common.require(k.value.value==8,'Old M8');k.value=ast.Constant(4);changed['m']+=1
                    if k.arg=='active_outputs':common.require(k.value.value==64,'Old outputs');k.value=ast.Constant(32);changed['outputs']+=1
            return node
    tree=Adapt().visit(tree);ast.fix_missing_locations(tree)
    common.require(changed==dict(test=1,code=1,m=1,outputs=1),'Four exact build adaptations')
    class BoundBuild(common.Build):
        def bind_sources(self,paths):
            return super().bind_sources([*paths,Path(frozen.__file__),*map(Path,proof['pins'])])
    def unpublished_save(path,value):
        if path==out/'preflight-manifest.json':path=out/'inherited-build-contract.json'
        return common.save(path,value)
    def unpublished_sha(path):
        if Path(path)==out/'preflight-manifest.json':path=out/'inherited-build-contract.json'
        return common.sha(path)
    ns=dict(vars(frozen),__file__=__file__,APP=APP,WORDS=WORDS,fixture=fixture,header=header,
        common=SimpleNamespace(**dict(vars(common),Build=BoundBuild,save=unpublished_save,sha=unpublished_sha)))
    exec(compile(tree,str(Path(frozen.__file__))+'<legal-M4>','exec'),ns)
    result=ns['build'](out)
    manifest=out/'preflight-manifest.json';record=common.read(out/'inherited-build-contract.json')
    record.update(status='LEGAL_TWO_PHASE_M4_HOST_INTEGER_GOLD_READY_NOT_DUT_PASS',
        candidate_mapping_upper_bound=proof['legal_mapping_upper_bound'],
        static_source_validation=proof,host_negative_tests=19)
    host=subprocess_run(out/'host')
    common.require(host.returncode==0 and b'untouched=1' in host.stdout,'Illegal M8/ROW negative')
    (out/'negative-invalid-m8-row.log').write_bytes(host.stdout+host.stderr)
    record['output_pins']=common.pins(p for p in out.iterdir() if p.is_file() and p!=manifest)
    common.save(manifest,record)
    return dict(manifest=str(manifest),seal=common.sha(manifest),elf_sha256=result['elf_sha256'],
        legal_mapping_upper_bound=proof['legal_mapping_upper_bound'])


def subprocess_run(host):
    import subprocess
    return subprocess.run([host,'invalid-m8-row'],capture_output=True,timeout=10)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--static-only',action='store_true')
    args=p.parse_args();out=args.output.resolve()
    if args.static_only:
        proof=static();common.save(out,proof);print(json.dumps(dict(path=str(out),seal=common.sha(out),bound=proof['legal_mapping_upper_bound'])))
    else:print(json.dumps(build(out)),flush=True)
