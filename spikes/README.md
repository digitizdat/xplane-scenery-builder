# Spikes

Spikes are throwaway prototypes used **only to answer specific questions** — is
something feasible, how hard is it, what does the format actually look like.

Rules:
- A spike exists to answer one or more explicit questions. State them, answer
  them, and record the answers here and in the spike file.
- Spikes are not shipped code. They live in `spikes/`, not `src/`, and are not
  held to the full `make precommit` bar. Promoting a spike's idea into `src/`
  means writing it properly (tests, types, edge cases) — not moving the file.
- Once a spike has answered its questions, leave it as a record. Do not keep
  extending it; open a real task instead.

## Index

### `obj8_parser.py` — can we parse X-Plane OBJ8 in pure Python? (WED-001 / RENDER-002)

Ports the OBJ8 read grammar from WED's MIT-licensed `Obj/XObjReadWrite.cpp`.

- **Q1. Can OBJ8 geometry be parsed in pure Python by porting WED's reader?**
  Yes — 296/300 sampled default-library `.obj` files parsed with counts matching
  an independent cross-check (0 mismatches).
- **Q2. Is the port low-risk enough to justify WED-001's "port to Python" plan
  and de-risk RENDER-002?** Yes — ~140 lines for geometry; the format is simple
  and GL-free. The remaining RENDER-002 work is the draw step and procedural
  facades, not OBJ parsing.
- **Q3. What edge cases must a production port handle?** Legacy OBJ7 (v700) files
  exist (~1% of sample) and need a separate reader or explicit skip;
  `ATTR_LOD_draped` takes one argument, unlike `ATTR_LOD near far`.

Run: `python3 spikes/obj8_parser.py <path-to.obj>`
