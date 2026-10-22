"""Read-only identity Context for formal729; no universal latest-ledger cc requirement."""
import argparse
import json
from pathlib import Path

import prepare_six_policy_population as base
import prepare_six_policy_population_v2 as v2

frozen,require=base.frozen,base.require
SCRIPT=Path(__file__).resolve()
TEST=SCRIPT.with_name('test_prepare_six_policy_population_729.py')
ADMISSION=frozen.OUT/'gap107-offline-admitted-729-parent-20261006-01'
ADMISSION_SEAL='e5bd9eeb19acc452d25db12f342c3c12532614a0c773c43355a33e34d8dd1912'
WORKSPACE=SCRIPT.parents[2]/'install/riscv-llvm/bin'
CANONICAL=Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin')
# Exact729 ledger entries: three links and two ordinary binaries.
LLVM={
    'clang':('clang-22','clang-22','c9e4459570b10dc31a2e9ed6006ae0484580ae19b2b77e7451687d8f52705795'),
    'ld.lld':('lld','lld','8bfa4d7d50f6d533264ab93df55e372a7247e580f0915257547bf4f71cdead83'),
    'llvm-objdump':(None,'llvm-objdump','1e36619e39e9ee8033a1713571191c1e525ebf9d40452ba50ea2d081ad598c27'),
    'llvm-readobj':(None,'llvm-readobj','3f554cd6c8bde87e4f16476283f3bee3f9514825eac82f062eded8efb927de43'),
    'llvm-readelf':('llvm-readobj','llvm-readobj','3f554cd6c8bde87e4f16476283f3bee3f9514825eac82f062eded8efb927de43'),
}
ALIASES={str(WORKSPACE/n):spec for n,spec in LLVM.items()}
LINKS=dict(frozen.INHERITED_TOOL_LINKS,**{p:s[0] for p,s in ALIASES.items() if s[0] is not None})
SCHEMAS={
    729:'GAP107_HISTORICAL729_SOFTWARE_NATIVE_ADMISSION_V1',
    728:'FENCE_PADDING_HISTORICAL728_SCOPED_SCALAR_ADMISSION_V1',
    727:'GAP106_HISTORICAL727_SOFTWARE_NATIVE_ADMISSION_V1',
    726:'VNCLIPU_HISTORICAL726_ADMISSION_V1',
    725:'GAP105_HISTORICAL725_SOFTWARE_NATIVE_ADMISSION_V1',
    724:'AKV_LIFECYCLE_HISTORICAL724_ADMISSION_V1',
    723:'R1_CACHED_HISTORICAL723_ADMISSION_V1',
}
R1_PREFLIGHT=frozen.OUT/'narrow-reject-r1-cached-preflight-719-20261006-01'


def bound(path,expected,pins):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),'Aliased/missing sealed identity evidence')
    data=frozen.load_sealed(path,expected)
    require(str(path) not in pins or pins[str(path)]==expected,'Identity evidence pin conflict')
    pins[str(path)]=expected
    return data


def sealed_ledger(admission,seal,pins):
    admission=Path(admission)
    require(admission.parent==frozen.OUT and admission.resolve()==admission,'Unsafe admission ancestry path')
    manifest=bound(admission/'admission-manifest.json',seal,pins)
    require(manifest['output']==str(admission),'Ancestor output ownership differs')
    ledger_path=admission/'evidence-pins.json'
    ledger=bound(ledger_path,manifest['output_pins'][str(ledger_path)],pins)
    require(isinstance(ledger,dict),'Identity ledger is not a mapping')
    return manifest,ledger


def cc_ancestry(admission,seal):
    """Verify seven linked formal admissions, then the actual sealed R1 host provenance."""
    pins={};chain=[];child_inputs=None;cc_nodes=[]
    current=Path(admission);expected=seal;seen=set()
    for population in range(729,722,-1):
        require(current not in seen,'Admission ancestry cycle');seen.add(current)
        manifest,ledger=sealed_ledger(current,expected,pins)
        require(manifest['schema']==SCHEMAS[population],'Unexpected ancestry schema/population')
        status_path=current/'status.json'
        status=bound(status_path,manifest['output_pins'][str(status_path)],pins)
        require(status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and
                type(status['aggregate_passed']) is int and status['aggregate_passed']==population,
                'Non-PASS ancestor or population relabel')
        input_path=current/'combined-inputs.txt'
        input_sha=manifest['output_pins'][str(input_path)]
        require(input_path.is_file() and not input_path.is_symlink() and frozen.sha(input_path)==input_sha,
                'Ancestor population input drift')
        pins[str(input_path)]=input_sha;inputs=input_path.read_text().splitlines()
        require(len(inputs)==population+1 and len(set(inputs))==len(inputs) and
                (child_inputs is None or child_inputs[:-1]==inputs),'Exact ancestor prefix lost')
        child_inputs=inputs
        if v2.CC in ledger:
            require(ledger[v2.CC]==v2.CC_SHA,'Conflicting historical cc pin')
            cc_nodes.append(str(current))
        chain.append(dict(admission=str(current),population=population,manifest_sha256=expected,
                          ledger_sha256=pins[str(current/'evidence-pins.json')]))
        if population==723:break
        current=Path(manifest['baseline']);expected=manifest['baseline_seal']
    require(len(chain)==7 and v2.CC in ledger,'R1 ancestor host identity missing')
    origin={}
    for name in ('input-pins.json','preflight-manifest.json','host-command.json'):
        path=R1_PREFLIGHT/name
        require(str(path) in ledger,'R1 source document absent from sealed ancestor ledger')
        origin[name]=bound(path,ledger[str(path)],pins)
    for table in (origin['input-pins.json'],origin['preflight-manifest.json']['pins']):
        require(table.get(v2.CC)==table.get('/usr/bin/gcc')==v2.CC_SHA,'R1 compiler bytes differ')
    preflight=origin['preflight-manifest.json']
    require(preflight['case']=='vnarrow_reject_r1_matrix_cached' and
            preflight['status']=='R1_CACHED_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS' and
            all(preflight['pins'].get(str(R1_PREFLIGHT/n))==pins[str(R1_PREFLIGHT/n)]
                for n in ('input-pins.json','host-command.json')),'R1 preflight document binding differs')
    command=origin['host-command.json']
    require(isinstance(command,list) and command==[
        v2.CC,'-std=c11','-Wall','-Wextra','-Werror',
        str(SCRIPT.parents[2]/'verification/tests/narrow_reject_r1_host.c'),
        '-o',str(R1_PREFLIGHT/'host-reference')],'R1 sealed host command differs')
    identity=v2.tool_link_identity(v2.CC)
    require(ledger.get('/usr/bin/gcc')==v2.CC_SHA,'Ancestor resolved gcc pin missing')
    pins[v2.CC]=pins['/usr/bin/gcc']=v2.CC_SHA
    return dict(chain=chain,cc_ledger_nodes=cc_nodes,origin=str(R1_PREFLIGHT),
        identity=identity,pins=pins,role='Historical R1 host producer only; never DVE launch tool',
        top_ledger_cc_required=False,history_identity_fabricated=False)


def llvm_identity(path):
    path=Path(path).absolute()
    require(str(path) in ALIASES,'Unknown workspace LLVM path')
    link,resolved_name,expected=ALIASES[str(path)]
    if link is None:require(not path.is_symlink(),'Ordinary LLVM binary became a link')
    else:require(path.is_symlink() and str(path.readlink())==link,'LLVM literal link target differs')
    resolved=path.resolve(strict=True)
    require(resolved==CANONICAL/resolved_name and resolved.is_file() and not resolved.is_symlink()
            and frozen.sha(resolved)==expected,'LLVM canonical endpoint/bytes differ')
    return dict(link_target=link,resolved=str(resolved),sha256=expected)


def tool_link_identity(path):
    key=str(Path(path).absolute())
    if key in ALIASES:return llvm_identity(path)
    if key==v2.CC:return v2.tool_link_identity(path)
    return frozen.tool_link_identity(path)


class Context(base.Context):
    def __init__(self,admission,seal,population):
        super().__init__(admission,seal,population)
        require(self.admission==ADMISSION and seal==ADMISSION_SEAL and
                type(population) is int and population==729,'Only explicitly sealed formal729')
        self._ledger=None;self._cc_proof=None

    def ledger(self):
        if self._ledger is None:
            _,self._ledger=sealed_ledger(self.admission,self.seal,{})
        return self._ledger

    def cc_proof(self):
        if self._cc_proof is None:self._cc_proof=cc_ancestry(self.admission,self.seal)
        return self._cc_proof

    def pin(self,pins,path,expected=None):
        path=Path(path).absolute();key=str(path)
        if key in ALIASES:
            sealed=self.ledger().get(key)
            require(sealed==ALIASES[key][2] and expected in (None,sealed),'LLVM not pinned by actual729 ledger')
            identity=llvm_identity(path)
        elif key==v2.CC:
            require(expected==v2.CC_SHA,'cc requires actual sealed ancestor expected hash')
            identity=self.cc_proof()['identity'];sealed=v2.CC_SHA
        else:return super().pin(pins,path,expected)
        require(pins.get(key,sealed)==sealed,'Tool identity pin conflict')
        pins[key]=sealed;frozen.four.pin(pins,identity['resolved'],sealed)
        return path

    def source_binding(self,pins):
        result=super().source_binding(pins)
        # All original admission-input checks remain inherited; this adds precise producer identity.
        self._ledger=None
        aliases={}
        for key in ALIASES:
            self.pin(pins,key,self.ledger().get(key));aliases[key]=llvm_identity(key)
        proof=cc_ancestry(self.admission,self.seal);self._cc_proof=proof
        for path,sha in proof['pins'].items():self.pin(pins,path,sha)
        for path in (SCRIPT,TEST,Path(base.__file__).resolve(),Path(v2.__file__).resolve()):self.pin(pins,path)
        result.update(workspace_llvm729=aliases,historical_r1_cc=proof,
            tool_scope='DVE historical aggregation; no compilation or simulation',
            current_admission_cc_present=v2.CC in self.ledger())
        return result

    def namespace(self):
        return dict(super().namespace(),INHERITED_TOOL_LINKS=LINKS,tool_link_identity=tool_link_identity)


def read_config(output,seal):
    config=frozen.load_sealed(output/'config.json',seal)
    context=Context(config['admitted_base'],config['admission_manifest_sha256'],config['population'])
    context.check_config(config,output)
    return context,config


prepare=base.prepare


def main():
    # Identity diagnostics only until the parent reviews runtime consumer wiring.
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('audit-identity',))
    a=parser.parse_args()
    context=Context(ADMISSION,ADMISSION_SEAL,729)
    ledger=context.ledger()
    aliases={p:llvm_identity(p) for p in ALIASES}
    require(all(ledger.get(p)==s['sha256'] for p,s in aliases.items()),'Actual729 LLVM ledger differs')
    proof=context.cc_proof()
    print(json.dumps(dict(status='IDENTITY_ONLY_NOT_PREPARED_NOT_APPLICATION',llvm=aliases,
        current_cc_present=v2.CC in ledger,current_gcc=ledger.get('/usr/bin/gcc'),cc_proof=proof),indent=2))


if __name__=='__main__':main()
