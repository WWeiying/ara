"""Identity and link gates for the isolated SDK dispatch model experiment."""
import json
from pathlib import Path

from audit import digest, require
from build_sdk_dispatch_library import compare_member_archives
from build_trace_context_library import archive_members

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
RUNS = VERIFY / 'verification/out'
PRIOR = RUNS / 'e2e_trace_context_model_pair_20261106_01'
LIBRARY = RUNS / 'e2e_sdk_dispatch_library_20261106_01/attempt-02'
MODEL = RUNS / 'e2e_output_model_20261106_01'
RECEIPT = ROOT / 'verification/performance/evidence/trace_context_model_20261106_01/result.json'
RECEIPT_SHA = 'c0079fe778bbd4b69de8cfa57dc128add6e06125212222b4837ddc00d5124024'
LIBRARY_SHA = 'd335a23205c19f0f4e4e8e77b4160812a925b3e848cb967b4479b0a6f4d29c5f'


def read(path):
    return json.loads(Path(path).read_text())


def recipe(records, label):
    rows = [row['argv'] for row in records if row['label'] == label]
    require(len(rows) == 1, 'Ambiguous command: ' + label)
    return list(rows[0])


def relink(command, model_object, old_archive, new_archive, old_output, new_output):
    require(command.count(str(model_object)) == command.count(str(old_archive)) ==
            command.count(str(old_output)) == command.count('-o') == 1, 'Ambiguous model link')
    require(command.index('-o') + 1 < len(command) and
            command[command.index('-o') + 1] == str(old_output), 'Wrong old output')
    return [str(new_archive) if value == str(old_archive) else str(new_output)
            if i == command.index('-o') + 1 else value for i, value in enumerate(command)]


def guest_listing(init, baseline, candidate, driver):
    paths = (init, baseline, candidate, driver)
    require(all(p.is_absolute() and not any(c.isspace() for c in str(p)) for p in paths),
            'Unsafe guest source path')
    prefix = 'dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'
    return prefix + ''.join(f'file /{guest} {path} 755 0 0\n' for guest, path in
                            zip(('init', 'base', 'candidate', 'test'), paths))


def accepted_inputs(pin):
    pin(RECEIPT, RECEIPT_SHA)
    receipt = read(RECEIPT)
    require(receipt['state'] == 'TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED', 'Prior model acceptance')
    audit_root = Path(receipt['run'])
    pin(audit_root / 'result.json', receipt['result_sha256'])
    audited = read(audit_root / 'result.json')['report']
    require(Path(audited['run']) == PRIOR, 'Prior worker identity')
    pin(PRIOR / 'result.json', receipt['worker_result_sha256'])
    pin(PRIOR / 'source-pins.json', receipt['source_pins_sha256'])
    prior = read(PRIOR / 'result.json')
    old = read(PRIOR / 'source-pins.json')
    require(prior['measured'] == audited['measured'], 'Prior model replay binding')
    for name in ('commands.json', 'projection-schema.json', 'model.o', 'candidate', 'test', 'initramfs.list'):
        pin(PRIOR / name, prior['artifacts'][str(PRIOR / name)])
    for name, field in (('model.o', 'common_model_object_sha256'),
                        ('candidate', 'candidate_elf_sha256'), ('test', 'driver_elf_sha256')):
        require(digest(PRIOR / name) == prior[field], 'Prior compiled input identity')
    pin(LIBRARY / 'result.json')
    library = read(LIBRARY / 'result.json')
    require(library['state'] == 'SDK_DISPATCH_LIBRARY_BUILT_ARCHIVE_VERIFIED' and
            library['member'] == 'qbs_runtime.c.o' and library['original_object_reproduced_exactly'] and
            library['unchanged_other_members'] == 31 and library['members'] == 32 and
            library['compiled_translation_units'] == 2 and library['public_exports_unchanged'] and
            library['inventory_and_order_unchanged'] and library['original_library_unchanged'] and
            not library['production_changes'] and not library['target_executed'], 'SDK archive gate')
    require(library['baseline_library_sha256'] == receipt['candidate_library_sha256'] and
            library['candidate_library_sha256'] == LIBRARY_SHA, 'Accepted base/candidate archive identity')
    pin(LIBRARY / 'source-pins.json', library['source_pins_sha256'])
    for path, expected in read(LIBRARY / 'source-pins.json').items():
        pin(path, expected)
    for path, expected in library['artifacts'].items():
        require(Path(path).resolve().is_relative_to(LIBRARY), 'Escaping library artifact')
        pin(path, expected)
    for path, target in read(LIBRARY / 'path-identities.json').items():
        require(str(Path(path).resolve(strict=True)) == target, 'Library symlink drift')
    base, candidate = Path(library['baseline_library']), Path(library['candidate_library'])
    pin(base, receipt['candidate_library_sha256'])
    pin(candidate, LIBRARY_SHA)
    member = Path(library['candidate_object'])
    pin(member, library['candidate_object_sha256'])
    evidence = compare_member_archives(archive_members(base.read_bytes()), archive_members(candidate.read_bytes()),
                                       'qbs_runtime.c.o', member.read_bytes())
    require(evidence == read(LIBRARY / 'archive-members.json'), 'Archive member replay differs')
    return prior, old, library, audited['measured']
