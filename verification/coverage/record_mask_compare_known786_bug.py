"""Source-bound closure of measured wrong old-mask reads; no qualification."""
from pathlib import Path
import collect_mask_compare_restart_known786 as frozen

life,require=frozen.life,frozen.require
OUT=life.OUT
ANALYSIS=OUT/'mask-compare-known786-failure-analysis-agent-20261008-01'
WAVE=OUT/'mask-compare-known786-wave-causality-agent-20261008-01/wave-causality.json'
WAVE_SHA='3221d0e4298582087f0ab4765b401872e969b0b97bb11b7522a360d02f36afc6'
RESULT=OUT/'mask-compare-known786-measured-bug-agent-20261008-01.json'


def record():
    require(not RESULT.exists(),'Fresh bug record')
    wave=life.read_bound(WAVE,WAVE_SHA)
    scalar_path=ANALYSIS/'scalar-comparison.json'; native_path=ANALYSIS/'native-compares.json'
    scalar=life.read_bound(scalar_path,life.digest(scalar_path)); native=life.read_bound(native_path,life.digest(native_path))
    book=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book_sha='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
    sources=life.read_bound(book,book_sha)
    pins={str(book):book_sha,str(WAVE):WAVE_SHA,str(scalar_path):life.digest(scalar_path),
        str(native_path):life.digest(native_path),str(Path(__file__).resolve()):life.digest(Path(__file__))}
    pins=life.merge_pins(pins,wave['input_pins'])
    for rel in ('hardware/src/lane/lane.sv','hardware/src/lane/operand_requester.sv',
                'hardware/include/ara_pkg.sv','hardware/include/rvv_pkg.sv','hardware/src/masku/masku.sv'):
        path=life.ROOT/rel; pins[str(path)]=sources[str(path)]
    life.check(pins)
    require(scalar['status']=='MISMATCH' and scalar['skipped_unobservable_register_values']==0 and
        scalar['ara_trap_events']==0,'Actual scalar failure, no skipped values or traps')
    mismatch=scalar['mismatch']
    require(mismatch['index']==31589 and mismatch['reason']=='gpr_value' and
        mismatch['spike']['pc']=='0x00000000800024f8' and
        mismatch['spike']['gpr_writes']['x10']=='0x00000000000000f3' and
        mismatch['ara']['rd_value']=='0x00000000000000f7','Exact first scalar mask-byte divergence')
    require(not native['unknown'] and len(native['nonmask_writer_checks'])==10 and
        all(not r['mismatches'] for r in native['nonmask_writer_checks']), 'All nonmask native writers exact')
    require([c['prestart_wrong_bits'] for c in native['cases']]==[[2],[3,6],[1,2,5,7,9,10,13,15]] and
        all(not c['active_wrong_bits'] and c['old_v1_matches_seed'] and c['v2_matches_seed'] for c in native['cases']),
        'Actual initialized prestate and precise prestart-only errors')
    for case,chain in enumerate(wave['chains']):
        offset=frozen.p.STARTS[case]//4
        for lane in chain['lanes']:
            seed=frozen.p.old_bytes(1 if offset==4 else 0)
            word=offset%4
            expected=bytes(seed[word*32+frozen.vc._deshuffle_byte(lane['lane']*8+b,4,0)] for b in range(8))
            require(int(lane['response']['data'],16)==int.from_bytes(expected,'little'),
                'Full64-bit actual VRF response not the predicted wrong initialized word')
            lane['predicted_wrong_physical_word_hex']='%016x'%int.from_bytes(expected,'little')
    result=dict(status='CONFIRMED_FROZEN_IMAGE_MASK_COMPARE_PRESTART_WRONG_WORD_BUG_NOT_ADMITTED',
        first_scalar_mismatch=mismatch,matched_scalar_prefix=31589,
        actual_retirements=scalar['ara_retired_instructions'],scalar_comparison=scalar,
        native_cases=native['cases'],all10_nonmask_writers_exact=True,
        cycle_causality=wave['chains'],all12_selected_VRF_responses_match_wrong_word=True,
        packed_layout_source_bound=True,input_pins=pins,
        detail='VMSLTU.vv v1,v8,v16: architectural vstart4/8/16 propagates lane vstart1/2/4 to EW64 MaskB fetch; wrong addresses5/6/8 instead of4. Last crosses v2. Old-vd merge preserves the wrong fetched prestart bits.',
        original_collector_failure_preserved=True,
        diagnostic_metadata_erratum='Initial diagnostic.json first_scalar_mismatch used a nonexistent generic key and is null. scalar-comparison.json mismatch is authoritative and reproduced here without changing the old artifact.',
        VPD_conversions=1,VCS_retries=0,RTL_modified=False,coverage_admitted=False,coverage_gain_claimed=False)
    life.check(pins); life.save(RESULT,result)
    print('BUG_RECORDED',str(RESULT),life.digest(RESULT))


if __name__=='__main__': record()
