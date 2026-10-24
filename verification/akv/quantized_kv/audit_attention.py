"""Replay a completed private-schedule inquiry before downstream execution."""
from pathlib import Path

from run_attention import s, ROOT, checked_prerequisite
from check_attention import check_log


def checked_attention(path):
    status,result=s.read_json(path/'status.json'),s.read_json(path/'result.json')
    s.require(status.get('state')==result.get('state')=='PASS' and
        status.get('child_pid') is None and result.get('post_pins_match') is True and
        result.get('simulator_exit_code')==0 and result.get('independent_protocol_checked') is True,
        'Require terminal numerically/protocol checked complete Attention')
    build=Path(status['build']); report=s.read_json(build/'build.json')
    s.require(report['state']=='BUILT_NOT_EXECUTED' and report['trials']==4 and
        report['expected_commands']==16 and report['outputs_per_trial']==768 and
        status['elf']==report['elf'] and status['simv']==report['simv'] and
        result['elf_sha256']==report['elf_sha256']==s.digest(Path(report['elf'])) and
        s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Prior build/ELF drift')
    required=s.read_json(build/'source-pins.json'); s.merge_pins(required,report['artifact_sha256'])
    s.require(s.digest(path/'source-pins.json')==result['source_pins_sha256'],'Prior receipt drift')
    pins=s.read_json(path/'source-pins.json')
    s.require(all(pins.get(p)==h for p,h in required.items()),'Prior omitted build inputs')
    image,accepted=s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image==report['accepted_image_pins'],'Prior image drift')
    s.merge_pins(pins,accepted); s.merge_pins(pins,result['evidence_sha256']); s.verify_pins(pins)
    prior_image,prior_pins=checked_prerequisite(Path(status['prerequisite']))
    s.require(image==prior_image and all(pins.get(p)==h for p,h in prior_pins.items()),
              'Prior QK evidence/image mismatch')
    data=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/(
        'capture-k-'+report['kind']+'-v-q8_0')/'decode/block'
    log,trace=path/'work/run.vcs.log',path/'work/vector_trace.csv'
    parsed=check_log(log.read_text(),int(report['kind']=='q4_0'),
        (data/'kqv_out-0.bin').read_bytes(),(ROOT/'hardware/src/vlsu/vlsu.sv').read_text())
    s.require(all(result.get(k)==v for k,v in parsed.items() if k not in
        ('state','independent_protocol_checked')),'Prior raw numerical/work/performance replay differs')
    s.check_result(path/'work/uvm_result.json',report['elf_sha256'],image)
    uvm=s.read_json(path/'work/uvm_result.json')
    s.require(uvm['log_sha256']==s.digest(log) and uvm['vector_trace_sha256']==s.digest(trace),
              'Prior protocol input mismatch')
    s.merge_pins(pins,s.hashes([path/'status.json',path/'result.json']))
    return report,image,pins,parsed
