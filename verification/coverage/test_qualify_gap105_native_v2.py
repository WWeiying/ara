"""Fixture-only successor: vector CSV wdata is bare hex, not Python hex()."""
import unittest
import test_qualify_gap105_native as frozen


class CSVIntegration(frozen.CSVIntegration):
    def execute(self):
        for row in self.vector:
            if row['wdata'].startswith('0x'):
                row['wdata'] = format(int(row['wdata'],16),'016x')
        return super().execute()


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (frozen.Native,frozen.Readback,frozen.Writebacks,frozen.Software,CSVIntegration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__=='__main__': unittest.main()
