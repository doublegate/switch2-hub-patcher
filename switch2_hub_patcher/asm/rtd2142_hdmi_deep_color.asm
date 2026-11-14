; RTD2142 bank 2, HDMI TX deep colour. CANDIDATE, not yet hardware-tested.
;
; Stock bug: hdmi_set_deep_color (E8FF) programs 5B07[7:4] (dp_color_depth) only for
; 10/12-bit input. Its 8-bit branch (E952) clears the 5B06 packing bits but leaves the old
; depth, so after 12-bit HDR the register keeps 0x6_ in SDR. A fresh start has 0 there.
;
; Hook (checked by patch_rtd2142_sdr_fix.py):
;   E952  mov dptr,#0x5b06  ->  ljmp hdmi_deep_color_off
;
; hdmi_deep_color_off does what the stock branch did (5B06 &= 0xFC), also clears
; 5B07[7:4], keeps dp_last_phase (5B07[3:0]), and rejoins the stock code at E959.
; Placed below the BT.2020 overlay (FF80) so both can be applied. No new RAM.

.module rtd2142_hdmi_deep_color
.area HDMIDC (ABS,CODE)
.org 0xff00

hdmi_deep_color_off::
    mov dptr,#0x5b06        ; HDMI_CONTROL_6
    movx a,@dptr
    anl a,#0xfc             ; stock: deep-colour packing off
    movx @dptr,a
    inc dptr                ; HDMI_CONTROL_7 (5B07)
    movx a,@dptr
    anl a,#0x0f             ; dp_color_depth = 0 (8-bit), keep dp_last_phase
    movx @dptr,a
    ljmp 0xe959             ; stock continues: 5B04 bit 7, ret
