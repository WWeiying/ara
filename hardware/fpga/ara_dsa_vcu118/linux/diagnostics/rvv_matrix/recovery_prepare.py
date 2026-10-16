"""Preserve a confirmed stall and preload immutable pending tests into a boot overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import struct
from audit import audit
import guest_batch


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_coverage(manifest):
    """Permit an explicitly VLEN1024-only release, without claiming VLEN512."""
    vlens = set(manifest.get('reference_vlens', []))
    required = manifest.get('required_vlen_bits')
    if not manifest.get('reference_passed'):
        raise ValueError('Release lacks passing reference')
    if required is None and vlens == {512, 1024}:
        return vlens
    if required == 1024 and vlens in ({1024}, {512, 1024}):
        return {1024}
    raise ValueError('Release lacks both references or explicit VLEN1024 requirement')


def remaining(manifest,report,retry_observation_gaps=False):
    audit(manifest,report)
    if report['inputs']['cases']!=manifest['cases'] or report['inputs']['archive_sha256']!=manifest['archive_sha256']:
        raise ValueError('Scene and release differ')
    if report['state']!='scene_preserved_incomplete' or not report.get('progress_diagnosis',{}).get('stalled'):
        raise ValueError('No confirmed stall scene')
    prior=report['results']
    if not prior or prior[-1]['status']!='stalled':raise ValueError('Last attempt is not a stall')
    if [x['name'] for x in prior]!=[x['name'] for x in manifest['cases'][:len(prior)]]:
        raise ValueError('Attempts are not a contiguous prefix')
    gaps=[x for x in prior if x['status']=='incomplete']
    if gaps and retry_observation_gaps:
        reasons={'Observer disconnected before complete result',
                 'UART observation gap; no correctness result inferred'}
        if (report.get('observation_reattached') is not True or
                report.get('serial_writes') is not False or
                report['progress_diagnosis'].get('name')!=prior[-1]['name'] or
                any(x.get('error') not in reasons for x in gaps)):
            raise ValueError('Unverified observation gaps')
    allowed=('passed','failed','stalled','incomplete') if retry_observation_gaps else ('passed','failed','stalled')
    if any(x['status'] not in allowed for x in prior):
        raise ValueError('Incomplete preceding result')
    a,b=report['progress_diagnosis']['snapshots']
    if b['core']['cycles']-a['core']['cycles']<=a['identity']['frequency_hz']*2:
        raise ValueError('Insufficient live-cycle evidence')
    if any(a['core'][k]!=b['core'][k] for k in ('retired','trap_count','last_pc','head_pc')):
        raise ValueError('Core still progressing')
    if any(s['watchdog_snapshot'] or s['live']['flags'] for s in (a,b)):
        raise ValueError('Core state is not an unhalted live stall')
    gap_names={x['name'] for x in gaps} if retry_observation_gaps else set()
    return [c for c in manifest['cases'][:len(prior)] if c['name'] in gap_names]+manifest['cases'][len(prior):]


def patch_embedded_dtb(firmware, original, replacement):
    if len(original) != len(replacement) or firmware.count(original) != 1:
        raise ValueError('Expected one equal-sized embedded DTB')
    if firmware[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', firmware)
    if header[2] != 243:
        raise ValueError('Expected RISC-V firmware')
    offset = firmware.index(original)
    data_section = False
    for i in range(header[12]):
        section = struct.unpack_from('<IIQQQQIIQQ', firmware, header[6] + i * header[11])
        _, kind, flags, _, start, size, _, _, _, _ = section
        if kind == 1 and start <= offset and offset + len(original) <= start + size:
            if flags & 4 or not flags & 2:
                raise ValueError('DTB is not in allocated nonexecutable data')
            data_section = True
    if not data_section:
        raise ValueError('Embedded DTB lacks a nonexecutable data section')
    for i in range(header[10]):
        segment = struct.unpack_from('<IIQQQQQQ', firmware, header[5] + i * header[9])
        kind, flags, start, _, _, size, _, _ = segment
        if kind == 1 and start <= offset and offset + len(original) <= start + size:
            return firmware[:offset] + replacement + firmware[offset + len(original):]
    raise ValueError('Embedded DTB is not in a loadable segment')


def prepare(out,base,base_dtb,base_firmware,release,report_path,queued,queued_first=False,defer_prefixes=(),batch_runner=False,prioritize_prefixes=(),retry_observation_gaps=False,execution_order=None):
    defer_prefixes=tuple(defer_prefixes)
    prioritize_prefixes=tuple(prioritize_prefixes)
    if any(not p for p in defer_prefixes) or (defer_prefixes and not queued_first):
        raise ValueError('Deferral requires nonempty prefixes and a full queued-first execution manifest')
    if any(not p for p in prioritize_prefixes) or (prioritize_prefixes and not queued_first):
        raise ValueError('Prioritization requires nonempty prefixes and a full execution manifest')
    data=json.loads((release/'transfer_manifest.json').read_text())
    report=json.loads(report_path.read_text())
    pending=remaining(data,report,retry_observation_gaps)
    if not pending and not (queued and queued_first):raise ValueError('No remaining tests')
    selected=[];names=set()
    common_vlens={512,1024}
    for root in [release,*queued]:
        m=json.loads((root/'transfer_manifest.json').read_text())
        common_vlens &= reference_coverage(m)
        if digest(root/'width_tests.tgz')!=m['archive_sha256']:raise ValueError('Package changed')
        for case in (pending if root==release else m['cases']):
            binary=root/'binaries'/case['name']
            if case['name'] in names or digest(binary)!=case['sha256'] or not binary.stat().st_mode&0o111:
                raise ValueError('Duplicate/changed/nonexecutable ELF')
            names.add(case['name']);selected.append((case,binary))
    if not selected:raise ValueError('No remaining tests')
    if queued_first:
        pending_names={c['name'] for c in pending}
        selected.sort(key=lambda pair:pair[0]['name'] in pending_names)
        if prioritize_prefixes:
            selected.sort(key=lambda pair:not pair[0]['name'].startswith(prioritize_prefixes))
        if defer_prefixes:
            selected.sort(key=lambda pair:pair[0]['name'].startswith(defer_prefixes))
    if execution_order is not None:
        if not queued_first:
            raise ValueError('Explicit order requires full execution manifest')
        from execution_order import reorder
        selected = reorder(selected, execution_order)
    execution=[c for c,_ in selected] if queued_first else pending
    batch_id = guest_batch.secrets.token_hex(16) if batch_runner else None
    batch_content = None
    if batch_runner:
        if 'batch.sh' in names:
            raise ValueError('Guest script collides with an ELF name')
        batch_content = guest_batch.script(dict(data, cases=execution), batch_id)
    out.mkdir(parents=True,exist_ok=False)
    resume=out/'resume';resume.mkdir()
    shutil.copy2(report_path,out/'previous_report.json')
    guest='width_'+hashlib.sha256(json.dumps([(c['name'],c['sha256']) for c,_ in selected]).encode()).hexdigest()[:12]
    overlay=out/'overlay';destination=overlay/'opt'/'rvv-preload'/guest;destination.mkdir(parents=True)
    for case,binary in selected:shutil.copy2(binary,destination/case['name'])
    entries=['opt','opt/rvv-preload','opt/rvv-preload/'+guest]+['opt/rvv-preload/'+guest+'/'+c['name'] for c,_ in selected]
    if batch_runner:
        (destination/'batch.sh').write_text(batch_content)
        (destination/'batch.sh').chmod(0o755)
        entries.append('opt/rvv-preload/'+guest+'/batch.sh')
    archive=out/'test_overlay.cpio'
    with archive.open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),
            stdout=stream,cwd=overlay,check=True)
    boot=out/'initramfs.cpio'
    with boot.open('wb') as stream:
        for path in (base,archive):
            with path.open('rb') as source:shutil.copyfileobj(source,stream)
    start=[int(x,16) for x in subprocess.check_output(['fdtget','-t','x',str(base_dtb),'/chosen','linux,initrd-start']).split()]
    end=[int(x,16) for x in subprocess.check_output(['fdtget','-t','x',str(base_dtb),'/chosen','linux,initrd-end']).split()]
    if len(start)!=2 or len(end)!=2:raise ValueError('Expected two-cell original initrd bounds')
    address=(start[0]<<32)|start[1]
    if ((end[0]<<32)|end[1])-address!=base.stat().st_size:raise ValueError('Original initrd bounds differ')
    dtb=out/'ara_vcu118.dtb';shutil.copy2(base_dtb,dtb)
    limit=address+boot.stat().st_size
    subprocess.run(['fdtput','-t','x',str(dtb),'/chosen','linux,initrd-end',format(limit>>32,'x'),format(limit&0xffffffff,'x')],check=True)
    firmware=out/'fw_jump.elf'
    firmware.write_bytes(patch_embedded_dtb(base_firmware.read_bytes(),base_dtb.read_bytes(),dtb.read_bytes()))
    shutil.copymode(base_firmware,firmware)
    binaries=resume/'binaries';binaries.mkdir()
    for case in execution:shutil.copy2(destination/case['name'],binaries/case['name'])
    package=resume/'width_tests.tgz'
    with tarfile.open(package,'w:gz') as tar:
        for case in execution:tar.add(binaries/case['name'],arcname=case['name'])
    data.update(cases=execution,archive_sha256=digest(package),archive_bytes=package.stat().st_size,
        reference_vlens=sorted(common_vlens),
        continuation=dict(previous_report_sha256=digest(report_path),
                          original_transfer_manifest_sha256=digest(release/'transfer_manifest.json'),
                          previous_attempts=[{'name':r['name'],'status':r['status']} for r in report['results']]))
    if common_vlens == {1024}:
        data['required_vlen_bits']=1024
    (resume/'transfer_manifest.json').write_text(json.dumps(data,indent=2)+'\n')
    if batch_runner:
        (resume/'batch.sh').write_text(batch_content)
        (resume/'batch_protocol.json').write_text(json.dumps(dict(
            run_id=batch_id, inputs=data,
            script_sha256=digest(destination/'batch.sh'),
            board_task_started=False), indent=2)+'\n')
        observer_sources = ('batch_serial.py', 'guest_batch.py', 'guest_watch.py')
        for name in observer_sources:
            shutil.copy2(Path(__file__).with_name(name), resume/name)
        shutil.copy2(Path(__file__).with_name('batch_width_suite.py'), resume/'width_suite.py')
    provenance=dict(scope='Authorized unchanged-bitstream restart; test-only appended rootfs overlay',
        base_initramfs_sha256=digest(base),initramfs_sha256=digest(boot),
        base_dtb_sha256=digest(base_dtb),dtb_sha256=digest(dtb),
        base_firmware_sha256=digest(base_firmware),firmware_sha256=digest(firmware),
        firmware_change='Only embedded DTB bytes; executable sections unchanged',
        preload_directory='/opt/rvv-preload/'+guest,
        dtb_change='Only /chosen/linux,initrd-end extends over test overlay',
        previous_report_sha256=digest(report_path),guest_directory='/tmp/'+guest,
        cases=[c for c,_ in selected],pending_in_stalled_batch=len(pending),
        execution_order=('Stall-prone families last; no cases omitted' if defer_prefixes else
                         'Queued releases before remaining stalled-batch cases') if queued_first else 'Stalled-batch continuation first',
        deferred_prefixes=list(defer_prefixes),
        retry_observation_gaps=retry_observation_gaps,
        retried_observation_cases=[r['name'] for r in report['results'] if r['status']=='incomplete'] if retry_observation_gaps else [],
        prioritized_prefixes=list(prioritize_prefixes),
        prioritized_cases=[c['name'] for c,_ in selected if c['name'].startswith(prioritize_prefixes)],
        deferred_cases=[c['name'] for c,_ in selected if c['name'].startswith(defer_prefixes)],
        execution_case_count=len(execution),sources=[str(p) for p in [release,*queued]])
    if execution_order is not None:
        provenance['execution_order'] = 'Explicit immutable pending-case order; no cases omitted'
        provenance['explicit_execution_order'] = list(execution_order)
    if batch_runner:
        provenance['guest_batch'] = dict(run_id=batch_id,
            script_path=provenance['preload_directory']+'/batch.sh',
            script_sha256=digest(destination/'batch.sh'),
            observer_adapter_required=False, board_task_started=False,
            observer_sha256={name:digest(resume/name) for name in
                             (*observer_sources, 'width_suite.py')})
    (out/'recovery.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('PRELOADED',len(selected),'REMAINING',len(pending),'GUEST',provenance['guest_directory'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--base-initrd',type=Path,required=True);p.add_argument('--release',type=Path,required=True)
    p.add_argument('--base-dtb',type=Path,required=True)
    p.add_argument('--base-firmware',type=Path,required=True)
    p.add_argument('--queued-first',action='store_true')
    p.add_argument('--defer-prefix',action='append',default=[])
    p.add_argument('--prioritize-prefix',action='append',default=[])
    p.add_argument('--batch-runner',action='store_true',
                   help='Preload optional guest script; does not select or start a board observer')
    p.add_argument('--retry-observation-gaps',action='store_true')
    p.add_argument('--board-report',type=Path,required=True);p.add_argument('queued',nargs='*',type=Path)
    a=p.parse_args();prepare(a.out,a.base_initrd,a.base_dtb,a.base_firmware,a.release,a.board_report,a.queued,a.queued_first,a.defer_prefix,a.batch_runner,a.prioritize_prefix,a.retry_observation_gaps)
