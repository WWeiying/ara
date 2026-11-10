#!/usr/bin/env python3
"""Host geometry and GNU object checks, not native QK execution acceptance."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-')
HELPER = ROOT/'software/akv/experimental/resident_attention'


class SdkHelper(unittest.TestCase):
    def test_geometry_exhaustive_and_invalid_arguments(self):
        code = r'''
#include "qk.h"
int main(void) {
  const unsigned dims[] = {0, 63, 64, 96, 128, 256, UINT32_MAX};
  for (unsigned t=0; t<=65; ++t)
    for (unsigned h=0; h<=3; ++h)
      for (unsigned d=0; d<sizeof(dims)/sizeof(dims[0]); ++d)
        for (unsigned b=0; b<=8; ++b)
          for (unsigned q=0; q<=9; ++q) {
            int expected = t>=1 && t<=64 && h>=1 && h<=2 &&
              (dims[d]==64 || dims[d]==96 || dims[d]==128) &&
              q<=8 && b+h<=q;
            if (akv_experimental_resident_qk_geometry(t,h,dims[d],b,q)!=expected)
              return 1;
          }
  if (akv_experimental_resident_qk_geometry(1,UINT32_MAX,64,1,8) ||
      akv_experimental_resident_qk_geometry(UINT32_MAX,1,64,1,8) ||
      akv_experimental_resident_qk_geometry(1,1,64,UINT32_MAX,8) ||
      akv_encode_resident_qk(0,10)!=0x0605705b ||
      akv_resident_qk_is_supported() || akv_resident_qk_capability_word(4,1))
    return 2;
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'geometry'
            subprocess.run(['/usr/bin/cc', '-x', 'c', '-std=c11', '-O2',
                '-Wall', '-Wextra', '-Werror', '-I'+str(HELPER),
                '-I'+str(ROOT/'software/akv/include'), '-', '-o', str(binary)],
                input=code, text=True, check=True, capture_output=True)
            subprocess.run([binary], check=True, timeout=10)

    def test_real_assembler_instruction_and_store_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            obj, raw = Path(directory)/'qk.o', Path(directory)/'qk.bin'
            subprocess.run([str(GNU)+'gcc', '-march=rv64gcv_zfh_zvfh',
                '-mabi=lp64d', '-c', str(HELPER/'qk.S'), '-o', str(obj)],
                check=True, capture_output=True, timeout=30)
            subprocess.run([str(GNU)+'objcopy', '-O', 'binary', '-j', '.text', obj, raw],
                check=True, capture_output=True, timeout=30)
            data = raw.read_bytes()
            self.assertEqual(len(data)%4, 0)
            words = struct.unpack('<'+'I'*(len(data)//4), data)
            custom = [word for word in words if word & 0x7f == 0x5b]
            self.assertEqual(custom, [0x0605705b])
            stores = [word for word in words if word & 0x7f == 0x27]
            self.assertEqual([(word>>7)&31 for word in stores], [0,2])
            self.assertTrue(all((word>>12)&7 == 6 for word in stores))
            self.assertTrue(all(word & 0x7f not in (0x07,0x53) for word in words))


if __name__ == '__main__':
    unittest.main()
