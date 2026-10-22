"""Explicit historical build/source binding; frozen v1 native/readback audit unchanged."""
import argparse
import json
from pathlib import Path
import sys

import qualify_gap105_native as frozen

life,runner,require = frozen.life,frozen.runner,frozen.require
BUILD = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BUILD_SEAL = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SNAPSHOT = life.OUT/'old-image-source-evidence-20261006-01'
SNAPSHOT_SEAL = 'f75d9b459600c077682e648c73c98fa39aa6bbf69c534308c7eea2ec8d3a565c'
FROZEN_SEAL = '077b9761e6ee811f81cea4566d390ad3e0611ea4760958fff0edf7499be82194'
TEST_SEALS = {
    'test_qualify_gap105_native.py':'2a39ead4378a7677b67bec3e2faf40069a3b9bf7f44fb86aa5c5e5c0b8b59cfd',
    'test_qualify_gap105_native_v2.py':'877067ee3e39274d6fde1b4869f6064eddafcec96d299071deb64da02cc9d1ef'}


def bind_sources(pins):
    # Add a new expected pin explicitly; never replace an existing expectation.
    pins = life.merge_pins(pins,{str(BUILD):BUILD_SEAL,str(SNAPSHOT/'manifest.json'):SNAPSHOT_SEAL})
    build = life.read_bound(BUILD,BUILD_SEAL)
    snapshot = life.read_bound(SNAPSHOT/'manifest.json',SNAPSHOT_SEAL)
    require(snapshot['build_pins']==str(BUILD.relative_to(life.ROOT)) and
            snapshot['processor_rtl_modified'] is False,'Snapshot/build identity differs')
    entry = [r for r in snapshot['files'] if r['original_relative_path']=='hardware/src/ara_dispatcher.sv']
    require(len(entry)==1 and entry[0]['snapshot_file']=='ara_dispatcher.sv' and
            entry[0]['sha256']==build[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]==frozen.DISPATCHER_SHA,
            'Exact historical dispatcher/snapshot binding differs')
    dispatcher = SNAPSHOT/'ara_dispatcher.sv'
    pins = life.merge_pins(pins,{str(dispatcher):frozen.DISPATCHER_SHA})
    sources = [life.ROOT/'hardware/src/vlsu/qbs/qbs_commit.sv',
               life.ROOT/'hardware/tb/ara_commit_monitor.sv']
    for path in sources: pins = life.merge_pins(pins,{str(path):build[str(path)]})
    life.check(pins)
    require("ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));" in dispatcher.read_text(),
            'Historical internal VL formula differs')
    commit = sources[0].read_text()
    require("? {{4{high_active}}, {4{low_active}}} : 8'hff;" in commit and
            "element < unsigned'(n_q)" in commit,'Historical active-only wide mask differs')
    return pins


def prepare(run, reviewed_seal):
    run = Path(run).absolute()
    require(run.parent==life.OUT and run.resolve()==run,'Foreign/aliased run')
    record = run.with_name(run.name+'.prepared.json')
    config = life.read_bound(record,reviewed_seal)
    require(config['command']==runner.command(run) and config['timeout_s']==1200 and
            config['preflight']==life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL),
            'Reviewed run contract differs')
    runner.validate(config['preflight'])
    pins = life.merge_pins({},config['pins'])
    pins = life.merge_pins(pins,{str(record):reviewed_seal})
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66 and
            plan['image'].get(str(life.IMAGE))==runner.IMAGE_SEAL,'Exact66-file image differs')
    pins = life.merge_pins(pins,plan['image'])
    pins = life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL})
    pins = bind_sources(pins)
    pins = life.merge_pins(pins,{str(Path(frozen.__file__).resolve()):FROZEN_SEAL})
    for name,seal in TEST_SEALS.items():
        pins = life.merge_pins(pins,{str(Path(__file__).with_name(name)):seal})
    dependencies = [Path(__file__).resolve(),Path(__file__).with_name('test_qualify_gap105_native_successor.py')]
    dependencies += [Path(sys.modules[f.__module__].__file__).resolve() for f in
                     (frozen.validate_trace,frozen.check_contract_log,frozen._architectural_bytes,
                      frozen._scalar_memory_access)]
    for path in dependencies: pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    symbols,data,sites = frozen.elf_view(); native = frozen.independent_native()
    for phase in (0,1): frozen.regions(phase,symbols,data,native)
    require(native[2]==config['preflight']['expected_bits_per_command'],'Independent Python/C native oracle differs')
    life.check(pins)
    return dict(status='GAP105_NATIVE_QUALIFIER_V2_PREPARED_NOT_EXECUTED',run=str(run),
        run_prepared_seal=reviewed_seal,pins=pins,native_expected_bits=native[2],
        historical_build_manifest=str(BUILD),historical_build_seal=BUILD_SEAL,
        frozen_native_qualifier_sha256=FROZEN_SEAL,
        scope='Complete software/native only; no full scalar ISA claim',coverage_admitted=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','collect'))
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--prepared-seal',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--config-seal')
    args = parser.parse_args(argv)
    require((args.mode=='collect')==bool(args.config_seal),'Collect alone requires reviewed qualifier seal')
    output = args.output.absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh independent sidecar required')
    config = prepare(args.run,args.prepared_seal)
    path = output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(path,config)
        print(json.dumps(dict(config=str(path),seal=life.digest(path),pins=len(config['pins'])))); return
    require(life.read_bound(path,args.config_seal)==config,'Reviewed qualifier config differs')
    run = Path(config['run']); pins = life.merge_pins(config['pins'],{str(path):args.config_seal})
    # No trace/VDB inspection until the sealed launcher reports a clean terminal.
    status_path = run/'simulation-status.json'
    status_hash = life.digest(status_path)
    status = life.read_bound(status_path,status_hash)
    require(status.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and status.get('returncode')==0 and
            status.get('coverage_admitted') is False,'Not a clean terminal run')
    pins = life.merge_pins(pins,{str(status_path):status_hash})
    required = [run/n for n in ('manifest.json','started.json','console.log','run.vcs.log',
                               'commit_trace.csv','vector_trace.csv')]
    required += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require(any(p.name=='cond.verilog.data.xml' for p in required),'Missing raw condition bitmap')
    for p in required: pins = life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    reviewed = life.read_bound(run.with_name(run.name+'.prepared.json'),args.prepared_seal)
    require(life.read_bound(run/'manifest.json',pins[str(run/'manifest.json')])==reviewed,'Runtime manifest differs')
    output.mkdir(); life.save(output/'evidence-pins.json',pins)
    try:
        symbols,data,sites = frozen.elf_view()
        audit = frozen.runtime(run,symbols,data,sites,frozen.independent_native())
        life.check(pins)
        life.save(output/'runtime-audit.json',audit)
        life.save(output/'qualification.json',dict(status='GAP105_SOFTWARE_NATIVE_V2_QUALIFIED_NOT_ADMITTED',
            audit_sha256=life.digest(output/'runtime-audit.json'),pins_sha256=life.digest(output/'evidence-pins.json'),
            full_scalar_isa_verified=False,coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False))
    except Exception as error:
        life.save(output/'qualification.json',dict(status='GAP105_NATIVE_QUALIFIER_V2_REJECTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'))))


if __name__=='__main__': main()
