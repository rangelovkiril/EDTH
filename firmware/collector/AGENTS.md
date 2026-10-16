# firmware/collector/ — collector node (ID 100)

## Purpose
- Receive `DETECTION_BATCH` and `STATUS` from observers over ESP-NOW.
- Be the **time master**: answer `TSYNC_REQ` (`tr_timesync` master). Its
  `esp_timer` clock is the network timescale.
- Relay observer messages towards the ground node.
- Send its own `STATUS` at 1 Hz (`sync_age_ms = 0`, `TIME_SYNCED` always set).

## Rules
- Time sync responses take priority over everything else; keep that path short.
- Relay: the collector↔ground link is an **open question**. Implement the relay
  against a `tr_uplink` interface (`tr_uplink_send(buf, len)`); until decided,
  the stub writes one log line per message (`node`, `type`, `seq`, `t`, rx stamp)
  to the serial console. That log is also the P0 debug view.
- Do not modify, merge or reorder observer messages unless the link decision
  requires it — and then document it in `docs/protocol.md`.
- Validate and count per observer: received, bad, `seq` gaps.

## Done criteria
- Two observers synced with `rtt_us` and offsets visible in the log.
- Measured: TSYNC round-trip, sync error between observers.
