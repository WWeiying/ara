#!/usr/bin/env python3
"""Frozen integrated area candidates; leaves the original serial flow untouched.

Use the same prepare/check/run/status/report commands as flow.py. Preparing
inputs does not invoke DC. These profiles are experimental, not RTL defaults.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import flow


HERE = Path(__file__).resolve().parent
BASE = dict(flow.PROFILES['full_area_shared1'])
# Same control changes on both sides; do not charge them to area candidates.
BASE.update(ARA_RED_ORDERED_READY_INDEPENDENT_MASK='1',
            ARA_RED_CONTEXT_ISSUE_CUT='1')
AREA_FLAGS = {
    'ARA_RED_ROOT_ONLY_RESULT_CACHE': '1',
    'ARA_RED_PRUNE_LEGACY_FP_STREAM': '1',
    'ARA_RED_COMPACT_EXACT_SEGMENTS': '1',
    'ARA_RED_SHARED_RCE_ADD': '1',
}
PROFILES = {
    'area_pair_reference': BASE,
    'area_pair_compact': dict(BASE, **AREA_FLAGS),
    'area_pair_arithmetic': dict(BASE, **AREA_FLAGS,
                                ARA_RED_ARITHMETIC_ONLY_FORWARD='1'),
}
TIMING_AREA_FLAGS = {
    'ARA_RED_STATIC_LEGACY_STATE': '1',
    'ARA_RED_STATIC_ORDERED_ARBITER': '1',
    'ARA_RED_COMPACT_ORDERED_BACKEND': '1',
}
PROFILES['area_pair_timing'] = dict(PROFILES['area_pair_arithmetic'], **TIMING_AREA_FLAGS)
PROFILES['area_pair_direct_read'] = dict(PROFILES['area_pair_timing'],
                                        ARA_RED_EXACT_DIRECT_BIN_READ='1')
POLICY = {
    'scope': 'Matched current RTL and full ara_soc; experimental area profiles',
    'base_profile': 'full_area_shared1',
    'common_control_flags': ['ARA_RED_ORDERED_READY_INDEPENDENT_MASK',
                             'ARA_RED_CONTEXT_ISSUE_CUT'],
    'profiles': PROFILES,
    'report_query': 'Clock-group worst path, checked edge-triggered endpoints; '
                    'no all-register Cartesian timing query',
    'limits': 'No area, timing, or performance conclusion from preparation. '
              'Reference is the five-refinement optimized implementation, '
              'not original upstream Ara. Local savings are not additive.',
}

original_prepare = flow.prepare


def bounded_report_template(text):
    old = '''        set starts [all_registers -edge_triggered -output_pins]
        set ends [all_registers -edge_triggered -data_pins]
        report_timing -from $starts -to $ends -delay_type max -max_paths 50 \\
            > ../reports/reg2reg_max.rpt'''
    new = '''        # INPUTS/OUTPUTS/COMBO have separate SDC groups. Query the clock
        # group directly, then verify its worst path really connects two FFs.
        # This avoids the expensive all-register -from/-to query; no timing
        # constraint, exception or optimization option changes.
        set reg2reg_worst [get_timing_paths -group clk_i -delay_type max -max_paths 1]
        if {[sizeof_collection $reg2reg_worst] != 1} {error "Missing clock-group worst path"}
        set edge_regs [all_registers -edge_triggered]
        set edge_count [sizeof_collection $edge_regs]
        set reg_path [index_collection $reg2reg_worst 0]
        set meta [open ../reports/reg2reg_query_scope.rpt w]
        puts $meta "query=clock_group_clk_i_top1"
        puts $meta "clocks=[get_object_name [get_clocks *]]"
        foreach key {startpoint endpoint} {
            set point [get_attribute $reg_path $key]
            set cls [get_attribute $point object_class]
            if {$cls == "pin"} {
                set cell [get_cells -of_objects $point]
            } elseif {$cls == "cell"} {
                set cell $point
            } else {error "Unexpected timing point type: $cls"}
            if {[sizeof_collection $cell] != 1} {error "Ambiguous timing point cell"}
            set member [expr {[sizeof_collection [remove_from_collection $edge_regs $cell]] == $edge_count - 1}]
            puts $meta "$key=[get_object_name $point] edge_triggered_member=$member"
            if {!$member} {error "Worst clock-group path is not FF-to-FF; explicit subset analysis required"}
        }
        close $meta
        report_timing -group clk_i -delay_type max -max_paths 1 -significant_digits 6 \\
            > ../reports/reg2reg_max.rpt'''
    assert text.count(old) == 1, 'Timing template changed; review required'
    text = text.replace(old, new)
    old_summary = '[min_slack [get_timing_paths -delay_type max -from $starts -to $ends -max_paths 1]]'
    assert text.count(old_summary) == 1
    text = text.replace(old_summary, '[min_slack $reg2reg_worst]')
    # Count the shared execution owners, not their per-format arithmetic
    # children. The compact backend has three i_add children per owner.
    marker = '    set local_adds [get_cells -hier -filter {full_name =~ *i_fpnew_ordered_fast}]'
    topology = r'''    set shared_unit_names {}
    set shared_unit_slices [dict create]
    foreach_in_collection c $shared_adds {
        set name [get_object_name $c]
        if {![regexp {^(.*gen_unit\[[0-9]+\])} $name _ unit_name]} {
            error "Unrecognized shared ADD instance: $name"
        }
        lappend shared_unit_names $unit_name
        dict incr shared_unit_slices $unit_name
    }
    set shared_unit_count [llength [lsort -unique $shared_unit_names]]
    set expected_slices [expr {$RCE_PROFILE in {area_pair_timing area_pair_direct_read} ? 3 : 1}]
    dict for {unit_name slices} $shared_unit_slices {
        if {$slices != $expected_slices} {
            error "Shared ADD format topology mismatch: $unit_name has $slices, expected $expected_slices"
        }
    }
'''
    assert text.count(marker) == 1
    text = text.replace(marker, topology + marker)
    text = text.replace('[sizeof_collection $shared_adds]', '$shared_unit_count')
    inventory = '    puts $f "shared_units=$shared_unit_count expected=$RCE_EXPECT_SHARED_ORDERED"'
    assert text.count(inventory) == 1
    text = text.replace(inventory, inventory + '\n    puts $f "arithmetic_instances=[get_object_name $shared_adds]"')
    # current_design's area attribute can be empty after hierarchical mapping.
    # Take the explicitly reported cell area, and fail on an empty summary.
    old_area = '        puts $f "total_cell_area=[get_attribute [current_design] area]"'
    new_area = '''        set area_file [open ../reports/area.rpt r]
        set area_report [read $area_file]
        close $area_file
        if {![regexp {Total cell area:\\s+([0-9.eE+-]+)} $area_report _ total_area]} {
            error "Missing numeric total cell area in report"
        }
        if {![string is double -strict $total_area] || $total_area <= 0} {
            error "Invalid total cell area: $total_area"
        }
        puts $f "total_cell_area=$total_area"'''
    assert text.count(old_area) == 1
    return text.replace(old_area, new_area)


def prepare(args, out):
    # Private templates are copied and sealed by the existing preparation.
    # Never edit the original template or any previously frozen run.
    original_here = flow.HERE
    with tempfile.TemporaryDirectory(prefix='ara_area_pair_templates_') as directory:
        private = Path(directory)
        shutil.copytree(original_here / 'templates', private / 'templates')
        dc = private / 'templates/dc.tcl'
        dc.write_text(bounded_report_template(dc.read_text()))
        config = json.loads((original_here / 'profiles.json').read_text())
        config['profiles'].update(PROFILES)
        flow.write_json(private / 'profiles.json', config)
        try:
            flow.HERE = private
            original_prepare(args, out)
        finally:
            flow.HERE = original_here
    provenance = out / 'provenance'
    extension = provenance / Path(__file__).name
    shutil.copy2(__file__, extension)
    policy = provenance / 'area_pair_profiles.json'
    flow.write_json(policy, POLICY)
    manifest = json.loads((out / 'manifest.json').read_text())
    manifest['area_pair_policy'] = POLICY
    manifest['frozen_files'].extend(
        {'snapshot': str(path.relative_to(out)), 'sha256': flow.sha(path)}
        for path in (extension, policy))
    flow.write_json(out / 'manifest.json', manifest)
    flow.check(out, environment=True)


if __name__ == '__main__':
    flow.PROFILES = PROFILES
    flow.prepare = prepare
    if not any(arg == '--profile' or arg.startswith('--profile=')
               for arg in sys.argv[1:]):
        sys.argv.extend(['--profile', 'area_pair_compact'])
    try:
        flow.main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        sys.exit(1)
