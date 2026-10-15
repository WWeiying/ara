extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int extension_e16_m2_vf2_main(void);
extern int extension_e32_m2_vf2_main(void);
extern int extension_e64_m2_vf2_main(void);
extern int extension_e32_m4_vf4_main(void);
extern int extension_e64_m4_vf4_main(void);
extern int extension_e64_m8_vf8_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 1;
replay_text("BOARD_CASE_BEGIN extension_e16_m2_vf2\n");
if (extension_e16_m2_vf2_main()) { replay_text("BOARD_CASE_FAIL extension_e16_m2_vf2\n"); return 1; }
replay_text("BOARD_CASE_PASS extension_e16_m2_vf2\n");
replay_case = 2;
replay_text("BOARD_CASE_BEGIN extension_e32_m2_vf2\n");
if (extension_e32_m2_vf2_main()) { replay_text("BOARD_CASE_FAIL extension_e32_m2_vf2\n"); return 2; }
replay_text("BOARD_CASE_PASS extension_e32_m2_vf2\n");
replay_case = 3;
replay_text("BOARD_CASE_BEGIN extension_e64_m2_vf2\n");
if (extension_e64_m2_vf2_main()) { replay_text("BOARD_CASE_FAIL extension_e64_m2_vf2\n"); return 3; }
replay_text("BOARD_CASE_PASS extension_e64_m2_vf2\n");
replay_case = 4;
replay_text("BOARD_CASE_BEGIN extension_e32_m4_vf4\n");
if (extension_e32_m4_vf4_main()) { replay_text("BOARD_CASE_FAIL extension_e32_m4_vf4\n"); return 4; }
replay_text("BOARD_CASE_PASS extension_e32_m4_vf4\n");
replay_case = 5;
replay_text("BOARD_CASE_BEGIN extension_e64_m4_vf4\n");
if (extension_e64_m4_vf4_main()) { replay_text("BOARD_CASE_FAIL extension_e64_m4_vf4\n"); return 5; }
replay_text("BOARD_CASE_PASS extension_e64_m4_vf4\n");
replay_case = 6;
replay_text("BOARD_CASE_BEGIN extension_e64_m8_vf8\n");
if (extension_e64_m8_vf8_main()) { replay_text("BOARD_CASE_FAIL extension_e64_m8_vf8\n"); return 6; }
replay_text("BOARD_CASE_PASS extension_e64_m8_vf8\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
