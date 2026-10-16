# firmware/ground/ — ground node (ID 110)

## Purpose
Receive messages from the collector and hand them to the ground host.
Send its own `STATUS` at 1 Hz.

## Rules
- Both of its links are **open questions** (root `AGENTS.md`): the
  collector↔ground link (`tr_uplink`) and the ground↔host interface (`tr_host`).
  Do not pick a transport inside this zone; implement against the interfaces
  with stubs and wait for the decision.
- Pass messages through unchanged. Decoding happens in `ground/bridge`.

## Done criteria
- Defined once the open questions are decided.
