"""Static target selection only; no simulator, EDA, admission or exclusions."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'narrow-reject-r1-cached-offline-admitted-723-20261006-01'
SEAL = '2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
MMU = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu'
VDB = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb'
REPORT = OUT / 'rvv-system-static-targets-723-20261006-01.json'
OBJDUMP = Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-objdump')
WORD = 0xBAA04857


def digest(path):
    with Path(path).open('rb') as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    require(not REPORT.exists() and not REPORT.with_suffix('.seal.json').exists(), 'Fresh output required')
    pins = {}

    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = digest(path)
        require(expected is None or actual == expected, 'Pin drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input changed')
        pins[str(path)] = actual
        return path

    manifest_path = pin(BASE / 'admission-manifest.json', SEAL)
    manifest = json.loads(manifest_path.read_bytes())
    for name in ('combined-bits.json', 'status.json', 'evidence-pins.json'):
        p = BASE / name
        pin(p, manifest['output_pins'][str(p)])
    bitmap = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 723, 'Not exact723')
    require(json.loads((BASE / 'status.json').read_bytes())['coverage_admitted'] is True, 'Not formal base')
    design = Design(VDB)
    for relative, expected in bitmap['design'].items():
        pin(design.db / relative, expected)
    for relative in ('auxiliary/verilog.sourceinfo.xml', 'shape/line.verilog.info.xml',
                     'shape/branch.verilog.info.xml', 'shape/cond.verilog.info.xml'):
        pin(design.db / relative)
    sourcepins = json.loads(pin(OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    frozen = pin(OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv',
                 sourcepins[str(ROOT / 'hardware/src/ara_dispatcher.sv')])
    for relative in ('hardware/src/cva6_accel_first_pass_decoder.sv', 'hardware/src/ara_soc.sv',
                     'hardware/src/lane/operand_queue.sv', 'hardware/src/lane/operand_queues_stage.sv',
                     'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
                     'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv'):
        p = ROOT / relative
        pin(p, sourcepins[str(p)])
    require(design.source(SCOPE)['file_id'] == '547', 'Dispatcher source identity drift')
    for p in (Path(__file__), Path(__file__).with_name('inventory_operand_debug.py'),
              Path(__file__).with_name('closure_point_inventory.py'),
              Path(__file__).parent / 'reviewed_20261004/audit_readonly.py'):
        pin(p)
    cond_root = read_xml(design.db / 'shape/cond.verilog.shape.xml')

    def inventory(scope, locations):
        result = []
        for metric in ('line', 'branch', 'cond'):
            record = bitmap['metrics'][metric][scope]
            node = (definition(cond_root, design.hierarchy[scope], record['checksum'])
                    if metric == 'cond' else design.definition(scope, metric))
            require(node.get('chksum') == record['checksum'], 'Shape checksum drift')
            for p in points(metric, node, record['width']):
                if metric == 'branch':
                    selected = [e for e in p['expressions'] if int(e['id']) in locations
                                and p['native_vector']['vector'][-int(e['index'])] == '1']
                    take = bool(selected)
                else:
                    selected = []
                    take = p['line'].isdigit() and int(p['line']) in locations
                if not take:
                    continue
                result.append(dict(scope=scope, metric=metric, raw_index=p['raw_index'],
                    width=record['width'], checksum=record['checksum'], compiled_id=p['native_id'],
                    file_id=p['file_id'], line=p['line'], vector=p['vector'],
                    hit723=bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - p['raw_index']))),
                    expression=p['expression'] if metric != 'branch' else None,
                    branch_predicates=selected,
                    branch_full_vector_sha256=(hashlib.sha256(p['native_vector']['vector'].encode()).hexdigest()
                                               if metric == 'branch' else None),
                    line_attributes=p['attributes'] if metric == 'line' else None,
                    condition_row=p.get('row'), source=design.source(scope)))
        return result

    dispatcher = inventory(SCOPE, {2251, 2254})
    targets = [p for p in dispatcher if not p['hit723']]
    require({(p['metric'], p['raw_index']) for p in targets} ==
            {('line', 557), ('line', 564), ('branch', 921), ('branch', 925), ('cond', 265)},
            'Candidate zero targets changed')
    evidence = json.loads((BASE / 'evidence-pins.json').read_bytes())
    elfs = {p: h for p, h in evidence.items() if p.endswith('.elf')}
    matches, scanned, cache = [], {}, {}
    # A missing byte sequence in the entire ELF proves absence in its instructions.
    # If present anywhere, use non-ZCC disassembly to avoid treating data as code.
    for p, h in elfs.items():
        require(digest(p) == h, 'Admitted ELF drift: ' + p)
        scanned[p] = h
        if h not in cache:
            found = []
            if WORD.to_bytes(4, 'little') in Path(p).read_bytes():
                pin(OBJDUMP); pin(OBJDUMP.resolve())
                lines = subprocess.run([str(OBJDUMP), '-d', p], check=True, capture_output=True).stdout.decode('utf-8', 'strict').splitlines()
                for line in lines:
                    m = re.match(r'\s*([0-9a-f]+):\s+(.*)', line)
                    if not m:
                        continue
                    tokens = m[2].split()
                    if len(tokens) >= 4 and all(re.fullmatch('[0-9a-f]{2}', t) for t in tokens[:4]):
                        value = int.from_bytes(bytes.fromhex(' '.join(tokens[:4])), 'little')
                    elif tokens and re.fullmatch('[0-9a-f]{8}', tokens[0]):
                        value = int(tokens[0], 16)
                    else:
                        continue
                    if value == WORD:
                        found.append(m[1])
            cache[h] = found
        if cache[h]:
            matches.append(dict(elf=p, sha256=h, pcs=cache[h]))
    software = ROOT / 'apps/riscv-tests/isa/rv64uv'
    for name in ('sv39_gap34_body.h', 'sv39_gap52_superpage_sfence_pmp0.c',
                 'sv39_gap68_warm_permissions_pmp0.c', 'vnarrow_reject_r1_matrix.c',
                 'vnarrow_reject_r1_matrix_cached.c', 'vgap103_narrow_prefix.c', 'vnclipu.c', 'vnclip_edges.c'):
        pin(software / name)
    system_members = [p for p in bitmap['tests'] if any(n in p for n in ('sv39_gap34', 'sv39_gap52', 'sv39_gap68'))]
    require(len(system_members) == 5, 'System case membership differs')
    report = dict(status='STATIC_TARGET_DESIGN_ONLY_NOT_RUN_NOT_ADMITTED_NOT_WAIVED', baseline=723,
        baseline_path=str(BASE), baseline_manifest_sha256=SEAL, target_points=targets,
        candidate=dict(name='vnclipu_wx_width_alignment_reject_723', word='0xbaa04857',
            instruction='vnclipu.wx v16,v10,zero', sew=64, lmul='m2', vtype='0x19', vl=2,
            vstart=1, vm=1, tail='undisturbed', mask='undisturbed',
            frozen_source=str(frozen), source_lines=[2246, 2248, 2249, 2251, 2252, 2254, 5257, 5273, 5277],
            principle='合法e64/m2且VL>vstart；窄化源EEW128超过ELEN64，同时源EMUL4而v10%4=2。两个独立if都赋illegal_insn。前端5257..5280清ara_req_valid并产生cause2/精确tval；不会生成queue command，不宣称operand queue正向收益。',
            producer='cva6_accel_first_pass_decoder.sv:79..90对OpcodeVec/OPIVX转发并读取scalar；不按func6过滤该编码。',
            expected_delta=dict(line=2, branch=2, cond=1, fsm=0), measured=False,
            oracle='复用保存全部标量trap state的CRT/handler。唯一trap cause2、tval=0xbaa04857、mepc=fault标号、仅PC+4；trap入口vstart=1，记录handler副作用。前后full32VRF+guards不变；vl/vtype/vcsr/fcsr按独立契约核验。精确bad退休owner不能有backend allocation/VRF writes/memory issue。随后e16/m2、VL2、vstart0执行vnclipu.wx v16,v8,zero，32bit源[0x1234,0x10001]结果[0x1234,0xffff]且vxsat=1，tail不变。完整Spike scalar/vector差分no skip/no falseSpike；禁止以DUT snapshot构造gold。',
            timing='仅一个拒绝点加一次合法恢复，预计1-3分钟为旧VSBC量级推测，未测量；不授权launch。',
            dedup='R1只测func6=44/45窄化移位；GAP103为合法narrow prefix，不是本拒绝上下文。723全evidence-pins ELF逐个hash+指令字检查如下；已有合法VNCLIP不等同这个case。新ELF尚未构建，不能声称新ELF去重完成。'),
        elf_dedup=dict(elf_paths=len(scanned), unique_hashes=len(cache), exact_word_matches=matches,
            scanned_map_sha256=hashlib.sha256(json.dumps(scanned, sort_keys=True).encode()).hexdigest(),
            original_evidence_pins=str(BASE / 'evidence-pins.json'), new_elf_created=False),
        queue_screening='ALUA factor4/8零点缺ordinary producer证明；ALUB实际conversion路径大多已命中；mask/neutral/reduction零点还受producer/实例参数约束。protected252仍保护，未选VL257/已知carry-slide-FP16/R2 VILL bug路径。',
        system=dict(exact723_members=system_members,
            existing_elf_pins={p: h for p, h in elfs.items() if any(n in p for n in ('sv39_gap34', 'sv39_gap52', 'sv39_gap68'))},
            ptw_points=inventory(MMU + '.i_ptw', {454, 456, 470, 479, 481, 487, 488, 490}),
            mmu_points=inventory(MMU, {529, 530, 531, 595, 596, 623, 624}),
            conclusion='gap34 scenarios明确包含A=0、D=0、execute-only MXR0/1、U-page SUM0/1、misaligned1G/2M。PTW A-only cond50、D-only cond67、MXR-only cond56、misaligned error line81均已hit；不盲重做。SUM及复合分支逐点见附表，个别raw零不等于场景未执行或可waive。已有成员资格不在本静态任务重新验收。',
            protection='编译表达式显示RVH=0；ara_soc.sv545冻结配置NrPMPEntries=0。仅可另做精确受这些常量支配的point级不可达证明，未生成/applied waiver。A/D/MXR/SUM/superpage是软件可达，不因Linux不用豁免；PTW共享error行hit不单独证明所有语义。'),
        pins=pins, simulations_started=False, EDA_started=False, rtl_changed=False,
        native_DVE_selector_binding=False, raw_indices_are_DVE_selectors=False)
    for p, h in pins.items():
        require(digest(p) == h, 'Input changed before sealing')
    with REPORT.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    seal = digest(REPORT)
    with REPORT.with_suffix('.seal.json').open('x') as stream:
        json.dump({str(REPORT): seal}, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(report=str(REPORT), seal=seal, targets=len(targets),
                         elfs=len(scanned), exact_word_matches=len(matches), system_members=len(system_members))))


if __name__ == '__main__':
    main()
