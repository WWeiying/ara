// SPDX-License-Identifier: SHL-0.51
#ifndef NARROW_CLIP_REJECT_REFERENCE_H
#define NARROW_CLIP_REJECT_REFERENCE_H
#include "narrow_reject_r1_reference.h"
#define NC_CASES 17
#define NC_PHASES 3
#define NC_CHECKS (NC_PHASES * 32 * 18 + NC_CASES * 21 + 9)
#define NC_MATRIX(X) \
  X(00,"e8, m1",0,0xba9c0857) \
  X(01,"e8, m1",0,0xbe9c0857) \
  X(02,"e8, m2",1,0xbeac0857) \
  X(03,"e8, m4",2,0xbecc0857) \
  X(04,"e8, m1",0,0xba93c857) \
  X(05,"e8, m4",2,0xbac3c857) \
  X(06,"e8, m8",3,0xba83c857) \
  X(07,"e8, m1",0,0xbe93c857) \
  X(08,"e8, m8",3,0xbe83c857) \
  X(09,"e64, m1",24,0xba80b857) \
  X(10,"e8, m2",1,0xbaa0b857) \
  X(11,"e8, m4",2,0xbac0b857) \
  X(12,"e8, m8",3,0xba80b857) \
  X(13,"e8, m1",0,0xbe90b857) \
  X(14,"e8, m2",1,0xbea0b857) \
  X(15,"e8, m4",2,0xbec0b857) \
  X(16,"e8, m8",3,0xbe80b857)
#endif
