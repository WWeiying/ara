extern void replay_text(const char *);
extern volatile unsigned long replay_case;
extern int changed_vl_main(void);
int main(void) {
unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case = 3;
replay_text("BOARD_CASE_BEGIN changed_vl\n");
if (changed_vl_main()) { replay_text("BOARD_CASE_FAIL changed_vl\n"); return 3; }
replay_text("BOARD_CASE_PASS changed_vl\n");
replay_text("BOARD_REPLAY_PASS\n"); return 0;
}
