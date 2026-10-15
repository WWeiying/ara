extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int extension_e64_m4_vf4_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 5;
replay_text("BOARD_CASE_BEGIN extension_e64_m4_vf4\n");
if (extension_e64_m4_vf4_main()) { replay_text("BOARD_CASE_FAIL extension_e64_m4_vf4\n"); return 5; }
replay_text("BOARD_CASE_PASS extension_e64_m4_vf4\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
