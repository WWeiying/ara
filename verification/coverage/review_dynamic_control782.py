"""Read-only exact782 control inventory; no simulator or coverage exclusion."""
import json
from pathlib import Path

import targeted_toggle_evidence_v2 as t
from rank_cva6_scalar_data767 import typed_nodes

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BASE = OUT/'dtlb-permissions-offline-admitted782-agent-20261008-01'
SEAL = 'a52004d8882b5101d823d6dd647b7fb20c7c25a544abc96d15cb6f85d36d50b8'
CACHE = OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'


def collect():
    pins = {}
    def bound(path, sha):
        t.require(t.digest(path)==sha, 'Pin drift: '+str(path))
        pins[str(path)] = sha
        return path.read_bytes()
    manifest = json.loads(bound(BASE/'admission-manifest.json', SEAL))
    t.require(manifest['coverage_admitted'] is True, 'Formal admission')
    ledger_path = BASE/'combined-inputs.txt'
    ledger = bound(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
    t.require(len(ledger)==len(set(ledger))==783, 'Exact782 ledger')
    cache = json.loads(bound(CACHE, CACHE_SHA))
    old = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(ledger[:742]==bound(old,cache['input_pins'][str(old)]).decode().splitlines(), 'Exact741 prefix')
    scopes = [s for s in cache['instances'] if s.startswith('ara_tb.dut.i_ara_soc.i_system.') and
              s.endswith(('.i_valu','.i_dispatcher','.i_addrgen','.i_vldu','.i_vstu',
                          '.controller_i','.csr_regfile_i','.id_stage_i'))]
    t.require(len(scopes)==11, 'Exact eleven scopes')
    union = {s:{k:cache['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    for i,vdb in enumerate(ledger[742:]):
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files)==1, 'Unique native sample')
        path = files[0]; sha = manifest['input_pins'][str(path)]
        bound(path, sha)
        rows, actual = t.rows(path, scopes)
        t.require(actual==sha, 'Read pin')
        union = t.union(union,rows)
        if i%10==0: print('STATIC_SUFFIX',i+1,flush=True)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/rel for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    for path in paths: bound(path,manifest['input_pins'][str(path)])
    checks,defs = t.definitions(*(t.xml(p) for p in paths),scopes)
    ranking = []
    for scope in scopes:
        t.require(union[scope]['checksum']==checks[scope], 'Compiled checksum')
        nodes,arrays = typed_nodes(defs[scope]['shape'],union[scope])
        ranking.append(dict(scope=scope,compiled_module=defs[scope]['module'],row=union[scope],
                            objects=sorted(nodes,key=lambda n:-n['missing_slots']),arrays_held=arrays))
    pins[str(Path(__file__).resolve())] = t.digest(__file__)
    return dict(population=782,baseline_manifest=str(BASE/'admission-manifest.json'),pins=pins,
                scopes=ranking,coordinate_semantics='Serialized pair slots; direction order not inferred',
                exclusions_proposed=False,EDA_started=False,official_percentage=False)


if __name__=='__main__':
    output = OUT/'dynamic-control782-static-agent-20261008-01.json'
    t.require(not output.exists(), 'Fresh output')
    result = collect()
    with output.open('x') as stream: json.dump(result,stream,indent=2);stream.write('\n')
    print('STATIC782',t.digest(output))
