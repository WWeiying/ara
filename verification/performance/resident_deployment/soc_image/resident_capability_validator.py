"""Successor index-4 contract; no changes to the inherited all-on/dependency gates."""
import importlib.util
from pathlib import Path
import re

WORD = 0x0000040000040301
LEGACY = (0x000F010808400101, 0x6B1A5B, 0x000001FF06084002, 0x1803E5B)
DISCOVERY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/'
                 'resident_deployment_discovery_20261112_020612')
DISCOVERY_REVIEW = '70146a39a651bb8fa7b6eaea5a3afda8fc8365f4339ab46f657b3159a2c33cbf'
DISCOVERY_RESULT = 'f68fe4e8482fe34133ab5038638100d81c0e8d213745e898fa6e2b3a37bd060a'
CAP_FILES = ('config/akv_abi.json', 'scripts/gen_akv_abi.py', 'hardware/include/akv_pkg.sv')


def validate(source, b):
    b.verify({DISCOVERY/'source-pins.json': DISCOVERY_REVIEW,
              DISCOVERY/'result.json': DISCOVERY_RESULT})
    result = b.read(DISCOVERY/'result.json')
    b.require(result['state'] == 'PASS' and result['sv_to_sdk_vectors'] == 1920 and
              result['legacy_words_unchanged'] is True and result['reference_resident_off'] is True,
              'Discovery predecessor is not the accepted successor')
    pins = b.read(DISCOVERY/'source-pins.json')
    for name in CAP_FILES:
        frozen = DISCOVERY/'inputs'/name
        b.require(pins[str(frozen)] == b.sha(source/name) == b.sha(frozen),
                  'Non-discovery capability overlay: '+name)
    spec = importlib.util.spec_from_file_location('resident_image_abi', source/'scripts/gen_akv_abi.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    abi = generator.load_spec()
    generator.validate_spec(abi)
    b.require(generator.sv_package(abi) == (source/'hardware/include/akv_pkg.sv').read_text(),
              'Generated package differs from the single-source ABI')
    words = {name: value for name, _, value in generator.resident_capability_words(abi)}
    b.require(words['BASE_WORD'] | words['SUPPORT_MASK'] == WORD,
              'Wrong Resident index-4 word')
    dispatcher = (source/'hardware/src/ara_dispatcher.sv').read_text()
    gates = {
        'akv_implementation_supported': 'AkvEnable && NrLanes == 4 && VLEN == 1024',
        'akv_v2_implementation_supported': 'akv_implementation_supported && AkvV2Enable',
        'akv_resident_pv_implementation_supported':
            'akv_v2_implementation_supported && AkvResidentPvEnable && RVVH(FPUSupport)',
        'akv_resident_qk_implementation_supported':
            'akv_resident_pv_implementation_supported && AkvResidentQkEnable && RVVF(FPUSupport)',
    }
    for name, expected in gates.items():
        matches = re.findall(r'\b'+name+r'\s*=\s*([^;]+);', dispatcher)
        b.require(len(matches) == 1 and ' '.join(matches[0].split()) == expected,
                  'Actual implementation gate changed: '+name)
    for kind in ('pv', 'qk'):
        b.require(re.search(r'akv_resident_'+kind+r'_capability_word\(\s*'
                            r"64'\(acc_req_i.rs1\),\s*akv_resident_"+kind+
                            r'_implementation_supported\)', dispatcher),
                  'Dispatcher is not discovering actual '+kind+' support')
    top = (source/'hardware/src/ara.sv').read_text()
    b.require(len(re.findall(r'\.FPUSupport\s*\(FPUSupport\s*\)', top)) == 2,
              'Top FPUSupport forwarding drift')
    # The actual frozen SoC must instantiate FP16+FP32, not just a capable package.
    system = (source/'hardware/src/ara_system.sv').read_text()
    b.require('FPUSupportHalfSingleDouble' in system, 'Reaudit SoC FPU instantiation')
