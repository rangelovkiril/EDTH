# Network

## Addressing
| Segment | Subnet | Gateway side | Others |
|---------|--------|--------------|--------|
| Sensor AP (`wlan0`) | `10.42.0.0/24` | `10.42.0.1` | ESP nodes via DHCP |
| Uplink (`eth0`) | `10.43.0.0/24` | `10.43.0.1` | laptop `10.43.0.2` (static) |

Nodes are identified by `node_id` in the payload, not by IP. ESP firmware only
needs the gateway address `10.42.0.1`.

## Ports on the gateway
| Port | Proto | Service | Reachable from |
|------|-------|---------|----------------|
| 123 | UDP | chrony | AP, uplink |
| 1883 | TCP | mosquitto | localhost, uplink |
| 5600 | UDP | ingest | AP, localhost |
| 5601 | UDP | tsync responder | AP |

Everything else is dropped (nftables).

## AP security (prototype)
- Own AP; never use venue Wi-Fi for sensors.
- Fixed channel chosen after a site scan (2.4 GHz: 1/6/11).
- WPA3-SAE with PMF required. If the Pi Wi-Fi chip cannot do SAE in AP mode,
  fall back to WPA2-PSK with PMF required and a long random passphrase.
- MAC allowlist for known nodes.
- Passphrase is not in git (`infra/gateway/ap.secrets.example`).
