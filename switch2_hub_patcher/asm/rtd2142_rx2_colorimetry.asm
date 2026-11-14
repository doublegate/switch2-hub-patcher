; RTD2142 bank 5, DP RX stream 2 (the hub's input). CANDIDATE, not yet hardware-tested.
;
; Stock bug: after an HDR -> SDR switch the source clears MSA MISC1 bit 6 (colorimetry is
; in the VSC SDP) and describes SDR in MISC0, but the format captured during the switch
; came from the VSC SDP (BT.2020) and is never refreshed: the "format unchanged?" check
; (rx2_format_matches_q, C476) compares only the pixel encoding. The HDMI AVI InfoFrame
; then keeps saying BT.2020 YCbCr over SDR video and the TV keeps re-detecting.
; DP 1.4a Table 2-96: with MISC1 bit 6 clear, MISC0 is authoritative.
;
; Hook (checked by patch_rtd2142_sdr_fix.py):
;   C476  mov dptr,#0xb403  ->  ljmp rx2_fmt_check
;
; rx2_fmt_check reports "format changed" (C = 0) when MISC1 bit 6 is clear but the cached
; format came from the VSC SDP (flag 0x2E, set and cleared by rx2_capture_format DCF4).
; The firmware's own setup path then re-captures from MISC0, which clears the flag. In
; every other case it continues with the stock code. No new RAM; A, C and DPTR only.

.module rtd2142_rx2_colorimetry
.area RX2COL (ABS,CODE)
.org 0xfd80

rx2_fmt_check::
    mov dptr,#0xb403        ; MN_STRM_ATTR_MISC1 (stream 2)
    movx a,@dptr
    jb acc.6,rx2_stock      ; colorimetry in the VSC SDP: stock check
    jnb 0x2e,rx2_stock      ; cached format came from MISC0: stock check
    clr c                   ; MISC0 now, cache from VSC: report a format change
    ret
rx2_stock:
    ljmp 0xc479             ; stock continues: movx a,@dptr with DPTR = B403
