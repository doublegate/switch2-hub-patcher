; RTD2142 bank 2, HDMI TX HDR (DRM, type 87h) packet. CANDIDATE (SDR-fix v5), not yet tested.
;
; Stock behaviour: hdmi_drm_update (F2E6) keeps the HDR packet enabled (5B6B bit 5,
; pr_spkt3_en) whenever the DP source sends HDR metadata, whatever its EOTF. In SDR, macOS
; keeps sending all-zero metadata (EOTF 0, "traditional gamma"), so the TV receives an SDR
; HDR packet forever; a source on HDMI stops it after 2 s (CTA-861-H). Also, every output
; restart enables all packets at once (hdmi_pkt_enable_all, CDAA: 5B6B |= FC), so the TV
; briefly gets the previous mode's metadata (PQ after HDR -> SDR) before it is rebuilt.
;
; Hook (checked by patch_rtd2142_sdr_fix.py):
;   F31F  lcall 4ae7 (then orl a,#20 / movx / ret)  ->  ljmp hdmi_drm_enable_guard
; plus a byte patch at CDB1 (orl #FC -> #DC) so a restart leaves bit 5 off until this
; guard turns it on with the rebuilt packet.
;
; hdmi_drm_enable_guard: send the HDR packet only when the metadata's EOTF (DD9F[2:0],
; rx_drm_eotf_p1) is non-zero (PQ 2, HLG 3, ...); with EOTF 0 keep it off. No new RAM.

.module rtd2142_hdmi_drm
.area HDMIDRM (ABS,CODE)
.org 0xff20

hdmi_drm_enable_guard::
    mov dptr,#0xdd9f        ; rx_drm_eotf_p1: [2:0] EOTF of the source's HDR metadata
    movx a,@dptr
    anl a,#0x07
    mov dptr,#0x5b6b        ; DATA_ISLAND_PACKETIZER_54: bit 5 = HDR packet enable
    jz hdmi_drm_off         ; EOTF 0 (SDR gamma): do not send the packet
    movx a,@dptr
    orl a,#0x20             ; stock: HDR packet on
    movx @dptr,a
    ret
hdmi_drm_off:
    movx a,@dptr
    anl a,#0xdf
    movx @dptr,a
    ret
