"""Fixed-image guard successor; original software oracle/build is unchanged."""
import argparse
from pathlib import Path

import build_store_fault_flush_preflight as frozen

life, require = frozen.life, frozen.require
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
COMPILE = frozen.BUILD / 'compile.command.json'
COMPILE_SHA = '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1'
FROZEN_SHA = '20c0b850ac3c972620ca4cc58f7b2cfa3f249998920867ab16348649faf48b2d'
BOOK = life.OUT / 'gap100-offline-admitted-715-20261006-01/seals.json'
BOOK_SHA = '069e9e7717e915c18ce921f583fa33bf18e7670a3f13ec12073e8bba1998a283'
PLAN = life.OUT / 'closure90-current-20261005-01/plan.json'
PLAN_SHA = '7dba67ac552e0f0a65fa1df6f8f6e8ec2e3469da738ca88e9ee965e33a9ecf49'
REVIEW = life.OUT / 'store-fault-flush-static-review-731-agent-20261006-01/review.json'
REVIEW_SHA = 'd6b95200821ea3c19554e923ebd680484a6d6ee4c4af2995e8934fb9236485dc'
ORIGINAL_STATIC = frozen.static


def fixed_inputs():
    require(life.digest(Path(frozen.__file__).resolve()) == FROZEN_SHA, 'Frozen predecessor drift')
    book = life.read_bound(BOOK, BOOK_SHA)
    plan = life.read_bound(PLAN, PLAN_SHA)
    review = life.read_bound(REVIEW, REVIEW_SHA)
    require(book['pins'].get(str(COMPILE)) == COMPILE_SHA, 'Historical compile identity differs')
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SHA, 'Historical runtime66 identity differs')
    require(life.digest(life.IMAGE) == IMAGE_SHA, 'Fixed simv bytes differ')
    require(life.digest(COMPILE) == COMPILE_SHA, 'Fixed compile-command bytes differ')
    # These are expected hashes from sealed history, never a fresh digest whitelist.
    pins = life.merge_pins(plan['image'], review['pins'])
    pins = life.merge_pins(pins, {
        str(BOOK): BOOK_SHA, str(PLAN): PLAN_SHA, str(COMPILE): COMPILE_SHA,
        str(REVIEW): REVIEW_SHA,
        str(Path(frozen.__file__).resolve()): FROZEN_SHA,
        str(Path(__file__).resolve()): life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_build_store_fault_flush_preflight_v2.py')):
            life.digest(Path(__file__).with_name('test_build_store_fault_flush_preflight_v2.py')),
    })
    life.check(pins)
    return pins


def static():
    pins = fixed_inputs()
    receipt = ORIGINAL_STATIC()
    receipt['pins'] = life.merge_pins(pins, receipt['pins'])
    require(receipt['pins'][str(life.IMAGE)] == IMAGE_SHA and
            receipt['pins'][str(COMPILE)] == COMPILE_SHA, 'Fresh identity cannot replace expected pins')
    receipt['fixed_image_contract'] = dict(image_sha256=IMAGE_SHA, compile_command_sha256=COMPILE_SHA,
        historical_compile_book=str(BOOK), historical_compile_book_seal=BOOK_SHA,
        historical_runtime_plan=str(PLAN), historical_runtime_plan_seal=PLAN_SHA,
        original_software_review=str(REVIEW), original_software_review_seal=REVIEW_SHA,
        runtime_files_checked=66, predecessor_sha256=FROZEN_SHA,
        later_runtime_must_recheck_same_66=True, raw_gain_must_use_latest_formal_population=True,
        software_reference_is_not_DUT_qualification=True)
    life.check(receipt['pins'])
    return receipt


def build(out):
    previous = frozen.static
    try:
        frozen.static = static
        frozen.build(out)
    finally:
        frozen.static = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('static', 'build'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'build':
        build(out)
    else:
        require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct receipt required')
        receipt = static()
        life.save(out, receipt)
        print('STATIC_ONLY_NO_SOFTWARE_TOOLS_NO_VCS seal=' + life.digest(out))


if __name__ == '__main__':
    main()
