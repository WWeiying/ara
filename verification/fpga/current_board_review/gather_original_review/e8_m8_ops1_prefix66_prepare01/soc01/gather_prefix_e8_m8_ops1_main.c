extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int gather_prefix_e8_m8_ops1_main(void);
int main(void) { unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case=1; replay_text("BOARD_CASE_BEGIN gather_prefix_e8_m8_ops1\n");
if (gather_prefix_e8_m8_ops1_main()) { replay_text("BOARD_CASE_FAIL gather_prefix_e8_m8_ops1\n"); return 1; }
replay_text("BOARD_CASE_PASS gather_prefix_e8_m8_ops1\nBOARD_REPLAY_PASS\n"); return 0; }
