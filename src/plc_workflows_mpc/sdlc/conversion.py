"""L5X ↔ JSON conversion — git-friendly representation for Rockwell Studio 5000 exports.

L5X is the XML interchange format for Rockwell Logix 5000 controllers. The binary
``.ACD`` form is opaque to git; the textual ``.L5X`` form is XML and *diffable*
in principle, but its nested structure means single logical edits often surface
as large textual diffs.

This module ships a **deterministic, structure-preserving** JSON serialization
of the L5X parse tree. Every element becomes a node dict with stable key order:

    {
        "tag": "Tag",
        "attrib": {"Name": "MPC_Enable", "DataType": "BOOL"},
        "text": None,
        "tail": None,
        "children": [...]
    }

XML comments are preserved as nodes with ``tag = "!comment"``. Round-trip:
``dict_to_l5x(l5x_to_dict(xml)) ≡ xml`` modulo whitespace inside the XML
declaration.

Why not just ship the XML as-is to git? Because the JSON form is amenable to
*structural* diffs (see :func:`l5x_diff`) and to per-element review — exactly
what brings PLC code into the standard software-development flow.

This Phase 3 implementation does **not** handle the binary ACD format; ACD
conversion needs Studio 5000 or an external tool (see the ``plc-format-converter``
package). Use this module's L5X ↔ JSON layer once you have an L5X export.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lxml import etree

from plc_workflows_mpc.sdlc.base import L5xDiffEntry

_COMMENT_TAG = "!comment"
_PI_TAG = "!processing_instruction"


# ── XML → dict --------------------------------------------------------------


def l5x_to_dict(xml: bytes | str) -> dict[str, Any]:
    """Parse L5X XML and return a deterministic JSON-ready dict.

    The dict mirrors the lxml ``_Element`` model (``tag``, ``attrib``, ``text``,
    ``tail``, ``children``) so round-trip back to XML is exact.
    """
    payload = xml.encode("utf-8") if isinstance(xml, str) else xml
    parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
    root = etree.fromstring(payload, parser=parser)
    return _element_to_dict(root)


def _element_to_dict(element: Any) -> dict[str, Any]:
    if element.tag is etree.Comment:
        return {
            "tag": _COMMENT_TAG,
            "attrib": {},
            "text": element.text,
            "tail": element.tail,
            "children": [],
        }
    if element.tag is etree.ProcessingInstruction:
        return {
            "tag": _PI_TAG,
            "attrib": {"target": element.target},
            "text": element.text,
            "tail": element.tail,
            "children": [],
        }
    return {
        "tag": str(element.tag),
        "attrib": dict(element.attrib),
        "text": element.text,
        "tail": element.tail,
        "children": [_element_to_dict(child) for child in element],
    }


# ── dict → XML --------------------------------------------------------------


def dict_to_l5x(payload: dict[str, Any]) -> bytes:
    """Render a node dict back to L5X XML bytes with the standard declaration.

    Raises :class:`ValueError` if ``payload`` is missing required keys.
    """
    if "tag" not in payload:
        raise ValueError("payload missing required 'tag' key")
    root = _dict_to_element(payload)
    rendered: bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
        pretty_print=False,
    )
    return rendered


def _dict_to_element(payload: dict[str, Any]) -> Any:
    tag = payload["tag"]
    if tag == _COMMENT_TAG:
        elem = etree.Comment(payload.get("text") or "")
    elif tag == _PI_TAG:
        target = (payload.get("attrib") or {}).get("target", "xml")
        elem = etree.ProcessingInstruction(target, payload.get("text") or "")
    else:
        elem = etree.Element(tag, attrib=payload.get("attrib") or {})
        if payload.get("text") is not None:
            elem.text = payload["text"]
        for child in payload.get("children", []):
            elem.append(_dict_to_element(child))
    if payload.get("tail") is not None:
        elem.tail = payload["tail"]
    return elem


# ── File helpers ------------------------------------------------------------


def write_json(payload: dict[str, Any], path: Path) -> None:
    """Write ``payload`` to ``path`` with stable formatting and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def read_json(path: Path) -> dict[str, Any]:
    """Load a node dict from a JSON file."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object at root, got {type(data).__name__}")
    return data


def convert_l5x_file_to_json(l5x_path: Path, json_path: Path) -> Path:
    """Read an L5X file and write its JSON representation to ``json_path``."""
    payload = l5x_to_dict(l5x_path.read_bytes())
    write_json(payload, json_path)
    return json_path


def convert_json_file_to_l5x(json_path: Path, l5x_path: Path) -> Path:
    """Read a JSON file and write its L5X (XML) representation to ``l5x_path``."""
    payload = read_json(json_path)
    l5x_path.parent.mkdir(parents=True, exist_ok=True)
    l5x_path.write_bytes(dict_to_l5x(payload))
    return l5x_path


# ── Validation --------------------------------------------------------------


_L5X_ROOT_RE = re.compile(r"^RSLogix5000Content$")


def validate_l5x(xml: bytes | str) -> tuple[bool, str | None]:
    """Validate that ``xml`` parses and has the expected ``RSLogix5000Content`` root.

    Returns ``(True, None)`` on success or ``(False, reason)`` on failure.
    """
    try:
        payload = xml.encode("utf-8") if isinstance(xml, str) else xml
        root = etree.fromstring(payload, etree.XMLParser(remove_blank_text=False))
    except etree.XMLSyntaxError as exc:
        return False, f"XML syntax error: {exc}"
    if not _L5X_ROOT_RE.match(str(root.tag)):
        return False, f"unexpected root element {root.tag!r}; expected RSLogix5000Content"
    return True, None


# ── Structural diff ---------------------------------------------------------


def l5x_diff(
    a: dict[str, Any] | bytes | str,
    b: dict[str, Any] | bytes | str,
) -> list[L5xDiffEntry]:
    """Compute a structural diff between two L5X documents (or their dict forms).

    Walks both trees in parallel, reporting added / removed / changed nodes by a
    JSON-pointer-like path.
    """
    dict_a = a if isinstance(a, dict) else l5x_to_dict(a)
    dict_b = b if isinstance(b, dict) else l5x_to_dict(b)
    out: list[L5xDiffEntry] = []
    _diff_node(dict_a, dict_b, path="$", out=out)
    return out


def _diff_node(a: dict[str, Any], b: dict[str, Any], *, path: str, out: list[L5xDiffEntry]) -> None:
    if a["tag"] != b["tag"]:
        out.append(L5xDiffEntry(path=f"{path}.tag", op="changed", before=a["tag"], after=b["tag"]))
        return
    # Attributes
    attrib_a = a.get("attrib") or {}
    attrib_b = b.get("attrib") or {}
    for key in attrib_a.keys() - attrib_b.keys():
        out.append(L5xDiffEntry(path=f"{path}.@{key}", op="removed", before=attrib_a[key]))
    for key in attrib_b.keys() - attrib_a.keys():
        out.append(L5xDiffEntry(path=f"{path}.@{key}", op="added", after=attrib_b[key]))
    for key in attrib_a.keys() & attrib_b.keys():
        if attrib_a[key] != attrib_b[key]:
            out.append(
                L5xDiffEntry(
                    path=f"{path}.@{key}", op="changed", before=attrib_a[key], after=attrib_b[key]
                )
            )
    # Text content
    if (a.get("text") or "").strip() != (b.get("text") or "").strip():
        out.append(
            L5xDiffEntry(
                path=f"{path}.text", op="changed", before=a.get("text"), after=b.get("text")
            )
        )
    # Children (positional alignment)
    children_a = a.get("children", [])
    children_b = b.get("children", [])
    common = min(len(children_a), len(children_b))
    for i in range(common):
        child_path = f"{path}.{children_a[i]['tag']}[{i}]"
        _diff_node(children_a[i], children_b[i], path=child_path, out=out)
    for i in range(common, len(children_a)):
        out.append(L5xDiffEntry(path=f"{path}.[{i}]", op="removed", before=children_a[i]["tag"]))
    for i in range(common, len(children_b)):
        out.append(L5xDiffEntry(path=f"{path}.[{i}]", op="added", after=children_b[i]["tag"]))


__all__ = [
    "l5x_to_dict",
    "dict_to_l5x",
    "convert_l5x_file_to_json",
    "convert_json_file_to_l5x",
    "read_json",
    "write_json",
    "validate_l5x",
    "l5x_diff",
]
