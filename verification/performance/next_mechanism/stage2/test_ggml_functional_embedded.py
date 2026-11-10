#!/usr/bin/env python3
"""Successor-only host contracts for the embedded build structure."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import run_ggml_functional_embedded as e


class EmbeddedTests(unittest.TestCase):
    def test_parent_config_uses_embedded_source_and_explicit_binary(self):
        text = e.parent_cmake('/frozen/ggml', '/fresh/build/frozen-ggml')
        self.assertIn('project(stage2_ggml_functional C CXX ASM)', text)
        self.assertIn('add_subdirectory("/frozen/ggml" "/fresh/build/frozen-ggml")', text)
        self.assertNotIn('GGML_STANDALONE', text)
        self.assertNotIn('ggml.pc', text)
        self.assertNotIn('find_package', text)

    def test_cmake_observes_embedded_mode_without_pc_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ggml = root/'frozen/ggml'; ggml.mkdir(parents=True)
            (ggml/'CMakeLists.txt').write_text(
                'if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)\n'
                ' message(FATAL_ERROR "unexpected standalone mode")\nendif()\n'
                'file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/embedded.txt" "yes")\n')
            parent = root/'parent'; parent.mkdir(); binary = root/'build/frozen-ggml'
            (parent/'CMakeLists.txt').write_text(e.parent_cmake(ggml, binary))
            result = subprocess.run(['cmake', '-S', parent, '-B', root/'build'],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual((binary/'embedded.txt').read_text(), 'yes')
            self.assertFalse((ggml/'ggml.pc.in').exists())

    def test_unique_libraries_are_layout_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = []
            for i, name in enumerate(e.LIBRARIES):
                path = root/f'child/variant{i}'/name; path.parent.mkdir(parents=True)
                path.write_bytes(b'archive'); expected.append(path)
            self.assertEqual(e.unique_libraries(root), expected)

    def test_missing_library_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): e.unique_libraries(tmp)

    def test_duplicate_library_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in e.LIBRARIES: (root/name).write_bytes(b'a')
            duplicate = root/'other'; duplicate.mkdir()
            (duplicate/e.LIBRARIES[0]).write_bytes(b'b')
            with self.assertRaises(ValueError): e.unique_libraries(root)

    def test_paths_cannot_inject_cmake(self):
        with self.assertRaises(ValueError): e.parent_cmake('/frozen/ggml";', '/fresh/build')

    def test_sealed_execution_and_four_arm_contracts_are_reused(self):
        self.assertEqual(e.v1.check.ARMS, ('m8', 'm4', 'shape', 'rvv'))
        self.assertIn('p.wait(timeout=600)', (e.HERE/'run_ggml_functional.py').read_text())
        self.assertIn("'--target', 'ggml', '-j4'], timeout=1800", (e.HERE/e.NEW[0]).read_text())
        self.assertIn('v1.execute(args.output.resolve())', (e.HERE/e.NEW[0]).read_text())


if __name__ == '__main__': unittest.main()
