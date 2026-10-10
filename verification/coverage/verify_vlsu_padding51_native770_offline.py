"""Read-only exact four width1-port aliases; never alters original failed evidence."""
import argparse
import copy
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import vlsu_address_padding_native770 as frozen

life, require = frozen.life, frozen.require
RUN = life.OUT / 'vlsu-address-padding51-native770-agent-20261007-02'
SEAL = 'bb0fad46532f16abe55da63f4522bbeb92f6d83dda5e6e0767a01ee89b7509c7'
PREFIX = frozen.proof.PREFIX
ALIASES = {
    PREFIX+'i_addrgen': {'axi_ar_o.user': '3', 'axi_aw_o.user': '3'},
    PREFIX+'i_vstu': {'axi_b_i.user': '2', 'axi_w_o.user': '3'},
}


def audit(instance, stages):
    allowed = ALIASES.get(instance['scope'], {})
    before = frozen.native.native_rows(stages['before'])
    replacement = {}
    for name, role in allowed.items():
        shapes = [n for n in instance['protected_shape'] if n['name'] == name]
        require(len(shapes) == 1 and shapes[0]['tag'] == 'vectornode' and
                shapes[0]['left'] == shapes[0]['right'] == '0' and shapes[0]['type'] == '1' and
                shapes[0]['portnode'] == role and shapes[0]['excluded'] == '0', 'Not exact protected width1 port')
        old = name+'[0:0]'
        require(instance['all_typed_labels'].count(old) == 1 and name not in instance['all_typed_labels'] and
                name not in {s['name'] for s in instance['signals']}, 'Alias collision/target')
        require(name in before and old not in before and name+'[0]' not in before, 'Actual scalar alias not unique')
        row = before[name]
        require(row['path'] == row['meta'] == name and row['type'] == 'port', 'Native role/path/meta differs')
        for stage in ('selected','reset','reloaded','final'):
            rows = frozen.native.native_rows(stages[stage])
            require(rows.get(name) == row, 'Protected alias full row changed: '+stage)
        replacement[old] = name
    modified = copy.deepcopy(instance)
    modified['all_typed_labels'] = [replacement.get(name, name) for name in instance['all_typed_labels']]
    norm = frozen.native.normalized_label
    expected = [norm(name) for name in modified['all_typed_labels']]
    actual = [norm(name) for name in before]
    require(len(expected) == len(set(expected)) and len(actual) == len(set(actual)) and
            set(expected) == set(actual), 'Full compiled/native inventory not bijective')
    # Existing audit retains every actual row, target identity, protected percentages,
    # reset/final restoration, and selected/reloaded equality. Only four required labels differ.
    return frozen.native.audit_native(modified, stages)


def verify(output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh separate qualification output')
    captured = []
    def capture(path, value):
        require(Path(path) == RUN/'capture-result.json', 'Unexpected write by frozen verifier')
        captured.append(value)
    private_life = SimpleNamespace(**{**vars(life), 'save': capture})
    private_native = SimpleNamespace(**{**vars(frozen.native), 'audit_native': audit})
    FunctionType(frozen.verify.__code__, {**vars(frozen), 'life':private_life, 'native':private_native})(RUN, SEAL)
    require(len(captured) == 1, 'Frozen verifier did not complete')
    result = captured[0]
    require(sum(n[0] for n in result['native_inventory_counts']) == 1404 and
            sum(n[1] for n in result['native_inventory_counts']) == 1353, 'Exact inventory boundary')
    result.update(status='VLSU_PADDING51_6528_NATIVE_OFFLINE_REVERIFIED_NOT_APPLIED',
                  original_run=str(RUN), original_Python_verifier='FAILED_WIDTH1_LABEL_BINDING',
                  original_DVE_returncode=0, original_service_success_claimed=False,
                  exact_width1_port_aliases={scope:{name+'[0:0]':name for name in names} for scope,names in ALIASES.items()},
                  arrays_flattened=False, low64_protection='Exact exported both-direction EL coordinates plus reset/full complement audits')
    for module in (frozen, frozen.native):
        path=Path(module.__file__).resolve(); result['pins'][str(path)]=life.digest(path)
    for name in ('verify_vlsu_padding51_native770_offline.py','test_verify_vlsu_padding51_native770_offline.py'):
        path=Path(__file__).with_name(name); result['pins'][str(path)]=life.digest(path)
    life.check(result['pins'])
    output.mkdir(); life.save(output/'qualification.json',result)
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification.json'),status=result['status'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.output.resolve())
