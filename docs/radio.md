# Radio (ESP-NOW)

## Observer ↔ collector
- ESP-NOW over Wi-Fi in STA mode, **not connected to any AP**.
- One fixed channel for all nodes: `CONFIG_TR_ESPNOW_CHANNEL`. Choose it
  after scanning the venue.
- Unicast only, explicit peers: each observer has the collector's MAC as its
  only peer; the collector has every observer's MAC.
- Encryption on: one PMK for the network, one LMK per peer. Keys in
  `firmware/*.keys` files (gitignored), template in `firmware/espnow.keys.example`.
- Wi-Fi power save off on every node.

## Node IDs
`node_id` in the message header identifies the sender (`protocol.md` §2).
MAC → node ID mapping lives in the collector's config and in `config/site.yaml`.

## Collector ↔ ground
Open question (root `AGENTS.md`).
