# firmware/components/ — shared ESP-IDF components

## `tr_link` — ESP-NOW link
- Init Wi-Fi in STA mode without connecting, fixed channel, power save off.
- Register peers from `network.defaults`; encryption with PMK/LMK from `espnow.keys`.
- `tr_link_send(peer, buf, len)` — non-blocking, enqueue; drop and count when full.
- Receive callback: stamp `esp_timer_get_time()` (or radio RX timestamp) first,
  copy frame + stamp + RSSI into a queue, return. Dispatch by `type` in a task.
- Validate header (magic, version, length per type) before dispatch; count bad frames.
- Exposes counters for `STATUS` (RSSI of last frame from a given peer, drops).
- Adds `../../../protocol/c` to its public include dirs so apps get `trwire.h`.

## `tr_timesync`
- **Master** (collector): answer `TSYNC_REQ` with `TSYNC_RESP`, t2 from the
  receive stamp, t3 right before send. No logging per packet.
- **Client** (observers): send `TSYNC_REQ` at 2 Hz, keep 16 samples, drop the
  half with largest delay, linear fit offset + drift, expose
  `tr_time_now_us()`, `tr_time_from_local(local_us)`, `tr_time_synced()`,
  `tr_time_last_offset_us()`, `tr_time_last_rtt_us()`.
- Collector-reboot handling per `docs/time-sync.md`.
- Unit-testable math in a plain C file without ESP-IDF dependencies.

## Rules
- No app-specific logic here. Changes are reviewed by every app owner.
