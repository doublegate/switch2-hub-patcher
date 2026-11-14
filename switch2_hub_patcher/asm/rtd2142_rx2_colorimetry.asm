; RTD2142 bank 5, DP RX stream 2 (the hub's input). CANDIDATE v2, not yet tested on a hub.
;
; Stock bug: in HDR the source signals colorimetry in the VSC SDP (MSA MISC1 bit 6 set) and
; rx2_colorimetry_from_vsc (C37B) stores a colorimetry code in E3E6[4:0] (BT.2020 YCbCr =
; 0x0E). That code is written by nothing else: the MISC0 path (rx2_colorimetry_from_misc0,
; D284) stores its result in E3E7, and only a power-up clears E3E6. After an HDR -> SDR
; switch (MISC1 bit 6 clear, MISC0 = BT.709) the HDMI side keeps reading the stale code, so
; the AVI InfoFrame says BT.2020 over SDR video with an SDR-gamma HDR packet; TVs flip between
; SDR, HDR and HLG. DP 1.4a Table 2-96: with MISC1 bit 6 clear, MISC0 is authoritative.
;
; Hook (checked by patch_rtd2142_sdr_fix.py):
;   C476  mov dptr,#0xb403  ->  ljmp rx2_fmt_check   (rx2_format_matches_q, polled)
;
; rx2_fmt_check: with MISC1 bit 6 clear, a non-zero E3E6[4:0] can only be left over from the
; VSC SDP. Clear it (the power-up value, which gives a stable, correct picture) and report a
; format change (C = 0) so the firmware's own setup path rebuilds the output from MISC0. Then
; the condition is false and the stock check runs as before. No new RAM; A, C, DPTR only.

.module rtd2142_rx2_colorimetry
.area RX2COL (ABS,CODE)
.org 0xfd80

rx2_fmt_check::
    mov dptr,#0xb403        ; MN_STRM_ATTR_MISC1 (stream 2)
    movx a,@dptr
    jb acc.6,rx2_stock      ; colorimetry in the VSC SDP: stock check
    mov dptr,#0xe3e6        ; rx2_colorimetry_code
    movx a,@dptr
    anl a,#0x1f
    jz rx2_stock_b403       ; no VSC code left over: stock check
    movx a,@dptr
    anl a,#0xe0             ; keep [7:5], clear the stale code
    movx @dptr,a
    clr c                   ; report a format change
    ret
rx2_stock_b403:
    mov dptr,#0xb403
rx2_stock:
    ljmp 0xc479             ; stock continues: movx a,@dptr with DPTR = B403
