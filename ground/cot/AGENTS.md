# ground/cot/ — tracks → Cursor on Target

## Purpose
Subscribe `tr/v1/tracks`, emit one CoT event per track to ATAK/WinTAK.
Default: UDP multicast `239.2.3.1:6969` (TAK SA), optional unicast targets.

## Mapping
- ENU → lat/lon/HAE around `origin` in `config/site.yaml` (local tangent-plane
  approximation is fine at demo scale; keep it in one function).
- `uid`: `triangulum.<site>.<track id>` — stable per track.
- `type`: hostile `a-h-A-M-F-Q`, friendly `a-f-A-M-F-Q`, unknown `a-u-A`
  (MIL-STD-2525 air / UAV). `how`: `m-f` (machine, fused). Verify both render
  as expected in ATAK before the demo.
- `time` = `start` = now, `stale` = now + 5 s (tracks vanish if fusion stops).
- `point ce` = horizontal sigma, `le` = vertical sigma, in metres.
- `<detail>`: `<track course=".." speed=".."/>` from `vel`, `<contact callsign="TR-<id>"/>`,
  `<remarks>` with nodes used and sigma.

## Rules
- Stateless translation: no tracking logic here.
- Generate XML with `xml.etree.ElementTree`, not string concatenation.
- Unit-test the ENU→LLH conversion and one golden CoT event.
- Stretch (P3): a second output adapter for SAPIENT (BSI Flex 335 protobuf over TCP)
  in its own module; same input, same rules.

## Done criteria
- Tracks from a replay appear and move on WinTAK/ATAK on the same network.
