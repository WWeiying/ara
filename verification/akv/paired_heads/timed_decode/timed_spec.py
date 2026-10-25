"""Timing-only successor of the sealed four-case native Decode fixture."""
import hashlib
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PAIRED = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(PAIRED))
import attention_run as s
import native_runtime_check as original_check
import run_live_regression as original_run

SOURCE = PAIRED / 'native_runtime_main.c'
SOURCE_SHA = '3e5700a22e67843406b40040045d22478d5b808a8fdc2505024c1cc498e88807'
SCHEMA = 'akv-timed-decode-v1'
IMAGE_GATE = ROOT / 'verification/out/qbacc-soc-accept-20261023-02'
ELF_TOOLS = ROOT / 'verification/akv/refill_overlap_probe/build.py'
CALL = '      const akv_status_t status = akv_attention_execute_v2_native(&plan,&workspace.data[0]);\n'
DRAIN = r'''      uintptr_t drain,fc,vc;
      __asm__ volatile("vmv.x.s %0, v12\nfence rw,rw\nfrcsr %1\ncsrr %2,vcsr"
                       : "=&r"(drain),"=&r"(fc),"=&r"(vc) : : "memory");
'''
TIMED_DRAIN = r'''      uintptr_t drain,fc,vc,cycle_end;
      __asm__ volatile("vmv.x.s %0, v12\nfence rw,rw\nrdcycle %1\nfrcsr %2\ncsrr %3,vcsr"
                       : "=&r"(drain),"=&r"(cycle_end),"=&r"(fc),"=&r"(vc) : : "memory");
'''
START = '      uintptr_t cycle_start;\n      __asm__ volatile("rdcycle %0" : "=r"(cycle_start) : : "memory");\n'
RESULT = '      printf("NATIVE_PAIR_RESULT case=%u trial=%u requested=%u outputs=%u compared=4096 hash=%016lx fcsr=%lu vcsr=%lu errors=%u\\n",\n'
TIMING = r'''      printf("NATIVE_PAIR_TIMING case=%u trial=%u start=%lu end=%lu cycles=%lu\n",
             c,trial,(unsigned long)cycle_start,(unsigned long)cycle_end,
             (unsigned long)(cycle_end-cycle_start));
'''
EDITS = ((CALL, START + CALL), (DRAIN, TIMED_DRAIN), (RESULT, TIMING + RESULT))


def inverse(text):
    for old, new in reversed(EDITS):
        s.require(text.count(new) == 1, 'Timed source anchor drift')
        text = text.replace(new, old, 1)
    s.require(hashlib.sha256(text.encode()).hexdigest() == SOURCE_SHA,
              'Inverse transform differs from sealed original source')
    return text


def render(text):
    s.require(hashlib.sha256(text.encode()).hexdigest() == SOURCE_SHA, 'Original main drift')
    for old, new in EDITS:
        s.require(text.count(old) == 1, 'Original source anchor drift')
        text = text.replace(old, new, 1)
    inverse(text)
    return text


def own_files():
    files = [*HERE.glob('*.py'), HERE/'README.md', SOURCE,
             Path(sys.executable).resolve(), *s.script_files(), ELF_TOOLS,
             ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                files.append(path)
    return sorted(set(files))
