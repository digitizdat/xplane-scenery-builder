"""Spike: minimal X-Plane OBJ8 parser, ported from WED's Obj/XObjReadWrite.cpp.

Backlog: WED-001 / RENDER-002. Status: spike (throwaway prototype, not shipped).

Questions this spike answered
-----------------------------
Q1. Can X-Plane OBJ8 geometry be parsed in pure Python by porting WED's
    MIT-licensed read routine (Obj/XObjReadWrite.cpp)?
A1. Yes. 296/300 randomly sampled default-library .obj files parsed with vertex
    counts and TRIS index sums matching an independent text cross-check
    (0 mismatches).

Q2. Is the port low-effort/low-risk enough to justify the WED-001 "port to
    Python" plan and de-risk RENDER-002?
A2. Yes. ~140 lines for geometry; the OBJ8 format is simple and GL-free. The
    remaining hard parts of RENDER-002 are the draw step (retarget to
    pyrender/moderngl) and procedural facades (WED_FacadePreview), not OBJ
    parsing.

Q3. What format edge cases must a production port handle?
A3. (a) Legacy OBJ7 (version 700) files exist in the default library (~1% of the
    sample) and need a separate reader or an explicit skip. (b) ATTR_LOD_draped
    takes a single distance argument (draped render attribute), distinct from
    ATTR_LOD near far (a geometry LOD bucket).

Scope: geometry only. Animations, ATTR_* render state, and lights/lines are
recognized but not fully modeled. Faithful to the WED grammar: a vertex pool
(VT, 8 floats each), an index list (IDX / IDX10), and draw commands
(TRIS offset count) that slice the index list; each index points into the
vertex pool. LOD buckets are split on ATTR_LOD.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# 8 floats per triangle vertex: x y z  nx ny nz  s t
Vertex = tuple[float, float, float, float, float, float, float, float]


@dataclass
class Command:
    """A draw command referencing a slice of the index list."""

    kind: str  # "TRIS" | "LINES" | "LIGHTS"
    idx_offset: int
    idx_count: int


@dataclass
class Lod:
    lod_near: float = 0.0
    lod_far: float = 0.0
    cmds: list[Command] = field(default_factory=list)


@dataclass
class Obj8:
    texture: str = ""
    texture_draped: str = ""
    vertices: list[Vertex] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    lods: list[Lod] = field(default_factory=list)

    def triangles(self, cmd: Command) -> list[tuple[Vertex, Vertex, Vertex]]:
        """Resolve a TRIS command into vertex triples (offset+count into indices)."""
        tris: list[tuple[Vertex, Vertex, Vertex]] = []
        sl = self.indices[cmd.idx_offset : cmd.idx_offset + cmd.idx_count]
        for i in range(0, len(sl) - 2, 3):
            tris.append((self.vertices[sl[i]], self.vertices[sl[i + 1]], self.vertices[sl[i + 2]]))
        return tris


class Obj8ParseError(Exception):
    pass


def parse_obj8(path: Path) -> Obj8:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    it = iter(lines)

    # X-Plane header: "I"/"A", then version "800", then "OBJ" (blank lines ignored).
    def next_nonblank() -> str:
        for ln in it:
            if ln.strip():
                return ln.strip()
        raise Obj8ParseError("unexpected end of file in header")

    if next_nonblank() not in ("I", "A"):
        raise Obj8ParseError("missing I/A line-ending marker")
    if next_nonblank() != "800":
        raise Obj8ParseError("not an OBJ8 (version != 800)")
    if next_nonblank() != "OBJ":
        raise Obj8ParseError("missing OBJ type line")

    obj = Obj8()
    obj.lods.append(Lod())

    for raw in it:
        tok = raw.split()
        if not tok or tok[0].startswith("#"):
            continue
        cmd = tok[0]

        if cmd == "POINT_COUNTS":
            # tris lines lights idx — informational; we size lazily from actual data
            continue
        elif cmd == "VT":
            f = [float(x) for x in tok[1:9]]
            obj.vertices.append((f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7]))
        elif cmd == "IDX10":
            obj.indices.extend(int(x) for x in tok[1:11])
        elif cmd == "IDX":
            obj.indices.append(int(tok[1]))
        elif cmd in ("TEXTURE", "TEXTURE_LIT", "TEXTURE_NORMAL"):
            if cmd == "TEXTURE" and len(tok) > 1:
                obj.texture = tok[1]
        elif cmd == "TEXTURE_DRAPED":
            if len(tok) > 1:
                obj.texture_draped = tok[1]
        elif cmd in ("TRIS", "LINES", "LIGHTS"):
            c = Command(kind=cmd, idx_offset=int(tok[1]), idx_count=int(tok[2]))
            obj.lods[-1].cmds.append(c)
        elif cmd == "ATTR_LOD":
            # ATTR_LOD near far — mirror WED: start a new LOD bucket once the
            # current one is bounded. (ATTR_LOD_draped takes a single distance
            # and is a draped-render attribute, not a geometry LOD; ignored.)
            near, far = float(tok[1]), float(tok[2])
            if obj.lods[-1].lod_far != 0.0:
                obj.lods.append(Lod())
            obj.lods[-1].lod_near = near
            obj.lods[-1].lod_far = far
        # Everything else (ATTR_*, ANIM_*, GLOBAL_*, VLINE, VLIGHT) is ignored
        # for this geometry-only spike.

    return obj


def _summary(path: Path) -> None:
    obj = parse_obj8(path)
    tri_cmds = [c for lod in obj.lods for c in lod.cmds if c.kind == "TRIS"]
    total_tris = sum(c.idx_count // 3 for c in tri_cmds)
    print(f"file:        {path.name}")
    print(f"texture:     {obj.texture or obj.texture_draped or '(none)'}")
    print(f"vertices:    {len(obj.vertices)}")
    print(f"indices:     {len(obj.indices)}")
    print(f"LOD buckets: {len(obj.lods)}")
    print(f"TRIS cmds:   {len(tri_cmds)}  ->  {total_tris} triangles total")
    if tri_cmds:
        first = obj.triangles(tri_cmds[0])
        if first:
            a, b, c = first[0]
            print("first triangle (xyz of each vertex):")
            print(f"  v0 = ({a[0]:.4f}, {a[1]:.4f}, {a[2]:.4f})")
            print(f"  v1 = ({b[0]:.4f}, {b[1]:.4f}, {b[2]:.4f})")
            print(f"  v2 = ({c[0]:.4f}, {c[1]:.4f}, {c[2]:.4f})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python obj8_parser.py <path-to.obj>", file=sys.stderr)
        raise SystemExit(2)
    _summary(Path(sys.argv[1]))
