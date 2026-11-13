# DP-port HDR and VRR: research notes

Status: **research only**. Nothing here is in the patch pipeline. Every register
below comes from the public Realtek tool database for the related **RTD2172**
(`roufsweb/portable-display`, `02_RTDCustomerTool_V3.8/RTDScaler/RTD2172/DB.bin`).
These are working assumptions for the RTD2142 until a real dump confirms them.

One check supports reusing it: the RTD2172 names page `0x5B` "HDMI2.0 Tx MAC0".
The registers that the shipped HDMI patch uses (`5B48`, `5B49`, `5B4B`, `5B6B`)
are its `DATA_ISLAND_PACKETIZER_19/20/22/54`. That matches what the patch does to
them: AVI payload bytes, the checksum, and a packet enable. The upstream author
also reports that the database's names matched the RTD2142 firmware.

XDATA address = page << 8 | register (`0x4DB6` = page 0x4D, register 0xB6).

## 1. HDR on the DisplayPort output

**Symptom:** HDR through the hub's DP port is washed out or not offered. The same
mechanism caused the HDMI bug: the Switch 2 sends PQ/HLG metadata but does not
mark the stream as BT.2020, so the monitor falls back to BT.709 primaries.

**DP 1.4 fix:** send the colorimetry in a VSC SDP (revision 05h). Set MSA MISC1
bit 6 so the sink ignores MSA colorimetry. Only do this when the sink advertises
DPCD `0x2210` bit 3 (VSC SDP colorimetry supported).

### Registers (RTD2172 DP 1.2 TX0, pages 4D/4E; TX1 is BB/BC at the same offsets)

| Addr | Name | Use |
|---|---|---|
| 4DB4 | MSA_CTRL | bit 7 `msa_db`: latch new MSA values |
| 4DB5 | MSA_MISC0 | [7:5] bpc, [4] BT.601/709, [3] CEA range, [2:1] RGB/422/444 |
| 4DB6 | MN_STRM_ATTR_MISC1 | bit 6 `pixel_fmt_indi`: colorimetry is in the VSC SDP |
| 4E00 | SEC_FUNCTION_CTRL | bit 2 `psr_en`: transmit VSC SDP; bit 4 AVI; bit 7 reserved-infoframe slot 0 |
| 4E02 | SEC_DBUF_CTRL | bit 0 `sec_db`: latch SDP header/payload; bit 1: latch at vblank |
| 4E04–4E13 | SEC_PSR_DB0–15 | VSC payload |
| 4E14 | SEC_PSR_DB16 | [7:4] pixel encoding, [3:0] colorimetry (6 = BT.2020) |
| 4E15 | SEC_PSR_DB17 | [7] CEA range, [2:0] bpc |
| 4E16 | SEC_PSR_DB18 | content type |
| 4E26–4E2B, 4E53–4E56 | DP_INFO_FM_RSV0..2 | reserved SDP slots (HB2/HB3, type, payload port). These are the likely carrier for the HDR static-metadata SDP (type 87h) |

### Draft

`research/dp_hdr_vsc.asm` (98 bytes; assembles with SDCC 4.6.0, but it is neither
hooked nor flashable). It is the DP twin of `asm/rtd2142_hdr_avi.asm`. When the
caller sets C=1, it writes DB16/17/18 from the stream's MISC0, sets MISC1 bit 6,
enables VSC transmission and latches at vblank. C=0 restores SDR signalling.

### To finish once a dump exists

1. `switch2-hub-patcher survey rtd2142-stock.bin`: shows whether the firmware
   drives TX0 (`4Dxx/4Exx`) or TX1 (`BBxx/BCxx`), and lists every code site that
   writes MISC0/MISC1, SEC_FUNCTION_CTRL and the VSC/INFO_FM registers.
2. In Ghidra (8051, banked) or REA, follow those sites to:
   - the function that programs the DP TX MSA after link training (the hook for
     "apply");
   - the function that forwards or regenerates the HDR metadata SDP for the DP
     port (the hook for "HDR on/off"). This also answers "not offered": either
     the HDR SDP is dropped, or the EDID/DPCD exposed upstream hides HDR;
   - where the downstream DPCD `0x2210` is read, so the patch can be gated on it.
3. Find the DP port's "HDR metadata present + EOTF" flags. The HDMI patch uses
   `E362` bit 1 and `DD9F & 7` for logical port 1; the DP port is probably a
   neighbouring flag or byte.
4. Write the builder like `patch_rtd2142_hdr_avi.py`: hash-guarded, with original
   bytes checked at each hook and an erased cave in a bank with room. Add it as a
   second RTD2142 step only after it has been tested on the hub with a SOIC-8
   clip as fallback.

**Test:** an HDR10 DP monitor whose OSD shows the colour space/gamut, plus a
known BT.2020 test pattern. Compare the HDMI port (already fixed) with the DP
port.

## 2. VRR

### Context

- Switch 2 system update **23.0.0 (September 2026)** added VRR in TV mode. It also
  needs a **dock firmware update** on the official dock (Settings > System > Dock
  Update), and games must opt in (at launch only *Welcome Tour* 1.1.0 did).
- The patched hub answers the version queries with records copied from the
  official dock, so the console offers VRR. Upstream saw the DP output freeze and
  HDMI stay at 60 Hz. Keep **VRR off**, and **never accept a Dock Update** with
  the patched hub: there is no update handler, and nothing about that path has
  been tested.

### Why it fails: the receiver regenerates timing

The RTD2172's DP RX has a per-stream display-format generator (DPF) that
rebuilds HSYNC/VSYNC. It runs in `frame_sync_mode` (or "full last line"). With a
variable vblank, the regenerated timing and clock tracking have to re-lock every
frame, which is the "clock re-lock loop" upstream suspected.

The silicon does have a VRR mode:

| Addr (stream 1; ST2 B3xx, ST3 B5xx, ST4 B8xx) | Name | Field |
|---|---|---|
| B130 | DPF_CTRL_0 | bit 5 `frame_sync_mode`, bit 4 `deonly_mode` |
| B190 | DP_RSV0 | bit 0 `drr_mode`: VS just before the first DE line |
| B191 | DP_RSV1 | bit 7 `deonly_full_mode` (after FIFO/tracking stable), bit 6 `de_window_fix_en` |
| B19A | DP_RSVA | bit 0 `vrr_mode`: "if vrr mode & deonly mode, DPF uses the Adaptive-Sync SDP to generate VS"; bit 1 `vrr_vs_mode` |
| B2FC | DUMMY_2 | bit 0 `vsc_for_vrr_en`: pass received Adaptive-Sync info to the DPF instead of filtering it |

So the "rewrite of the input lock" probably reduces to enabling the hardware
mode: `deonly_mode` + `vrr_mode` (+ `vsc_for_vrr_en`, and possibly
`deonly_full_mode` once tracking is stable). This applies only while the source
actually sends Adaptive-Sync SDPs, and the upstream DPCD must advertise
Adaptive-Sync (`MSA_TIMING_PAR_IGNORED`, DPCD 0x0007 bit 6) so the Switch varies
the timing.

### Per output

- **DP port:** the most plausible target. With the DPF in VRR mode and the TX
  forwarding the Adaptive-Sync SDP (it has the reserved SDP slots above), a
  FreeSync/Adaptive-Sync DP monitor could follow. Upstream's attempt
  (Adaptive-Sync advertisement plus EDID override) failed because the DPF stayed
  in frame-sync mode.
- **HDMI port:** much harder. Besides varying timing, the HDMI TX must send either
  an HDMI 2.1 VRR EMP (VTEM) or AMD's FreeSync-over-HDMI vendor InfoFrame
  (OUI 00001A). The RTD2172 database has no named EMP/VRR registers on the HDMI
  2.0 TX, only generic data-island packet slots. A FreeSync VSIF through a
  generic InfoFrame slot is the realistic option. It is unknown which signal the
  official dock uses.

### Hardware-day experiment (read/poke only, with a stock dump saved first)

1. `survey`: find who writes `B130`/`B19A`/`B2FC` (and the ST2–4 copies) and the
   DPCD 0x0007 bit 6 that the hub advertises upstream.
2. In the main loop, find the timing-stable state (where it writes
   `deonly_full_mode` or leaves frame-sync). That is the hook for "VRR on".
3. Build a candidate that sets `deonly_mode|vrr_mode` and `vsc_for_vrr_en` only
   when the received stream carries Adaptive-Sync SDPs. Test DP-port VRR first,
   using *Welcome Tour* 1.1.0 with VRR on and a monitor with a refresh-rate OSD.
4. Watch for the upstream failure (black screen when the frame rate varies) and
   recover by power cycling. Keep the SOIC-8 clip ready.

## Sources

- Upstream write-up: <https://blog.nozomi.space/posts/sw2_dock/>
- RTD2172 register database:
  <https://github.com/roufsweb/portable-display/tree/HEAD/02_RTDCustomerTool_V3.8/RTDScaler/RTD2172>
- DP BT.2020 via VSC SDP + MISC1 bit 6, DPCD 0x2210 bit 3:
  <https://community.altera.com/discussions/ip-and-transceiver/how-to-configure-displayport-tx-to-support-bt-2020-colorimetry/45740>,
  <https://lkml.iu.edu/2605.2/04577.html>
- Switch 2 23.0.0 docked VRR + dock update:
  <https://www.thesixthaxis.com/2026/09/10/nintendo-switch-2-finally-gets-docked-vrr-with-system-update-23-0-0/>,
  <https://tech-insider.org/nintendo-switch-2-docked-vrr-update-23-2026/>
