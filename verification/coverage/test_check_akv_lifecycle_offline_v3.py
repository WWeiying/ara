import copy
import unittest

import check_akv_lifecycle_offline_v3 as check


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre=check.life.read_bound(check.previous.runner.PRE/"preflight-manifest.json",check.previous.runner.PRE_SEAL)
        path=check.previous.runner.PRE/"target-before.json"
        cls.target=check.life.read_bound(path,pre["pins"][str(path)])
        design=check.Design(check.previous.native.common.DESIGN)
        cls.hierarchy=design.hierarchy[check.previous.fixture.SCOPE]
        cls.source=design.source(check.previous.fixture.SCOPE)
        cond=check.previous.fixture.shape.read_xml(design.db/"shape/cond.verilog.shape.xml")
        cls.definition=check.previous.fixture.shape.definition(cond,cls.hierarchy,"2836473276")
        cls.points=check.previous.fixture.shape.points("cond",cls.definition,392)
        engine=str(check.life.ROOT/"hardware/src/vlsu/akv/akv_engine.sv")
        cls.sources={engine:check.ENGINE_SHA}

    def bind(self, **updates):
        args=dict(hierarchy=copy.deepcopy(self.hierarchy),source=copy.deepcopy(self.source),
                  definition=self.definition,points=copy.deepcopy(self.points),
                  target=copy.deepcopy(self.target),sources=dict(self.sources))
        args.update(updates)
        return check.bind_compiled(**args)

    def test_actual_compiled_shape(self):
        result=self.bind()
        self.assertEqual(result["condition_width"],392)
        self.assertFalse(result["latest_population_bound"])
        self.assertFalse(result["coverage_admitted"])

    def test_v2_and_v3_tests_required(self):
        names={p.name for p in check.required_tests()}
        self.assertIn("test_check_akv_lifecycle_offline_v2.py",names)
        self.assertIn("test_check_akv_lifecycle_offline_v3.py",names)
        self.assertTrue(all(p.is_file() for p in check.required_tests()))

    def test_wrong_module_checksum(self):
        h=copy.deepcopy(self.hierarchy);h.set("chksum","0")
        with self.assertRaises(ValueError):self.bind(hierarchy=h)

    def test_wrong_metric_checksum(self):
        with self.assertRaises(ValueError):self.bind(definition={"chksum":"0"})

    def test_wrong_source_path(self):
        s=dict(self.source,resolved_path="/tmp/akv_engine.sv")
        with self.assertRaises(ValueError):self.bind(source=s)

    def test_wrong_source_bytes(self):
        with self.assertRaises(ValueError):self.bind(sources={p:"0"*64 for p in self.sources})

    def test_missing_source_pin(self):
        with self.assertRaises(ValueError):self.bind(sources={})

    def test_incomplete_shape(self):
        with self.assertRaises(ValueError):self.bind(points=self.points[:-1])

    def test_duplicate_coordinate(self):
        p=copy.deepcopy(self.points);p[-1]=p[0]
        with self.assertRaises(ValueError):self.bind(points=p)

    def test_wrong_vector(self):
        p=copy.deepcopy(self.points)
        next(r for r in p if r["raw_index"] == 194)["vector"]="0"
        with self.assertRaises(ValueError):self.bind(points=p)

    def test_wrong_expression(self):
        p=copy.deepcopy(self.points)
        next(r for r in p if r["raw_index"] == 194)["expression"]="other"
        with self.assertRaises(ValueError):self.bind(points=p)

    def test_wrong_fileid(self):
        p=copy.deepcopy(self.points)
        next(r for r in p if r["raw_index"] == 194)["file_id"]="0"
        with self.assertRaises(ValueError):self.bind(points=p)


if __name__ == "__main__":unittest.main()
