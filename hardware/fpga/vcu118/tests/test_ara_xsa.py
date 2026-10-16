from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ethernet"))
import check_ara_xsa as audit


def fixture():
    root = ET.Element("SYSTEM")
    modules = {}
    for group, expected, key in (("PARAMETERS", audit.PARAMETERS, "VALUE"),
                                  ("PORTS", audit.PORTS, "SIGNAME")):
        for name, values in expected.items():
            if name not in modules:
                modules[name] = ET.SubElement(root, "MODULE", INSTANCE=name)
            container = ET.SubElement(modules[name], group)
            for field, value in values.items():
                ET.SubElement(container, "PORT" if group == "PORTS" else "PARAMETER",
                              NAME=field, **{key: value})
    for name, pin, hz in (("clock", "clk_in1", "250000000"),
                           ("mb", "Clk", "100000000"),
                           ("ddr_fabric", "aclk", "300000000")):
        modules[name].find(f"PORTS/PORT[@NAME='{pin}']").set("CLKFREQUENCY", hz)
    return root


class XsaTests(unittest.TestCase):
    def test_expected(self):
        self.assertGreater(audit.check(fixture()), 25)

    def test_each_connection_and_parameter_is_required(self):
        for path in (".//PORT", ".//PARAMETER"):
            count = len(fixture().findall(path))
            for index in range(count):
                with self.subTest(path=path, index=index):
                    root = fixture()
                    field = "SIGNAME" if path.endswith("PORT") else "VALUE"
                    root.findall(path)[index].set(field, "unexpected")
                    with self.assertRaises(ValueError):
                        audit.check(root)

    def test_private_mig_rejected(self):
        root = fixture()
        ET.SubElement(root, "MODULE", INSTANCE="ddr", MODTYPE="ddr4")
        with self.assertRaisesRegex(ValueError, "private MIG"):
            audit.check(root)


if __name__ == "__main__":
    unittest.main()
