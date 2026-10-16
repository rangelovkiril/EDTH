# protocol/ — wire protocol codecs

## Purpose
Single implementation of `docs/protocol.md` §2 for every language in the repo.
Nothing else in the repo may hand-parse or hand-build packets.

```
c/trwire.h                 header-only C (ESP-IDF firmware includes it directly)
python/src/trwire/         Python codec, used by ingest, pi-node, tools
test-vectors/vectors.json  canonical encoded messages + decoded fields
tools/gen_vectors.py       regenerates vectors from the Python codec
```

## Rules
- `docs/protocol.md` is the source of truth. If it and the code disagree, fix the code.
- A layout change touches **all of**: doc, `trwire.h`, Python codec, vectors —
  in one commit (`feat(protocol): ...`). Bump `TR_VERSION` / `VERSION` if
  old decoders would misread it.
- C: header-only, C11, `__attribute__((packed))`, `_Static_assert` on every
  struct size and on little-endian. No dynamic allocation.
- Python: stdlib only (`struct`, `dataclasses`). Quantized values are stored as
  the raw integers (`cx_q3`, `conf_u8`) with float convenience properties, so
  encode/decode round-trips are exact.
- Decoders reject: short/long datagrams, wrong magic, unknown version, unknown
  type, `count` out of 1..16. They never raise anything but `WireError`.

## Commands
```sh
uv run pytest protocol/python
uv run python protocol/tools/gen_vectors.py      # after an intentional change
gcc -std=c11 -Wall -Wextra -fsyntax-only -x c protocol/c/trwire.h
```

## Done criteria
- Python tests pass against the vectors; the C header compiles with the size asserts.
