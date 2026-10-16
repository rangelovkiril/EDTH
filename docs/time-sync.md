# Time synchronization

## Timescale
One timescale for the whole system: the **gateway's system clock** (chrony),
expressed as UTC µs since epoch. The gateway runs chrony with `local stratum`
so it serves time without internet. The laptop is a chrony client of the gateway.

Required accuracy for the demo: ≤ 2 ms node-to-node (a target at 10 m/s moves
2 cm). The field target is ≤ 100 µs.

## Capture stamps
- Stamp from the earliest available point in the capture path, not when the
  frame reaches application code.
- Keep the stamp in a **local monotonic** base (`esp_timer_get_time()`,
  `CLOCK_MONOTONIC`) and convert to the gateway timescale with the current
  correction at the moment the message is built.
- Constant capture latency per camera type is measured once (see below) and
  subtracted on the node.

## Phase 1 — SNTP (P0)
- ESP: ESP-IDF SNTP client, server `10.42.0.1`. Wi-Fi power save **off**.
- Pi nodes run on the gateway: they share its clock directly.
- `TIME_SYNCED` = a successful sync within the last 60 s.

## Phase 2 — `TSYNC` (P3)
NTP-style exchange on UDP 5601 (`protocol.md` §2.4–2.5), at 2 Hz:
- offset θ = ((t2 − t1) + (t3 − t4)) / 2, delay δ = (t4 − t1) − (t3 − t2).
- Keep the last 16 samples, discard the half with the largest δ (Wi-Fi spikes),
  fit `gateway = local + a·local + b` (offset + drift) on the rest.
- Gateway stamps t2 with kernel RX timestamps (`SO_TIMESTAMPNS`).
- Report θ and δ in `STATUS` (`clock_offset_us`, `rtt_us`).
- `TIME_SYNCED` = fit from ≥ 8 samples, newest < 5 s old.

## Latency calibration (LED test)
Point all cameras at one LED driven by a gateway GPIO, blinking at known
gateway timestamps. For each node, compare the blink time with `t_capture_us`
of the first frame where the LED appears. The mean difference is that
camera's capture latency; record it in `config/site.yaml` (`latency_us`).
Fusion subtracts it when the node cannot (Pi/USB cameras).
