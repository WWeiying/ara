"""Prepare isolated refill fixture and fail-closed causal oracle; never launch EDA."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'verification/out'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
AUDIT = OUT / 'cache-port1-fsm762-readonly-audit-agent-20261007-02.json'
AUDIT_SHA = 'e465bbe7f351c6467305ee42feb61602083af2a932757d8f0e2284c1364dfdfb'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
A, B, B_WORD = 0x80010000, 0x80020000, 0x13579bdf2468ace0
FIELDS = ('cycle rst_n state_q state_d data_req tag_valid kill_req rd_ack rd_ack_q '
          'wr_cl_vld any_hit miss_req miss_ack miss_return data_gnt data_rvalid '
          'data_rdata data_rid mshr_valid mshr_owner axi_rvalid axi_rready axi_rlast '
          'axi_rid return_valid load_ack a_addr b_addr').split()
TARGETS = {6: ('State', 'REPLAY_READ'), 7: ('State', 'REPLAY_REQ'),
           21: ('Transition', 'READ->REPLAY_REQ'),
           23: ('Transition', 'REPLAY_READ->MISS_REQ'),
           27: ('Transition', 'REPLAY_REQ->REPLAY_READ')}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2)
        stream.write('\n')


def sample_contract():
    """Host-only protocol example, never presented as captured DUT evidence."""
    rows = []
    for i, (q, d) in enumerate(((0, 1), (1, 6), (6, 7), (7, 2), (2, 3), (3, 0))):
        row = dict.fromkeys(FIELDS, 0)
        row.update(cycle=i, rst_n=1, state_q=q, state_d=d,
                   data_rdata=B_WORD, data_rid=0 if i == 0 else 1,
                   a_addr=A, b_addr=B, axi_rready=1, axi_rid=1,
                   mshr_owner=1 if i == 5 else 0,
                   mshr_valid=int(i in (0, 1, 5)),
                   rd_ack=int(i in (0, 2, 3)), rd_ack_q=int(i in (1, 3, 4)),
                   data_req=int(i == 0), data_gnt=int(i == 0), tag_valid=int(i == 1),
                   wr_cl_vld=int(i == 1), load_ack=int(i == 1), return_valid=int(i == 1),
                   axi_rvalid=int(i == 0), axi_rlast=int(i == 0),
                   miss_req=int(i == 4), miss_ack=int(i == 4),
                   miss_return=int(i == 5), data_rvalid=int(i == 5))
        rows.append(row)
    return rows


def read_trace(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS, 'Exact passive probe schema required')
        rows = []
        for row in reader:
            require(set(row) == set(FIELDS) and all(v is not None for v in row.values()),
                    'Malformed trace row')
            require(all(v.isdecimal() for v in row.values()), 'Unknown/negative/nondecimal signal')
            rows.append({key: int(value) for key, value in row.items()})
    return rows


def oracle(rows):
    require(len(rows) == 6, 'Exactly six focused fixture cycles, including completion, required')
    for i, row in enumerate(rows):
        require(set(row) == set(FIELDS), 'Missing/foreign probe field')
        require(all(type(v) is int and v >= 0 for v in row.values()), 'Unknown/untyped probe value')
        for key in set(FIELDS) - {'cycle', 'state_q', 'state_d', 'data_rdata', 'data_rid',
                                  'mshr_owner', 'axi_rid', 'a_addr', 'b_addr'}:
            require(row[key] in (0, 1), 'Non-binary ' + key)
        require(row['cycle'] == i and row['rst_n'] == 1 and row['kill_req'] == 0,
                'Gap, reset or kill contaminates witness')
        require(row['a_addr'] == A and row['b_addr'] == B and A // 32 != B // 32,
                'Exact distinct cacheable A/B cachelines required')
        require(row['any_hit'] == 0, 'B must be cold, not hit-selected')
        require(row['wr_cl_vld'] == row['load_ack'], 'Refill not attributable to A load_ack')
        require(row['load_ack'] == int(bool(row['return_valid'] and row['mshr_valid']
                                          and row['mshr_owner'] == 0)), 'Wrong MSHR/refill ownership')
        if i:
            previous = rows[i - 1]
            require(row['state_q'] == previous['state_d'], 'Noncontiguous state sequence')
            require(row['rd_ack_q'] == previous['rd_ack'], 'Previous SRAM grant not recorded')
            require(row['return_valid'] == int(bool(previous['axi_rvalid'] and
                    previous['axi_rready'] and previous['axi_rlast'] and previous['axi_rid'] == 1)),
                    'Return pipeline is not one registered last-beat handshake')
    expected = sample_contract()
    for i, (row, contract) in enumerate(zip(rows, expected)):
        for key in FIELDS:
            # Read data is meaningful only at successful B completion.
            if key in ('data_rdata', 'data_rid') and i != 5:
                continue
            require(row[key] == contract[key], 'C%d %s violates exact fixture contract' % (i, key))
    return dict(status='LOCAL_CAUSAL_TRACE_PASS_NOT_SYSTEM_COVERAGE',
                target_raw_positions=sorted(TARGETS), B_word=B_WORD, B_id=1,
                system_population_admissible=False, measured_FSM_increment=None,
                CPU_PTW_path_qualified=False, full_cache_path_qualified=False)


def evidence(path, start, end):
    lines = path.read_text().splitlines()
    return dict(path=str(path), sha256=sha(path), lines=[start, end],
                text='\n'.join('%d: %s' % (i + 1, lines[i]) for i in range(start - 1, end)))


def prepare(output):
    output = Path(output).absolute()
    require(output.parent == OUT and not output.exists(), 'Fresh independent directory required')
    require(sha(AUDIT) == AUDIT_SHA, 'Reviewed audit drift')
    audit = json.loads(AUDIT.read_bytes())
    for path, digest in audit['pins'].items():
        require(sha(path) == digest, 'Reviewed audit evidence drift: ' + path)
    require(sha(BUILD / 'sim/simv') == IMAGE_SHA, 'Frozen image drift')
    core = ROOT / 'hardware/deps/cva6/core'
    sources = [
        (core / 'axi_shim.sv', 265, 280),
        (core / 'cache_subsystem/wt_axi_adapter.sv', 467, 473),
        (core / 'cache_subsystem/wt_axi_adapter.sv', 532, 595),
        (core / 'cache_subsystem/wt_axi_adapter.sv', 636, 673),
        (core / 'cache_subsystem/wt_dcache_missunit.sv', 345, 365),
        (core / 'cache_subsystem/wt_dcache_missunit.sv', 405, 429),
        (core / 'cache_subsystem/wt_dcache_mem.sv', 164, 187),
        (core / 'cache_subsystem/wt_dcache_ctrl.sv', 157, 201),
        (ROOT / 'hardware/src/ara_system.sv', 368, 385),
        (ROOT / 'hardware/src/ara_soc.sv', 615, 646),
        (ROOT / 'hardware/tb/ara_tb.sv', 745, 751),
        (ROOT / 'hardware/deps/axi/src/axi_delayer.sv', 108, 123)]
    frozen = json.loads((BUILD / 'build-source-pins.json').read_bytes())
    for path, _, _ in sources:
        require(str(path) in frozen and sha(path) == frozen[str(path)], 'Relevant frozen source drift: ' + str(path))
    targets = [r for r in audit['missing'] if r['raw_position'] in TARGETS]
    require({r['raw_position']: (r['kind'], r['name']) for r in targets} == TARGETS,
            'Full target5 compiled coordinates differ')
    require(all(not r['hit'] for r in targets), 'Targets must remain zero in formal762')
    compiled = json.loads((BUILD / 'compile.command.json').read_bytes())
    require('verify_axi_delay=1' in compiled['command'] and 'no_fsdb=1' in compiled['command'],
            'Frozen compile flags differ')
    host_result = oracle(sample_contract())
    pins = {str(AUDIT): AUDIT_SHA, str(BUILD / 'sim/simv'): IMAGE_SHA,
            str(BUILD / 'build-source-pins.json'): sha(BUILD / 'build-source-pins.json'),
            str(BUILD / 'compile.command.json'): sha(BUILD / 'compile.command.json')}
    pins.update({str(path): sha(path) for path, _, _ in sources})
    for name in ('cache_port1_refill_successor.py', 'cache_port1_refill_successor_fixture.sv',
                 'cache_port1_refill_successor_probe.sv', 'test_cache_port1_refill_successor.py'):
        pins[str(HERE / name)] = sha(HERE / name)
    result = dict(schema='CACHE_PORT1_REFILL_SUCCESSOR_PREPARATION_V1',
        status='HOST_PREFLIGHT_PASS_REAL_DUT_RUN_BLOCKED_NO_EXACT_RESPONSE_CONTROL',
        reviewed_population=762, scope=audit['scope'], machine=audit['compiled_machine'],
        target5=targets, pins=pins, source_evidence=[evidence(*item) for item in sources],
        causal_derivation=dict(boundary='CVA6 wt_axi_adapter/i_axi_shim AXI R input, pre-edge sample',
            equation='G = B data_gnt edge; F = registered load_ack cycle = G+1; H = A last R handshake edge = F-1 = G',
            exact_last_handshake_offset_from_B_grant=0, adapter_return_register_cycles=1,
            preconditions=['Accepted cacheable read A owns MSHR port0; valid DCACHE_LOAD_ACK with matching transaction ID',
                'No invalidate/inval_valid arbitration masks dcache read response; axi_rd_rdy=1',
                'B DTLB hit, no exception/flush, B granted at G and tag_valid at G+1',
                'No other SRAM requester denies replay grant at G+2; B cold and cache enabled'],
            upstream_formula='At an upstream responder with L cycles to shim last-handshake, release at G-L. L and G must be independently established, not guessed or swept.',
            response_protocol='Hold a not-yet-asserted final beat; once RVALID is asserted, keep payload/ID/LAST stable until handshake. Do not withdraw RVALID.',
            fixed_delay_numeric_choice_justified=False,
            PTW_setup='Requires independent port0 PTW walk (e.g. instruction-side walk) while B has warm data translation. A scalar load waiting on its own DTLB walk cannot be treated as an independent B.',
            real_DUT_PTW_B_issue_alignment_proven=False),
        blockers=[
            'Existing i_ara_verify_axi_delayer delays Ara vector requests by3, response by0; it is not a runtime PTW/CPU R-response control.',
            'AxiRespDelay=200ps only drives TARGET_GATESIM response assignment, not this frozen RTL path.',
            'No reviewed frozen runtime hook holds a selected CPU/PTW final R beat or targets B-grant alignment; no numeric delay can be causally selected.',
            'New focused probe is not compiled into frozen image; no_fsdb=1 forbids assuming a new FSDB path.',
            'PTW A concurrent with independent scalar B is not yet demonstrated by a cycle-qualified real-DUT workload.'],
        fixture=dict(path=str(HERE / 'cache_port1_refill_successor_fixture.sv'),
            kind='STANDALONE_UNCHANGED_CONTROLLER_WITH_MODELED_ENVIRONMENT',
            uses_internal_force=False, observes_state_readonly=True,
            real_CPU=False, real_PTW=False, real_missunit=False, real_AXI_adapter=False,
            full_cache=False, SV_compiled=False, SV_executed=False,
            response_model='Single return-valid register models adapter latency; explicit accepted-A MSHR context, normal controller interface inputs only.',
            B_completion_model='Explicit miss_ack/miss_return inputs, fixed expected B data; validates controller result routing, not physical memory correctness.',
            system_population_admissible=False, VDB_admission_policy='NEVER admit standalone fixture VDB to system population'),
        focused_probe=dict(path=str(HERE / 'cache_port1_refill_successor_probe.sv'),
            schema=FIELDS, sampling='pre-edge posedge clk', max_cycles=32,
            injection_into_frozen_image=False),
        host_model=dict(status='PROTOCOL_CONTRACT_ONLY_NOT_CAPTURED_DUT', result=host_result),
        expected_example=str(output / 'expected-protocol-example.json'),
        permitted_run_count=1, permitted_real_DUT_timeout_s=600, real_DUT_launch_authorized_by_preflight=False,
        simulation_launched=False, RTL_changed=False, sealed_helpers_changed=False,
        exclusions_applied=False, system_population_changed=False)
    output.mkdir()
    save(output / 'expected-protocol-example.json', dict(provenance='HOST_MODEL_NOT_CAPTURED_DUT', rows=sample_contract()))
    save(output / 'preflight.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('oracle')
    check.add_argument('--trace', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        result = prepare(args.output)
        print(json.dumps(dict(status=result['status'], seal=sha(args.output / 'preflight.json'),
                              target_raw_positions=sorted(TARGETS), simulation_launched=False)))
    else:
        result = oracle(read_trace(args.trace))
        result.update(trace=str(args.trace.absolute()), trace_sha256=sha(args.trace),
                      provenance='USER_SUPPLIED_LOCAL_TRACE_NOT_SYSTEM_QUALIFIED')
        save(args.output, result)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
