"""Host-only adapter mutation tests. Mock cycles are not performance evidence."""
from pathlib import Path
import struct
import unittest

from contract import ROOT, module
from prepare import f16_slice, quant_driver, fixture
from check import check_f16, native_sequence, check_quant, activity, successful_log


def f16_log():
    f = dict(kind="f16",queries=4,first_query=16,outputs=1024,visible_prefixes=[17,18,19,20])
    lines = ["EXT_PREFILL_CAP queries=4 first=16 heads=2 kvheads=1 d=128 capacity=256 trials=4 pair_pv=1"]
    seqno = 0
    for trial,mode in enumerate((0,1,1,0)):
        lines.append(f"EXT_PREFILL_BEGIN trial={trial} mode={mode}")
        for cmd in native_sequence(f) if mode else ():
            seqno += 1
            lines.append(f"[AKV_PERF] seq={seqno} command={cmd} success=1 fault=0 validation_fault=0 "
                         "validation_error=0 read_fault=0 busy_cycles=1 v2_rejected=0")
        lines.append(f"EXT_PREFILL_RESULT trial={trial} mode={mode} cycles=1 fcsr=1 vcsr=5 vstart=0 "
                     "guards=128 inputs=1 errors=0 hex="+"3f800000"*1024)
    lines += ["EXT_PREFILL_SUITE_PASS","Core Test *** SUCCESS *** (tohost = 0)"]
    return "\n".join(lines),struct.pack("<1024f",*([1.0]*1024)),f


class ExtensionsTest(unittest.TestCase):
    def test_f16_positive(self):
        text,gold,f = f16_log()
        self.assertEqual(check_f16(text,gold,f)["outputs_per_trial"],1024)
        self.assertEqual(activity(text,f),[0,204,204,0])
        successful_log(text)

    def test_f16_mutations(self):
        text,gold,f = f16_log()
        for old,new in (("inputs=1","inputs=0"),("guards=128","guards=0"),("vstart=0","vstart=1"),
                        ("vcsr=5","vcsr=0"),("fcsr=1","fcsr=32"),("cycles=1 fcsr","cycles=0 fcsr"),
                        ("3f800000","7fc00000"),("EXT_PREFILL_SUITE_PASS",""),
                        ("BEGIN trial=0 mode=0","BEGIN trial=0 mode=1")):
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_f16(text.replace(old,new,1),gold,f)
        for old,new in (("command=4","command=5"),("success=1","success=0"),
                        ("seq=1 ","seq=2 "),("v2_rejected=0","v2_rejected=1")):
            with self.subTest(old=old),self.assertRaises(ValueError):
                activity(text.replace(old,new,1),f)
        with self.assertRaises(ValueError): check_f16(text,gold[:-4],f)
        with self.assertRaises(ValueError): successful_log(text+"\nUVM_FATAL : 1")
        with self.assertRaises(ValueError): successful_log(text.replace("tohost = 0","tohost = 1"))
        with self.assertRaises(ValueError): successful_log(text+"\nCore Test *** SUCCESS *** (tohost = 0)")

    def test_slice_retains_k_and_exact_golden_coordinates(self):
        blobs = {"attn_q_input-0":bytes(range(256))*4352,
                 "attn_k_input-0":bytes(range(256))*2048,
                 "attn_v_input-0":bytes(range(255,-1,-1))*2048,
                 "attn_mask_input-0":bytes(69632),
                 "kqv_out-0":b"".join(struct.pack("<I",i) for i in range(278528))}
        data = f16_slice(blobs,16,4,3)
        self.assertEqual(len(data["query"]),4096)
        self.assertEqual(data["key"],blobs["attn_k_input-0"][3*65536:4*65536])
        self.assertEqual(data["golden"][:4],struct.pack("<I",(16*16+6)*128))
        self.assertEqual(len(data["mask"]),2048)
        with self.assertRaises(ValueError): f16_slice(blobs,135,4,0)

    def test_checked_quant_instrumentation_and_checker(self):
        prior = ROOT/"verification/akv/quantized_kv/prefill"
        source = (prior/"native_main.c").read_text()
        transformed = quant_driver(source)
        self.assertEqual(transformed.count('"csrr zero,cycle"'),2)
        self.assertEqual(transformed.count("fence rw,rw"),source.count("fence rw,rw"))
        with self.assertRaises(ValueError): quant_driver(source.replace("cycles()-start","cycles() - start"))
        checker = module(prior/"check_native.py","extensions_quant_unit_checker")
        lines = ["PREFILL_CAP q4=1 rows=8 d=128 first_query=16 tokens=20 trials=4"]
        for trial,shared in enumerate((0,1,1,0)):
            lines += [f"PREFILL_BEGIN trial={trial} shared={shared}",
                f"PREFILL_RESULT trial={trial} shared={shared} cycles=1 commands=4 "
                f"values={20 if shared else 74} fcsr=1 vcsr=5 errors=0 hex="+"3f800000"*1024]
        lines.append("PREFILL_SUITE_PASS")
        text,gold = "\n".join(lines),struct.pack("<40960f",*([1.0]*40960))
        for trial in range(4):
            text = text.replace(f"PREFILL_RESULT trial={trial}",
                f"EXT_QUANT_STATE trial={trial} vstart=0 inputs=1\nPREFILL_RESULT trial={trial}")
        self.assertEqual(check_quant(text,gold,1,checker)["outputs_per_trial"],1024)
        with self.assertRaises(ValueError): check_quant(text.replace("inputs=1","inputs=0",1),gold,1,checker)
        raw = []
        seq = 0
        for line in text.splitlines():
            raw.append(line)
            if line.startswith("PREFILL_BEGIN "):
                for n in range(17,21):
                    seq += 1
                    raw.append(f"[QBS_PERF] seq={seq} m=2 n={n} vlen=1024 lanes=4 success=1 fault=0 "
                        "validation_fault=0 validation_error=0 read_fault=0 busy_cycles=1")
        raw = "\n".join(raw)
        self.assertEqual(activity(raw,dict(kind="q4_0")),[4,4,4,4])
        with self.assertRaises(ValueError): activity(raw.replace("m=2","m=4",1),dict(kind="q4_0"))

    def test_real_capture_geometry(self):
        for kind in ("f16","q4_0","q8_0"):
            data,f = fixture(kind,16,4,0,lambda p:None)
            self.assertEqual(f["visible_prefixes"],[17,18,19,20])
            self.assertFalse(f["softmax_k_truncated"])
            self.assertEqual(len(data["golden"]),4096 if kind == "f16" else 163840)


if __name__ == "__main__":
    unittest.main()
