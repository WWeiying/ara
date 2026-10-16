"""Order immutable pending cases; risk ranking is not a correctness verdict."""


def efficient_order(cases):
    def rank(case):
        name = case['name']
        # These traces/reductions have measured no-retirement predecessors.
        # Finish returning diagnostics before paying another recovery cost.
        if name.startswith(('rvv_trace_fp_move_', 'rvv_trace_extension_', 'rvv_trace_permute_')):
            return -2
        # Gather discriminating short evidence before another full-suite stall.
        if name.startswith(('rvv_prefix_fp_move_', 'rvv_detail_fp_compare_', 'rvv_prefix_fp_compare_',
                            'rvv_small_fp_move_', 'rvv_small_fp_compare_',
                            'rvv_prefix_whole_', 'rvv_small_whole_',
                            'rvv_trace_masks_', 'rvv_small_masks_', 'rvv_small_fpwide_',
                            'rvv_small_exceptions_',
                            'rvv_small_slide_', 'rvv_prefix_slide_',
                            'rvv_small_gather_', 'rvv_small_fp_redspecial_', 'rvv_trace_fault_',
                            'rvv_small_fault_', 'rvv_small_segments_misaligned_')):
            return -4
        if name in ('rvv_repro_mask_boundary', 'rvv_repro_extension_overlap',
                    'rvv_repro_slidedown_zero_restart'):
            # These three short diagnostics may stall, but must not wait
            # behind hundreds of full original partitions to be exercised.
            return -2
        if name.startswith('rvv_repro_'):
            return -3
        # The remaining memory-restart originals have mixed historical
        # outcomes. Resolve these before repeatedly recovering known stalls.
        if name.startswith('rvv_memory_restart_'):
            return -1
        if name.startswith('rvv_fp_compare_restart_unmasked_'):
            return 0
        if name.startswith('rvv_segment_alignment_'):
            return 3
        # Masked slide partitions have captured completion stalls; defer,
        # but retain them rather than declaring the remaining trials covered.
        if (name.startswith('rvv_fp_move_restart_') and
                set(case.get('operation_ids', ())) & {2, 3}):
            return 4
        if (name.startswith('rvv_extension_') and
                (set(case.get('operation_ids', ())) & {2, 3} or
                 (case.get('overlap') is True and not case.get('operation_ids')))):
            return 4
        # Recoveries147..151 captured stalls in this masked slide family.
        # Defer the whole family, not just observed variants; this is scheduling
        # risk, not a failure verdict for the untested variants17..19.
        if (name.startswith('rvv_permute_restart_') and
                set(case.get('operation_ids', ())) & set(range(12, 20))):
            return 4
        # Recoveries156/158/159 captured merge stalls at these exact shapes.
        if name.startswith(('rvv_permute_restart_e8_m4_',
                            'rvv_permute_restart_e8_m8_',
                            'rvv_permute_restart_e16_m8_')):
            return 3
        # e8/m4 vv and vx gathers stalled in recoveries153/154. Schedule
        # wide-group gather variants after ordinary work, without judging
        # untested forms or omitting any of their configurations.
        if (name.startswith('rvv_permute_restart_') and
                case.get('lmul') in ('m4', 'm8') and
                set(case.get('operation_ids', ())) & {0, 1, 2, 3, 20}):
            return 3
        if case.get('lmul') == 'm8' or name.endswith('_m8'):
            return 2
        return 1

    return [case['name'] for case in sorted(cases, key=rank)]


def reorder(selected, names):
    original = [case['name'] for case, _ in selected]
    if len(set(original)) != len(original) or len(set(names)) != len(names):
        raise ValueError('Repeated execution case')
    if set(original) != set(names):
        raise ValueError('Execution order must retain every case exactly once')
    positions = {name: index for index, name in enumerate(names)}
    return sorted(selected, key=lambda pair: positions[pair[0]['name']])
