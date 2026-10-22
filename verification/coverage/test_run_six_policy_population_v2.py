from types import FunctionType
import unittest

import test_run_six_policy_population as legacy_tests
import run_six_policy_population_v2 as subject


class SuccessorLaunchTests(unittest.TestCase):
    pass


# Replay the exact11 one-shot tests with the successor namespace, no module patch.
for name, function in vars(legacy_tests.LaunchTests).items():
    if isinstance(function, FunctionType):
        copied = FunctionType(function.__code__, dict(function.__globals__, subject=subject),
                              function.__name__, function.__defaults__, function.__closure__)
        setattr(SuccessorLaunchTests, name, copied)


if __name__ == '__main__':
    unittest.main()
