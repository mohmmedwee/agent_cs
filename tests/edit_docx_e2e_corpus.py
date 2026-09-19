"""Fixed edit_docx e2e corpus builders (slice 7).

Each builder returns (filename, bytes). Cases are designed so the agent must
take a specific tool path; fixture-level assertions below verify the docs
themselves trigger the expected validator behavior.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _save(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _inject_into_first_matching_paragraph(
    data: bytes, needle: str, tag: str, attrs: dict[str, str] | None = None
) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    for p in root.iter(f"{W}p"):
        text = "".join(t.text or "" for t in p.iter(f"{W}t"))
        if needle in text:
            el = ET.SubElement(p, tag)
            for key, value in (attrs or {}).items():
                el.set(key, value)
            break
    else:
        raise LookupError(needle)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), "r") as src:
        with zipfile.ZipFile(out, "w") as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename == "word/document.xml":
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                dst.writestr(info, payload)
    return out.getvalue()


def build_simple_en() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Project status report")
    doc.add_paragraph("Status: Draft")
    doc.add_paragraph("Owner: Alice")
    return "e2e-simple-en.docx", _save(doc)


def build_simple_ar() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("تقرير الحالة")
    doc.add_paragraph("الحالة: مسودة")
    doc.add_paragraph("المالك: أحمد")
    return "e2e-simple-ar.docx", _save(doc)


def build_table_cell() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Delivery schedule")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Item"
    table.cell(0, 1).text = "Date"
    table.cell(1, 0).text = "Shipment"
    table.cell(1, 1).text = "2026-01-15"
    return "e2e-table.docx", _save(doc)


def build_multi_change() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Contract cover sheet")
    doc.add_paragraph("Effective date: 2025-06-01")
    doc.add_paragraph("Document owner: Bob Martinez")
    doc.add_paragraph("Other notes stay unchanged.")
    return "e2e-multi-change.docx", _save(doc)


def build_insert_base() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Executive summary")
    doc.add_paragraph("Background section.")
    doc.add_paragraph("Closing remarks.")
    return "e2e-insert.docx", _save(doc)


def build_ambiguous_dates() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Timeline")
    doc.add_paragraph("Kickoff date: 2026-01-01")
    doc.add_paragraph("Review date: 2026-02-01")
    doc.add_paragraph("Ship date: 2026-03-01")
    return "e2e-ambiguous-dates.docx", _save(doc)


def build_multi_run_span() -> tuple[str, bytes]:
    """Adjacent runs with different rPr — whole-span replace → multi_run_span."""
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("Effective ")
    bold = p.add_run("01-01-2026")
    bold.bold = True
    p.add_run(" until renewal.")
    return "e2e-multi-run.docx", _save(doc)


def build_tracked_changes() -> tuple[str, bytes]:
    doc = Document()
    doc.add_paragraph("Clause A remains editable.")
    doc.add_paragraph("Clause B has tracked changes text")
    data = _save(doc)
    return (
        "e2e-tracked.docx",
        _inject_into_first_matching_paragraph(
            data, "Clause B", f"{W}ins", {qn("w:author"): "Reviewer"}
        ),
    )


def build_footer_doc() -> tuple[str, bytes]:
    """Body is editable; footer text is out of edit_docx scope."""
    doc = Document()
    doc.add_paragraph("Body title")
    doc.add_paragraph("Body paragraph only.")
    section = doc.sections[0]
    footer = section.footer
    footer.is_linked_to_previous = False
    footer.paragraphs[0].text = "CONFIDENTIAL — footer v1"
    footer.paragraphs[0].runs[0].font.size = Pt(9)
    return "e2e-footer.docx", _save(doc)


def build_identical_rpr_merge() -> tuple[str, bytes]:
    """Two runs, same rPr — whole-span replace should merge (slice 6)."""
    doc = Document()
    p = doc.add_paragraph()
    r1 = p.add_run("Hello ")
    r2 = p.add_run("world")
    # Force identical rPr by clearing and sharing a lang hint only on first.
    for run in (r1, r2):
        run.font.name = "Calibri"
    return "e2e-rpr-merge.docx", _save(doc)


@dataclass(frozen=True)
class E2ECase:
    id: str
    prompt: str
    builder: Callable[[], tuple[str, bytes]]
    expect_tools: tuple[str, ...]
    forbid_tools: tuple[str, ...] = ("write_file", "convert_upload_to_docx")
    expect_ask: bool = False
    expect_explain: bool = False
    # Substrings that must appear in tip text after a successful edit.
    expect_text: tuple[str, ...] = ()
    # Substrings that must remain (formatting/content preservation smoke).
    preserve_text: tuple[str, ...] = ()
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


CASES: list[E2ECase] = [
    E2ECase(
        id="replace_en",
        prompt=(
            "In e2e-simple-en.docx, change Status: Draft to Status: Final. "
            "Use edit_docx. Keep everything else the same."
        ),
        builder=build_simple_en,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("Status: Final",),
        preserve_text=("Owner: Alice",),
        tags=("replace", "en"),
    ),
    E2ECase(
        id="replace_ar",
        prompt=(
            "في الملف e2e-simple-ar.docx غيّر «الحالة: مسودة» إلى «الحالة: نهائي». "
            "استخدم edit_docx فقط."
        ),
        builder=build_simple_ar,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("الحالة: نهائي",),
        preserve_text=("المالك: أحمد",),
        tags=("replace", "ar"),
    ),
    E2ECase(
        id="table_cell",
        prompt=(
            "In e2e-table.docx, change the Shipment date cell from "
            "2026-01-15 to 2026-02-20 using edit_docx."
        ),
        builder=build_table_cell,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("2026-02-20",),
        preserve_text=("Shipment",),
        tags=("table",),
    ),
    E2ECase(
        id="multi_change",
        prompt=(
            "In e2e-multi-change.docx, update the date to 2026-09-01 and the "
            "owner to Carol Nguyen in one edit_docx call."
        ),
        builder=build_multi_change,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("2026-09-01", "Carol Nguyen"),
        preserve_text=("Other notes stay unchanged.",),
        tags=("batch",),
    ),
    E2ECase(
        id="insert_section",
        prompt=(
            "In e2e-insert.docx, after the Executive summary paragraph, insert "
            "a new heading 'Findings' and then a short paragraph "
            "'No blocking issues.' using an edit_docx insert chain "
            "(new_1 / new_2)."
        ),
        builder=build_insert_base,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("Findings", "No blocking issues."),
        preserve_text=("Closing remarks.",),
        tags=("insert",),
    ),
    E2ECase(
        id="ambiguous_date",
        prompt=(
            "In e2e-ambiguous-dates.docx, change the date to 2026-12-31. "
            "There are multiple dates — do not guess."
        ),
        builder=build_ambiguous_dates,
        expect_tools=("ask_user",),
        forbid_tools=("write_file", "convert_upload_to_docx", "edit_docx"),
        expect_ask=True,
        tags=("ambiguous",),
    ),
    E2ECase(
        id="multi_run_span",
        prompt=(
            "In e2e-multi-run.docx, change the date 01-01-2026 to 02-02-2026. "
            "Prefer a replace that stays inside one run. Do not rewrite the "
            "whole paragraph and do not use run_python."
        ),
        builder=build_multi_run_span,
        expect_tools=("read_uploaded_file", "edit_docx"),
        forbid_tools=("write_file", "convert_upload_to_docx", "run_python"),
        expect_text=("02-02-2026",),
        preserve_text=("until renewal.",),
        tags=("multi_run",),
        notes="May first hit multi_run_span if old spans bold+plain; shorter old should work.",
    ),
    E2ECase(
        id="tracked_changes",
        prompt=(
            "In e2e-tracked.docx, try to edit Clause B to say "
            "'Clause B was revised'. If the tool rejects tracked changes, "
            "explain that to me instead of forcing a rewrite."
        ),
        builder=build_tracked_changes,
        expect_tools=("read_uploaded_file",),
        forbid_tools=("write_file", "convert_upload_to_docx"),
        expect_explain=True,
        tags=("tracked",),
    ),
    E2ECase(
        id="footer_unsupported",
        prompt=(
            "In e2e-footer.docx, change the footer text from "
            "'CONFIDENTIAL — footer v1' to 'CONFIDENTIAL — footer v2'. "
            "Body paragraphs must stay untouched."
        ),
        builder=build_footer_doc,
        expect_tools=("read_uploaded_file",),
        forbid_tools=("write_file", "convert_upload_to_docx", "edit_docx"),
        expect_explain=True,
        tags=("footer",),
        notes="Agent should explain edit_docx cannot touch footers, or use gated run_python.",
    ),
    E2ECase(
        id="rpr_merge_smoke",
        prompt=(
            "In e2e-rpr-merge.docx, replace 'Hello world' with 'Hi there' "
            "using edit_docx replace (not rewrite)."
        ),
        builder=build_identical_rpr_merge,
        expect_tools=("read_uploaded_file", "edit_docx"),
        expect_text=("Hi there",),
        tags=("merge",),
    ),
]


def all_fixtures() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for case in CASES:
        name, data = case.builder()
        out[name] = data
    return out
