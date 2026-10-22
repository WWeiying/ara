import json
import tempfile
import unittest
from pathlib import Path

from rerun_paired_campaign import ROOT, _retry_destination, make_plan, resume_plan, run


class RerunPairedCampaignTests(unittest.TestCase):
    def test_plan_records_22_runs_and_rejects_mutated_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "sim/simv"
            simv.parent.mkdir()
            simv.write_bytes(b"simulator")
            (simv.parent / "simv.daidir").mkdir()
            config = simv.parent / "simulator.conf"
            config.write_text("qbs=1\nakv_v2=1\nsim_l2_mb=16\n")
            pairs = []
            for index in range(10):
                item = {"format": "q4_K", "variant": f"case{index}"}
                for mode in ("qbs", "rvv"):
                    old = root / f"old{index}_{mode}"
                    (old / "work").mkdir(parents=True)
                    (old / "work/input.elf").write_bytes(f"elf{index}{mode}".encode())
                    app = root / f"app{index}_{mode}"
                    (app / "generated").mkdir(parents=True)
                    (app / "case.json").write_text("{}\n")
                    for name in ("source_weight.bin", "activation_f32.bin",
                                 "golden_f32.bin"):
                        (app / "generated" / name).write_bytes(name.encode())
                    item[f"{mode}_run"] = str(old)
                    item[f"{mode}_app"] = str(app)
                pairs.append(item)
            akv = {}
            for mode in ("rvv", "akv"):
                elf = root / f"akv_{mode}.elf"
                assembly = root / f"akv_{mode}.S"
                elf.write_bytes(mode.encode())
                assembly.write_text("nop\n")
                akv[f"{mode}_elf"] = str(elf)
                akv[f"{mode}_asm"] = str(assembly)
            source = root / "manifest.json"
            source.write_text(json.dumps({"schema_version": 1,
                                          "qbs_pairs": pairs, "akv_pair": akv}))
            output = root / "new"
            plan = make_plan(source, simv, output)
            self.assertEqual(len(plan["cases"]), 22)
            self.assertEqual(len(plan["output_manifest"]["qbs_pairs"]), 10)
            self.assertEqual(plan["source_root"], str(ROOT.resolve()))
            rooted_source = json.loads(source.read_text())
            for pair in rooted_source["qbs_pairs"]:
                for mode in ("rvv", "qbs"):
                    for key in (f"{mode}_run", f"{mode}_app"):
                        pair[key] = str(Path(pair[key]).relative_to(root))
            for mode in ("rvv", "akv"):
                for key in (f"{mode}_elf", f"{mode}_asm"):
                    rooted_source["akv_pair"][key] = str(
                        Path(rooted_source["akv_pair"][key]).relative_to(root))
            relative_source = root / "relative-manifest.json"
            relative_source.write_text(json.dumps(rooted_source))
            with self.assertRaises(FileNotFoundError):
                make_plan(relative_source, simv, output, root / "wrong-root")
            rooted_plan = make_plan(relative_source, simv, output, root)
            self.assertEqual(rooted_plan["source_root"], str(root.resolve()))
            self.assertEqual(rooted_plan["cases"][0]["elf"], plan["cases"][0]["elf"])
            self.assertEqual(rooted_plan["cases"][-1]["elf"], plan["cases"][-1]["elf"])
            config.write_text("qbs=0\nakv_v2=0\nsim_l2_mb=16\n")
            with self.assertRaisesRegex(ValueError, "both QBS and AKV-v2"):
                make_plan(source, simv, output)
            config.write_text("qbs=1\nakv_v2=1\nsim_l2_mb=16\n")

            output.mkdir()
            (output / "plan.json").write_text(json.dumps(plan))
            config.write_text("qbs=1\nakv_v2=1\nsim_l2_mb=8\n")
            with self.assertRaisesRegex(ValueError, "simulator_conf_sha256"):
                resume_plan(source, simv, output)
            config.write_text("qbs=1\nakv_v2=1\nsim_l2_mb=16\n")
            Path(plan["cases"][0]["elf"]).write_bytes(b"mutated")
            self.assertEqual(run(plan, output, simv, 900), 1)
            self.assertEqual(plan["status"], "FAIL")
            self.assertEqual(plan["cases"][0]["reason"],
                             "frozen input or runner hash changed")
            with self.assertRaisesRegex(ValueError, "resume case input differs"):
                resume_plan(source, simv, output)

    def test_retry_preserves_failed_artifacts_and_updates_pair_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            failed = output / "q3_K/rvv"
            failed.mkdir(parents=True)
            (failed / "console.log").write_text("timeout\n")
            case = {"name": "q3_K", "mode": "rvv", "output": str(failed),
                    "status": "FAIL", "returncode": 124}
            plan = {"output_manifest": {"qbs_pairs": [{}, {"rvv_run": str(failed)}],
                                        "akv_pair": {}}}
            destination = _retry_destination(case, output, plan, 2)
            self.assertEqual(destination, output / "q3_K/rvv.retry-1")
            self.assertEqual((failed / "console.log").read_text(), "timeout\n")
            self.assertEqual(plan["output_manifest"]["qbs_pairs"][1]["rvv_run"],
                             str(destination))
            self.assertEqual(case["attempts"][0]["returncode"], 124)


if __name__ == "__main__":
    unittest.main()
