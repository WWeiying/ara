import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import struct
from unittest.mock import patch

from analyze_loader_stall import IMAGE_SHA256, inspect_page, inspect_task_capture, jal_target
from run_loader_cache_chain import capture_fixture


class LoaderStallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.page = bytes(range(256)) * 16
        core = {"retired": 10, "last_pc": 0x11b4a, "head_pc": 0x11b32,
                "trap_count": 2, "cycles": 100}
        self.report = {"code_sha256": hashlib.sha256(self.page).hexdigest(),
                       "memory_writes": False, "reset": False,
                       "before": {"core": core, "ddr1": {"ar_count": 20}},
                       "after": {"core": dict(core, cycles=200),
                                 "ddr1": {"ar_count": 21}},
                       "page_walk": [{"level": 0, "pte": "0x2005985b"}],
                       "code_va": "0x3f93ee2000", "pc_pa": "0x801660dc",
                       "reads": [{"data": "00" * 8}]}
        (self.path / "code_page.bin").write_bytes(self.page)

    def inspect(self, loader=None):
        (self.path / "report.json").write_text(json.dumps(self.report))
        return inspect_page(self.path, self.page if loader is None else loader)

    def test_jal_negative_real_instruction(self):
        self.assertEqual(jal_target(0x3f93ee6b4a, 0xd92fb0ef), 0x3f93ee20dc)

    def test_jal_positive(self):
        self.assertEqual(jal_target(0x1000, 0x008000ef), 0x1008)

    def test_not_jal(self):
        with self.assertRaises(ValueError):
            jal_target(0x1000, 0x13)

    def test_valid_capture(self):
        self.assertTrue(self.inspect()[2]["reads_account_for_ar_delta"])

    def test_changed_execution(self):
        self.report["after"]["core"]["retired"] += 1
        with self.assertRaisesRegex(ValueError, "Execution changed"):
            self.inspect()

    def test_corrupt_page(self):
        (self.path / "code_page.bin").write_bytes(bytes(4096))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.inspect()

    def test_ambiguous_match(self):
        with self.assertRaisesRegex(ValueError, "uniquely"):
            self.inspect(self.page * 2)

    def test_unexecutable_page(self):
        self.report["page_walk"][0]["pte"] = "0x20059853"
        with self.assertRaisesRegex(ValueError, "executable"):
            self.inspect()

    def test_physical_mismatch(self):
        self.report["pc_pa"] = "0x801670dc"
        with self.assertRaisesRegex(ValueError, "physical address"):
            self.inspect()

    def test_extra_traffic_is_not_cpu_progress_proof(self):
        self.report["after"]["ddr1"]["ar_count"] += 1
        self.assertFalse(self.inspect()[2]["reads_account_for_ar_delta"])


class TaskCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        loader = bytearray(b''.join(bytes([i])*4096 for i in range(18)))
        struct.pack_into('<I', loader, 0x11b4a, 0xd92fb0ef)
        self.loader = bytes(loader)
        self.patch_hash = patch('analyze_loader_stall.LOADER_SHA256', hashlib.sha256(loader).hexdigest())
        self.patch_hash.start()
        self.addCleanup(self.patch_hash.stop)
        base = 0x3f869ce000
        core = dict(retired=10, last_pc=base+0x11b4a, head_pc=base+0x11b32,
                    trap_count=2, cycles=100)
        snap = dict(core=core, watchdog_snapshot=False, ddr1=dict(ar_count=20, last_ar_addr=0x820007e0))
        self.report = dict(evidence_verified=True, memory_writes=False, reset=False, cpu_halt=False,
                           counter_frozen_before=0, counter_frozen_after=0, task_unchanged=True,
                           image_sha256=IMAGE_SHA256, task_va='0xffffffd602800000', task_comm='cp',
                           pgd_va='0xffffffd602000000', jal_target=hex(base+0xd0dc),
                           before=snap, second=dict(snap, core=dict(core, cycles=200)),
                           after=dict(snap, core=dict(core, cycles=300)), reads=[], pages=[],
                           pte_cache_lines=[])
        task = bytearray(4096)
        task[1696:1699] = b'cp\0'
        (self.path/'task.bin').write_bytes(task)
        self.record(0x82800000, task)
        lines = {}
        for label, offset, pa in (('retired_page', 0x11b4a, 0x8016ab4a),
                                   ('target_page', 0xd0dc, 0x801660dc)):
            va = base + offset
            entries = []
            for level, table, dest in ((2, 0x82000000, 0x82001000),
                                       (1, 0x82001000, 0x82002000),
                                       (0, 0x82002000, pa & ~4095)):
                addr = table + ((va >> (12+9*level)) & 511)*8
                pte = ((dest >> 12) << 10) | (0x5b if level == 0 else 1)
                entries.append(dict(level=level, pa=hex(addr), pte=hex(pte)))
                self.record(addr, struct.pack('<Q', pte))
                line = lines.setdefault(addr & ~31, bytearray(32))
                struct.pack_into('<Q', line, addr & 31, pte)
            data = self.loader[offset & ~4095:(offset & ~4095)+4096]
            (self.path/(label+'.bin')).write_bytes(data)
            self.record(pa & ~4095, data)
            self.report['pages'].append(dict(label=label, requested_va=hex(va), pa=hex(pa),
                                              page_walk=entries, sha256=hashlib.sha256(data).hexdigest()))
        for addr, data in lines.items():
            self.record(addr, data)
            self.report['pte_cache_lines'].append(dict(pa=hex(addr), data=data.hex()))

    def record(self, pa, data):
        self.report['reads'].append(dict(pa=hex(pa), data=data.hex()))

    def save(self):
        (self.path/'report.json').write_text(json.dumps(self.report))

    def test_valid_and_fixture(self):
        self.save()
        _, result = inspect_task_capture(self.path, self.loader)
        self.assertEqual(result['task'], 'cp')
        self.assertEqual(result['target_offset'], '0xd0dc')
        loader = self.path/'loader'
        loader.write_bytes(self.loader)
        output = capture_fixture(self.path, loader, self.path)
        self.assertEqual(len(output.read_text().splitlines()), 19)

    def test_frozen_rejected(self):
        self.report['counter_frozen_before'] = 1
        self.save()
        with self.assertRaises(ValueError):
            inspect_task_capture(self.path, self.loader)

    def test_walking_pointer_mismatch(self):
        self.report['pages'][0]['page_walk'][0]['pa'] = '0x82000000'
        self.save()
        with self.assertRaisesRegex(ValueError, 'walk address'):
            inspect_task_capture(self.path, self.loader)

    def test_pte_line_mutation_rejected(self):
        self.report['pte_cache_lines'][0]['data'] = bytes(32).hex()
        self.save()
        loader = self.path/'loader'
        loader.write_bytes(self.loader)
        with self.assertRaises(ValueError):
            capture_fixture(self.path, loader, self.path)

    def test_retirement_change_rejected(self):
        self.report['after']['core']['retired'] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, 'Execution changed'):
            inspect_task_capture(self.path, self.loader)

    def test_cleanup_failure_is_not_hardware_diagnosis(self):
        self.report['error'] = 'Owned Vivado tree cleanup failed: exit race'
        self.save()
        _, summary = inspect_task_capture(self.path, self.loader)
        self.assertIn('cleanup', summary['cleanup_error'])
        self.report['error'] = 'memory read failed'
        self.save()
        with self.assertRaises(ValueError):
            inspect_task_capture(self.path, self.loader)


if __name__ == "__main__":
    unittest.main()
