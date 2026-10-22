"""Metadata-only runtime risk basis; no process/trace progress polling."""
import checker as c
import replay as r
old=c.HERE.parent/'full_e16_m8_block_vcs_m9_plan01/prepared01'
receipt=old/'replay/tests/arithmetic_original_e16_m8_full4095_block/child_outcome.unvalidated.json'
watch=c.HERE.parent/'m8_sentinel_mask_static_review_hilbert01/WATCHDOG_CANDIDATE_REVIEW.md'
c.require(c.sha(watch)=='e27603e7f56146a68fc4fb235d0046454c50a0a4725d53bb4627dac5956ae918','Independent diagnostic candidate')
r.durable(c.HERE/'runtime_basis.json',dict(
    budget_gate='QUALIFIED_UNPROVEN_RUNTIME_REQUIRES_PARENT_ONCE_ADMISSION',
    reference_firmware_to_HTIF=2540955,reference_firmware_to_exit=2540949,
    previous_reference_firmware_to_exit=2807400,
    reference_firmware_reduction_fraction=1-2540949/2807400,
    previous_actual_monitor=c.read(receipt),previous_actual_monitor_sha256=c.sha(receipt),
    previous_actual_full_completion_runtime_known=False,
    under_3h_completion_guaranteed=False,wall_case_s=10800,wall_worker_s=12000,wall_service_s=13200,
    watchdog_plusarg=r.WATCHDOG,watchdog_candidate_review=str(watch),watchdog_candidate_review_sha256=c.sha(watch),
    watchdog_cycle_silence_limit=1000000,watchdog_progress='retire or accepted req/resp or backend alloc/done; not arch_start alone',
    observed_old_prefix_all_event_gap=6352,observation_is_not_end_to_end_or_shape_max_bound=True,
    fixed_memory_service='L2 grant=req; registered rvalid; fixed AXI200ps; not fairness proof',
    progress_fflush_wall_overhead_unmeasured=True,fflush_is_not_fsync=True,
    possible_active_livelock_masks_owner_hang=True,watchdog_fatal_is_NOT_PASS=True,
    no_timeout_extension=True,no_retry=True,no_DUT_launch_authorization=True))
print('RUNTIME_RISK_RECORDED')
