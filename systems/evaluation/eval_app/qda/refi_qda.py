"""REFI-QDA 1.5 packer / unpacker.

REFI-QDA (Rotterdam Exchange Format for Qualitative Data Analysis) is
the interchange standard supported by ATLAS.ti, NVivo, MAXQDA, QualCoder,
and (increasingly) OpenQDA. Public spec:
https://www.qdasoftware.org/

A REFI-QDA project is a `.qdpx` file — a ZIP archive with:

    project.qde            XML root: Project, Users, CodeBook, Sources, Sets
    sources/<source-id>.txt|.pdf|.docx|…   plain or rich source files

We use plain-text sources (one `.txt` per sampled signal). The XML
root holds:

    <Project name="…" creatingUserGUID="…" creationDateTime="…">
      <Users>
        <User guid="…" name="…"/>
      </Users>
      <CodeBook>
        <Codes>
          <Code guid="…" name="…" isCodable="true">
            <Description>…</Description>
            <Code …>  <!-- nested -->
        </Codes>
      </CodeBook>
      <Sources>
        <TextSource guid="…" name="…" plainTextPath="sources/…">
          <Description>…</Description>
          <PlainTextSelection guid="…" startPosition="0" endPosition="N">
            <Coding guid="…" creatingUser="…" creationDateTime="…">
              <CodeRef targetGUID="…"/>
            </Coding>
          </PlainTextSelection>
        </TextSource>
      </Sources>
    </Project>

We render whole-document selections (startPosition=0,
endPosition=len(text)) because each source IS one signal — there's
no sub-document segmentation.

This module deliberately avoids importing any heavy XML library
(`lxml` is not in eval_app's deps); the stdlib `xml.etree.ElementTree`
emits a perfectly valid REFI-QDA document.
"""

from __future__ import annotations

import datetime as _dt
import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Iterable

from .codebook import CodeBook, CodeNode


# REFI-QDA xmlns. Tools accept either the bare "no-namespace" form or
# this namespace. QualCoder uses this exact one; we emit it to maximise
# compatibility.
_NS = "urn:QDA-XML:project:1.5"


def _ns(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------- in-memory representation ----------


@dataclass
class SignalSource:
    """A single signal rendered as a plain-text REFI-QDA source.

    `text` is the body the coder sees. We compose it from title +
    evidence_quote + summary + a metadata footer so all the data the
    coder needs to call a category is visible inside the QDA tool.
    """

    signal_id: str        # public.signals.id (uuid str)
    name: str             # short display name — usually `<actor> | <title>`
    text: str
    # Pre-existing system predictions written into the source footer so
    # the coder can see what System A / System B already produced.
    pre_existing_codings: list["AppliedCode"] = field(default_factory=list)
    # Stable GUID derived from signal_id so re-exports of the same signal
    # produce identical xml.
    @property
    def guid(self) -> str:
        return str(uuid.uuid5(uuid.UUID("8c4f3f1e-5c8b-4f6c-b1d7-2f9e0c1a4b3e"), f"source:{self.signal_id}"))

    @property
    def filename(self) -> str:
        return f"sources/{self.signal_id}.txt"


@dataclass
class AppliedCode:
    """One coding decision the importer needs to recover.

    `coder_name` is "anna" / "supervisor" / "system_a" / "system_b".
    On import we only honour codings whose `coder_name` matches the
    `--coder` flag (default: "anna").
    """
    code_name: str
    coder_name: str = "anna"


# ---------- writer ----------


def write_qdpx(
    out_path: str | Path,
    *,
    codebook: CodeBook,
    sources: list[SignalSource],
    project_name: str,
    creating_user: str = "anna",
) -> Path:
    """Pack a REFI-QDA `.qdpx` file ready to open in QualCoder / ATLAS.ti."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- build the XML ----
    project = ET.Element(_ns("Project"), {
        "name": project_name,
        "creatingUserGUID": str(uuid.uuid5(uuid.UUID("8c4f3f1e-5c8b-4f6c-b1d7-2f9e0c1a4b3e"), f"user:{creating_user}")),
        "creationDateTime": _utc_now(),
        "origin": "mas-deeptech-research v0.4.39 (REFI-QDA exporter)",
    })

    users = ET.SubElement(project, _ns("Users"))
    ET.SubElement(users, _ns("User"), {
        "guid": project.attrib["creatingUserGUID"],
        "name": creating_user,
    })

    code_book_el = ET.SubElement(project, _ns("CodeBook"))
    codes_el = ET.SubElement(code_book_el, _ns("Codes"))
    for node in codebook.codes:
        _render_code(codes_el, node)

    sources_el = ET.SubElement(project, _ns("Sources"))
    for src in sources:
        _render_source(sources_el, src, codebook)

    # ---- serialise to bytes ----
    ET.register_namespace("", _NS)  # default namespace, no prefix on tags
    xml_bytes = ET.tostring(project, encoding="utf-8", xml_declaration=True)

    # ---- pack into ZIP ----
    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.qde", xml_bytes)
        for src in sources:
            zf.writestr(src.filename, src.text.encode("utf-8"))

    return out_path


def _render_code(parent: ET.Element, node: CodeNode) -> None:
    code_el = ET.SubElement(parent, _ns("Code"), {
        "guid": node.guid,
        "name": node.name,
        "isCodable": "true",
    })
    if node.description:
        desc = ET.SubElement(code_el, _ns("Description"))
        desc.text = node.description
    for child in node.children:
        _render_code(code_el, child)


def _render_source(parent: ET.Element, src: SignalSource, codebook: CodeBook) -> None:
    src_el = ET.SubElement(parent, _ns("TextSource"), {
        "guid": src.guid,
        "name": src.name,
        "plainTextPath": src.filename,
        "creatingUserGUID": parent.getparent().attrib["creatingUserGUID"]
            if hasattr(parent, "getparent") else "",  # ET has no getparent; harmless
    })
    desc = ET.SubElement(src_el, _ns("Description"))
    desc.text = f"signal_id={src.signal_id}"

    if not src.pre_existing_codings:
        return

    # Pre-existing System A / System B codings are written as
    # whole-document selections so the coder sees them but they're
    # tagged with system_a / system_b coder names — the importer filters
    # by coder when reading back.
    sel = ET.SubElement(src_el, _ns("PlainTextSelection"), {
        "guid": str(uuid.uuid5(uuid.UUID("8c4f3f1e-5c8b-4f6c-b1d7-2f9e0c1a4b3e"),
                               f"selection:{src.signal_id}:system")),
        "startPosition": "0",
        "endPosition": str(len(src.text)),
        "name": "system-prediction",
    })
    for applied in src.pre_existing_codings:
        code_node = codebook.by_name.get(applied.code_name)
        if code_node is None:
            continue
        coding = ET.SubElement(sel, _ns("Coding"), {
            "guid": str(uuid.uuid5(uuid.UUID("8c4f3f1e-5c8b-4f6c-b1d7-2f9e0c1a4b3e"),
                                   f"coding:{src.signal_id}:{applied.coder_name}:{applied.code_name}")),
            "creatingUser": applied.coder_name,
            "creationDateTime": _utc_now(),
        })
        ET.SubElement(coding, _ns("CodeRef"), {"targetGUID": code_node.guid})


# ---------- reader ----------


@dataclass
class CodedSource:
    """What the importer recovers per source from a coded .qdpx."""
    signal_id: str
    # Coder name → list of applied code names. Multi-coder files
    # (Anna + supervisor) round-trip cleanly.
    codings: dict[str, list[str]] = field(default_factory=dict)


def read_qdpx(path: str | Path) -> tuple[CodeBook, list[CodedSource]]:
    """Unpack a .qdpx file back into a CodeBook + list of CodedSource.

    Returns the codebook AS WRITTEN in the file (not re-derived from
    schema.yaml — the file is the source of truth at import time so
    we can detect codebook drift via the by_name lookup).
    """
    path = Path(path)
    with zipfile.ZipFile(path, mode="r") as zf:
        with zf.open("project.qde") as fh:
            tree = ET.parse(fh)
    root = tree.getroot()

    # ---- recover the codebook (codes by GUID) ----
    codes_el = root.find(f"{_ns('CodeBook')}/{_ns('Codes')}")
    code_by_guid: dict[str, CodeNode] = {}
    code_book = CodeBook(codes=[])
    if codes_el is not None:
        for code_el in list(codes_el):
            top = _parse_code(code_el, code_by_guid)
            code_book.codes.append(top)
    for node in code_book.all_nodes():
        code_book.by_name[node.name] = node

    # ---- recover sources + their codings ----
    coded: list[CodedSource] = []
    sources_el = root.find(_ns("Sources"))
    if sources_el is None:
        return code_book, coded

    for src_el in sources_el.findall(_ns("TextSource")):
        # signal_id lives in <Description>signal_id=…</Description>
        signal_id = ""
        desc_el = src_el.find(_ns("Description"))
        if desc_el is not None and desc_el.text:
            for piece in desc_el.text.split():
                if piece.startswith("signal_id="):
                    signal_id = piece.split("=", 1)[1]
                    break
        if not signal_id:
            continue

        cs = CodedSource(signal_id=signal_id, codings={})
        for sel_el in src_el.findall(_ns("PlainTextSelection")):
            for coding_el in sel_el.findall(_ns("Coding")):
                coder = (coding_el.get("creatingUser") or "anna").strip()
                code_ref = coding_el.find(_ns("CodeRef"))
                if code_ref is None:
                    continue
                guid = code_ref.get("targetGUID")
                node = code_by_guid.get(guid)
                if node is None:
                    continue
                cs.codings.setdefault(coder, []).append(node.name)
        coded.append(cs)

    return code_book, coded


def _parse_code(code_el: ET.Element, by_guid: dict[str, CodeNode]) -> CodeNode:
    guid = code_el.get("guid") or ""
    name = code_el.get("name") or ""
    desc_el = code_el.find(_ns("Description"))
    desc = (desc_el.text or "").strip() if desc_el is not None else ""
    node = CodeNode(guid=guid, name=name, description=desc, axis="dimension")
    by_guid[guid] = node
    for child_el in code_el.findall(_ns("Code")):
        child = _parse_code(child_el, by_guid)
        node.children.append(child)
    return node
