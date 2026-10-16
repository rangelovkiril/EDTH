# Time synchronization

## Network timescale
One timescale for all observers: the **collector's clock**, in µs
(`esp_timer_get_time()` on the collector). It is not UTC and starts at the
collector's boot. Fusion only needs observers to agree with each other.

Required accuracy for the demo: ≤ 2 ms observer-to-observer (a target at
10 m/s moves 2 cm).

## Capture stamps
- Stamp from the earliest available point in the capture path, not when the
  frame reaches application code.
- Keep the stamp in the local monotonic base (`esp_timer_get_time()`) and
  convert to network time with the current correction when the message is built.
- A constant per-camera capture latency, if measured, is subtracted on the node
  (`CONFIG_TR_CAPTURE_LATENCY_US`) or on the ground (`latency_us` in
  `config/site.yaml`).

## `TSYNC` over ESP-NOW
NTP-style exchange (`protocol.md` §2.4–2.5), observer-initiated, at 2 Hz:
- offset θ = ((t2 − t1) + (t3 − t4)) / 2, delay δ = (t4 − t1) − (t3 − t2).
- Keep the last 16 samples, discard the half with the largest δ, fit
  `network = local + a·local + b` (offset + drift) on the rest.
- Collector stamps t2 as early as possible in the receive callback (radio RX
  timestamp from `rx_ctrl` if available, otherwise `esp_timer_get_time()` first
  thing in the callback) and t3 immediately before `esp_now_send`.
- Report θ and δ in `STATUS` (`clock_offset_us`, `rtt_us`).
- `TIME_SYNCED` = fit from ≥ 8 samples, newest < 5 s old.

## Collector reboot
The network timescale restarts. Observers detect it as an offset jump larger
than 1 s, drop their sample window and resync; until synced again they clear
`TIME_SYNCED`. Fusion resets tracks when network time goes backwards.
