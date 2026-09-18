"""Building a real .docx from the Markdown the model writes.

`extraction` reads Word documents; this is the other direction. It exists
because encoding Markdown as UTF-8 and calling the result `report.docx` produces
a file Word refuses to open — the user asked for a document, not a text file
wearing a document's extension.

Stdlib-only, for the same reason extraction is: the server may run somewhere a
parser cannot be installed.

What survives the trip
----------------------
Blocks: ATX headings (1-6) and setext headings, paragraphs with soft wrapping,
fenced and indented code, blockquotes (nested), bullet / ordered / task lists
(nested, real Word numbering), GFM pipe tables with per-column alignment,
horizontal rules, page breaks, YAML front matter, HTML comments.
Inline: bold, italic, bold-italic, strikethrough, highlight, inline code,
links, autolinks, images, hard line breaks, backslash escapes.
Document: heading styles wired for the navigation pane, an optional field-based
table of contents and page-number footer, core properties, and bidirectional
paragraphs so Arabic and Hebrew lay out right-to-left without being asked.

Deliberately absent: footnotes, definition lists, and raw HTML blocks, each of
which needs a part or a parser this module does not carry. They pass through as
literal text rather than being dropped silently.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.sax.saxutils import escape

__all__ = ["DOCX_MEDIA_TYPE", "build_docx"]

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_CORE = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_CORE_REL = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
    "/metadata/core-properties"
)

# Word only treats a paragraph as a heading when the style carries the built-in
# name ("heading 1") and an outline level; without both, the navigation pane and
# any generated table of contents come out empty.
_HEADINGS = {1: 36, 2: 28, 3: 24, 4: 22, 5: 22, 6: 22}  # level -> half-points


@dataclass(frozen=True)
class _DocTheme:
    """Visual skin for styles.xml — one look per document, not one forever."""

    name: str
    body_font: str
    heading_font: str
    mono_font: str
    ink: str
    muted: str
    accent: str
    link: str
    code_fill: str
    rule: str
    body_size: int = 22  # half-points
    title_size: int = 52
    line: int = 276


# Named themes the model picks via YAML front matter (`theme: cleverso`).
_THEMES: dict[str, _DocTheme] = {
    "editorial": _DocTheme(
        name="editorial",
        body_font="Calibri",
        heading_font="Calibri",
        mono_font="Consolas",
        ink="1F2430",
        muted="4B5162",
        accent="1F2430",
        link="0563C1",
        code_fill="F3F4F6",
        rule="C9CDD6",
    ),
    "cleverso": _DocTheme(
        name="cleverso",
        body_font="Calibri",
        heading_font="Calibri",
        mono_font="Consolas",
        ink="181819",
        muted="6B7280",
        accent="673CDB",
        link="5833BA",
        code_fill="F8F5FF",
        rule="DCC7FF",
    ),
    "classic": _DocTheme(
        name="classic",
        body_font="Georgia",
        heading_font="Georgia",
        mono_font="Courier New",
        ink="2C1810",
        muted="6B5344",
        accent="8B4513",
        link="1A5276",
        code_fill="F5F0E8",
        rule="D4C4B0",
        body_size=24,
        title_size=56,
        line=300,
    ),
    "modern": _DocTheme(
        name="modern",
        body_font="Calibri",
        heading_font="Calibri Light",
        mono_font="Consolas",
        ink="111827",
        muted="6B7280",
        accent="0F766E",
        link="0D9488",
        code_fill="F0FDFA",
        rule="99F6E4",
        title_size=48,
    ),
    "warm": _DocTheme(
        name="warm",
        body_font="Calibri",
        heading_font="Calibri",
        mono_font="Consolas",
        ink="292524",
        muted="78716C",
        accent="C2410C",
        link="B45309",
        code_fill="FFF7ED",
        rule="FED7AA",
    ),
}

_DEFAULT_THEME = "editorial"


def _resolve_theme(name: str | None) -> _DocTheme:
    key = (name or _DEFAULT_THEME).strip().lower()
    return _THEMES.get(key, _THEMES[_DEFAULT_THEME])


# A4 minus one-inch margins, in twips; also the table and image width budget.
_CONTENT_TWIPS = 9026
_TWIP_EMU = 635
_PIXEL_EMU = 9525  # 914400 EMU per inch / 96 px per inch

_RTL_CHARS = re.compile(
    "[\u0590-\u05ff\u0600-\u06ff\u0700-\u074f\u0750-\u077f"
    "\u08a0-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]"
)
# XML 1.0 forbids most control characters outright — no escaping saves them.
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


# --------------------------------------------------------------------------
# Static package parts
# --------------------------------------------------------------------------

_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _heading_style(level: int, size: int, theme: _DocTheme) -> str:
    italic = "<w:i/><w:iCs/>" if level >= 5 else ""
    color = theme.accent if level <= 2 else theme.ink
    return (
        f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
        f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="400" w:after="160"/>'
        f'<w:outlineLvl w:val="{level - 1}"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{theme.heading_font}" '
        f'w:hAnsi="{theme.heading_font}" w:cs="{theme.heading_font}"/>'
        f'<w:b/><w:bCs/>{italic}<w:color w:val="{color}"/>'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr></w:style>'
    )


def _styles_xml(theme: _DocTheme) -> str:
    """Build styles.xml for one theme — every .docx used to share one skin."""
    return (
        _DECL + f'<w:styles xmlns:w="{_W}">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        f'<w:rFonts w:ascii="{theme.body_font}" w:hAnsi="{theme.body_font}" '
        f'w:cs="{theme.body_font}"/>'
        f'<w:sz w:val="{theme.body_size}"/><w:szCs w:val="{theme.body_size}"/>'
        f'<w:color w:val="{theme.ink}"/>'
        "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
        f'<w:spacing w:after="160" w:line="{theme.line}" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont">'
        '<w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/>'
        "<w:semiHidden/><w:unhideWhenUsed/></w:style>"
        + "".join(
            _heading_style(level, size, theme) for level, size in _HEADINGS.items()
        )
        + '<w:style w:type="paragraph" w:styleId="Title">'
        '<w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="240"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{theme.heading_font}" '
        f'w:hAnsi="{theme.heading_font}" w:cs="{theme.heading_font}"/>'
        f'<w:b/><w:bCs/><w:sz w:val="{theme.title_size}"/>'
        f'<w:szCs w:val="{theme.title_size}"/>'
        f'<w:color w:val="{theme.accent}"/></w:rPr></w:style>'
        # The contents heading must not carry an outline level, or the table of
        # contents lists itself as its own first entry.
        '<w:style w:type="paragraph" w:styleId="TOCHeading">'
        '<w:name w:val="TOC Heading"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:uiPriority w:val="39"/><w:qFormat/>'
        '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr>'
        f'<w:rPr><w:b/><w:bCs/><w:sz w:val="36"/><w:szCs w:val="36"/>'
        f'<w:color w:val="{theme.ink}"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Code">'
        '<w:name w:val="HTML Preformatted"/><w:basedOn w:val="Normal"/>'
        f'<w:pPr><w:shd w:val="clear" w:color="auto" w:fill="{theme.code_fill}"/>'
        '<w:spacing w:after="160" w:line="240" w:lineRule="auto"/>'
        '<w:ind w:left="360"/></w:pPr><w:rPr>'
        f'<w:rFonts w:ascii="{theme.mono_font}" w:hAnsi="{theme.mono_font}" '
        f'w:cs="{theme.mono_font}"/>'
        '<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Quote">'
        '<w:name w:val="Quote"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" '
        f'w:color="{theme.accent}"/></w:pBdr><w:spacing w:after="120"/>'
        '<w:ind w:left="360"/></w:pPr>'
        f'<w:rPr><w:i/><w:iCs/><w:color w:val="{theme.muted}"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ListParagraph">'
        '<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
        '<w:uiPriority w:val="34"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="60"/><w:contextualSpacing/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="HorizontalRule">'
        '<w:name w:val="Horizontal Rule"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/>'
        '<w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" '
        f'w:color="{theme.rule}"/></w:pBdr><w:spacing w:before="120" w:after="240"/>'
        "</w:pPr></w:style>"
        '<w:style w:type="character" w:styleId="Hyperlink">'
        '<w:name w:val="Hyperlink"/><w:basedOn w:val="DefaultParagraphFont"/>'
        '<w:uiPriority w:val="99"/><w:unhideWhenUsed/>'
        f'<w:rPr><w:color w:val="{theme.link}"/><w:u w:val="single"/></w:rPr></w:style>'
        "</w:styles>"
    )


# Kept so older call sites / tests that imported the constant still resolve;
# new packages always go through `_styles_xml(theme)`.
_STYLES = _styles_xml(_THEMES[_DEFAULT_THEME])

_BULLET_GLYPHS = ("\u2022", "o", "\u25aa")
_BULLET_FONTS = ("Symbol", "Courier New", "Wingdings")
_NUMBER_FORMATS = ("decimal", "lowerLetter", "lowerRoman")


def _numbering(ordered_ids: list[int]) -> str:
    """Nine indent levels of bullets and of restartable numbers.

    Every ordered list gets its own `w:num` pointing at the shared abstract
    definition, which is how Word is told to start counting from one again
    rather than continuing the previous list.
    """
    bullets = "".join(
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/>'
        '<w:numFmt w:val="bullet"/>'
        f'<w:lvlText w:val="{_BULLET_GLYPHS[i % 3]}"/><w:lvlJc w:val="left"/>'
        f'<w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{_BULLET_FONTS[i % 3]}" '
        f'w:hAnsi="{_BULLET_FONTS[i % 3]}" w:hint="default"/></w:rPr></w:lvl>'
        for i in range(9)
    )
    numbers = "".join(
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/>'
        f'<w:numFmt w:val="{_NUMBER_FORMATS[i % 3]}"/>'
        f'<w:lvlText w:val="%{i + 1}."/><w:lvlJc w:val="left"/>'
        f'<w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr></w:lvl>'
        for i in range(9)
    )
    instances = '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>' + "".join(
        f'<w:num w:numId="{num_id}"><w:abstractNumId w:val="1"/></w:num>'
        for num_id in ordered_ids
    )
    return (
        _DECL + f'<w:numbering xmlns:w="{_W}">'
        '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
        f"{bullets}</w:abstractNum>"
        '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="multilevel"/>'
        f"{numbers}</w:abstractNum>{instances}</w:numbering>"
    )


def _settings(update_fields: bool) -> str:
    fields = '<w:updateFields w:val="true"/>' if update_fields else ""
    return (
        _DECL + f'<w:settings xmlns:w="{_W}">'
        '<w:defaultTabStop w:val="720"/>'
        f"{fields}<w:compat><w:compatSetting w:name=\"compatibilityMode\" "
        'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
        "</w:settings>"
    )


_FOOTER = (
    _DECL + f'<w:ftr xmlns:w="{_W}"><w:p>'
    '<w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>1</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
)


def _core_properties(title: str, author: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        _DECL + f'<cp:coreProperties xmlns:cp="{_CORE}" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        f"<dc:creator>{escape(author)}</dc:creator>"
        f"<cp:lastModifiedBy>{escape(author)}</cp:lastModifiedBy>"
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
        f"<dc:title>{escape(title)}</dc:title></cp:coreProperties>"
    )


def _content_types(extensions: set[str], parts: list[str]) -> str:
    defaults = "".join(
        f'<Default Extension="{ext}" ContentType="image/{"jpeg" if ext in ("jpg", "jpeg") else ext}"/>'
        for ext in sorted(extensions)
    )
    overrides = "".join(parts)
    return (
        _DECL
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{defaults}"
        f'<Override PartName="/word/document.xml" ContentType="{DOCX_MEDIA_TYPE}.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        f"{overrides}</Types>"
    )


_ROOT_RELS = (
    _DECL + f'<Relationships xmlns="{_PKG}">'
    f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="word/document.xml"/>'
    f'<Relationship Id="rId2" Type="{_CORE_REL}" Target="docProps/core.xml"/>'
    "</Relationships>"
)


# --------------------------------------------------------------------------
# Image measurement
# --------------------------------------------------------------------------


def _image_size(data: bytes) -> tuple[int, int] | None:
    """Pixel dimensions of a PNG, JPEG or GIF, or None if unrecognised.

    Word needs an explicit extent on every inline drawing; there is no
    "natural size" it can fall back to, so an image we cannot measure is an
    image we cannot place.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                offset += 2
                continue
            length = int.from_bytes(data[offset + 2 : offset + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height = int.from_bytes(data[offset + 5 : offset + 7], "big")
                width = int.from_bytes(data[offset + 7 : offset + 9], "big")
                return width, height
            offset += 2 + length
    return None


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


def _text(value: str) -> str:
    return escape(_ILLEGAL.sub("", value))


def _run(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    strike: bool = False,
    mono: bool = False,
    mark: bool = False,
    size: int = 0,
    style: str = "",
    color: str = "",
) -> str:
    """One run. Child order follows the schema, or Word rejects the part.

    A newline in `text` becomes a hard line break rather than a new paragraph,
    which is what Markdown's two-space line ending means.
    """
    rtl = bool(_RTL_CHARS.search(text))
    parts: list[str] = []
    if style:
        parts.append(f'<w:rStyle w:val="{style}"/>')
    if mono:
        parts.append(
            '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
        )
    if bold:
        parts.append("<w:b/><w:bCs/>")
    if italic:
        parts.append("<w:i/><w:iCs/>")
    if strike:
        parts.append("<w:strike/>")
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    if size:
        parts.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if mark:
        parts.append('<w:highlight w:val="yellow"/>')
    if rtl:
        parts.append("<w:rtl/>")
    properties = f"<w:rPr>{''.join(parts)}</w:rPr>" if parts else ""

    segments = text.split("\n")
    body = '<w:br/>'.join(
        f'<w:t xml:space="preserve">{_text(segment)}</w:t>' for segment in segments
    )
    return f"<w:r>{properties}{body}</w:r>"


def _drawing(rel_id: str, width: int, height: int, alt: str, uid: int) -> str:
    """An inline picture, scaled down if it would run past the margins."""
    emu_w, emu_h = width * _PIXEL_EMU, height * _PIXEL_EMU
    limit = _CONTENT_TWIPS * _TWIP_EMU
    if emu_w > limit:
        emu_h = max(1, round(emu_h * limit / emu_w))
        emu_w = limit
    name = _text(alt) or f"Picture {uid}"
    return (
        "<w:r><w:drawing>"
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{emu_w}" cy="{emu_h}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{uid}" name="Picture {uid}" descr="{name}"/>'
        "<wp:cNvGraphicFramePr>"
        '<a:graphicFrameLocks noChangeAspect="1"/>'
        "</wp:cNvGraphicFramePr>"
        f'<a:graphic><a:graphicData uri="{_PIC}">'
        "<pic:pic><pic:nvPicPr>"
        f'<pic:cNvPr id="{uid}" name="Picture {uid}" descr="{name}"/>'
        "<pic:cNvPicPr/></pic:nvPicPr>"
        f'<pic:blipFill><a:blip r:embed="{rel_id}"/>'
        "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{emu_w}" cy="{emu_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )


def _paragraph(
    runs: str,
    *,
    style: str = "",
    indent: int = 0,
    hanging: bool = False,
    num: tuple[int, int] | None = None,
    align: str = "",
    rtl: bool = False,
    spacing: int = -1,
) -> str:
    parts: list[str] = []
    if style:
        parts.append(f'<w:pStyle w:val="{style}"/>')
    if num is not None:
        parts.append(
            f'<w:numPr><w:ilvl w:val="{num[0]}"/><w:numId w:val="{num[1]}"/></w:numPr>'
        )
    if rtl:
        parts.append("<w:bidi/>")
    if spacing >= 0:
        parts.append(f'<w:spacing w:after="{spacing}"/>')
    if indent:
        suffix = ' w:hanging="360"' if hanging else ""
        parts.append(f'<w:ind w:left="{indent}"{suffix}/>')
    if align:
        parts.append(f'<w:jc w:val="{align}"/>')
    properties = f"<w:pPr>{''.join(parts)}</w:pPr>" if parts else ""
    return f"<w:p>{properties}{runs}</w:p>"


# --------------------------------------------------------------------------
# Inline grammar
# --------------------------------------------------------------------------

_INLINE = re.compile(
    r"\\(?P<escape>[\\`*_{}\[\]()#+\-.!~>|=])"
    r"|!\[(?P<image_alt>[^\]]*)\]\((?P<image_src>[^)\s]*)(?:\s+\"[^\"]*\")?\)"
    r"|\[(?P<link_text>[^\]]*)\]\((?P<link_href>[^)\s]*)(?:\s+\"[^\"]*\")?\)"
    r"|<(?P<autolink>(?:https?://|mailto:)[^>\s]+)>"
    r"|(?P<ticks>`+)(?P<code>.+?)(?P=ticks)"
    r"|\*\*\*(?P<strong_em>[^*]+)\*\*\*"
    r"|\*\*(?P<bold>[^*]+)\*\*"
    r"|__(?P<bold_alt>[^_]+)__"
    r"|~~(?P<strike>[^~]+)~~"
    r"|==(?P<mark>[^=]+)=="
    r"|\*(?P<italic>[^*]+)\*"
    r"|(?<![A-Za-z0-9])_(?P<italic_alt>[^_]+)_(?![A-Za-z0-9])"
)
_HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*")
_BULLET = re.compile(r"[-*+]\s+(.*)")
_NUMBERED = re.compile(r"(\d{1,9})[.)]\s+(.*)")
_TASK = re.compile(r"[-*+]\s+\[([ xX])\]\s+(.*)")
_RULE = re.compile(r"^\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_SETEXT = re.compile(r"^\s*(=+|-+)\s*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
_PAGE_BREAK = re.compile(r"^\s*(?:\\pagebreak|\\newpage|<!--\s*pagebreak\s*-->)\s*$", re.I)


class _Document:
    """Accumulates the body along with the parts it forces into existence.

    Hyperlinks and images are relationships, and numbered lists are entries in
    the numbering part, so none of them can be resolved by a pure
    text-to-text transformation — the parser has to collect them as it goes.
    """

    def __init__(self, base_dir: str | None, images: dict[str, bytes] | None):
        self.base_dir = base_dir
        self.images = dict(images or {})
        self.rels: list[str] = []
        self.media: dict[str, bytes] = {}
        self.extensions: set[str] = set()
        self.ordered_ids: list[int] = []
        self.headings: int = 0
        self._rel_seq = 100
        self._uid = 1000

    # -- resources ---------------------------------------------------------

    def _rel(self, kind: str, target: str, external: bool = False) -> str:
        self._rel_seq += 1
        rel_id = f"rId{self._rel_seq}"
        mode = ' TargetMode="External"' if external else ""
        self.rels.append(
            f'<Relationship Id="{rel_id}" Type="{_REL}/{kind}" '
            f'Target="{escape(target, {chr(34): "&quot;"})}"{mode}/>'
        )
        return rel_id

    def hyperlink(self, href: str) -> str:
        return self._rel("hyperlink", href, external=True)

    def next_ordered_id(self) -> int:
        num_id = 2 + len(self.ordered_ids)
        self.ordered_ids.append(num_id)
        return num_id

    def _load(self, src: str) -> bytes | None:
        if src in self.images:
            return self.images[src]
        if src.startswith(("http://", "https://", "data:")):
            return None  # no network, and no base64 decoder worth the surface
        path = src if os.path.isabs(src) else os.path.join(self.base_dir or "", src)
        try:
            if os.path.getsize(path) > 32 * 1024 * 1024:
                return None
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def image(self, src: str, alt: str) -> str:
        """An inline picture, or the alt text when the source cannot be used."""
        data = self._load(src)
        size = _image_size(data) if data else None
        if not data or not size:
            return _run(alt or src, italic=True)
        extension = {b"\x89P": "png", b"GI": "gif", b"\xff\xd8": "jpeg"}[data[:2]]
        self.extensions.add(extension)
        name = f"image{len(self.media) + 1}.{extension}"
        self.media[name] = data
        rel_id = self._rel("image", f"media/{name}")
        self._uid += 1
        return _drawing(rel_id, size[0], size[1], alt, self._uid)

    # -- inline ------------------------------------------------------------

    def inline(
        self, text: str, *, bold: bool = False, size: int = 0, color: str = ""
    ) -> str:
        """Markdown emphasis within one paragraph, as a sequence of Word runs.

        `bold` and `size` carry heading formatting onto every run. Headings
        already name a style, but readers that ignore the styles part — Quick
        Look and Pages among them — would otherwise show them at body size.
        """
        runs: list[str] = []
        position = 0
        for match in _INLINE.finditer(text):
            if match.start() > position:
                runs.append(
                    _run(text[position : match.start()], bold=bold, size=size, color=color)
                )
            if (escaped := match.group("escape")) is not None:
                runs.append(_run(escaped, bold=bold, size=size, color=color))
            elif match.group("image_src") is not None:
                runs.append(self.image(match.group("image_src"), match.group("image_alt")))
            elif (href := match.group("link_href")) is not None:
                label = match.group("link_text") or href
                rel_id = self.hyperlink(href)
                runs.append(
                    f'<w:hyperlink r:id="{rel_id}">'
                    f"{self.inline(label, bold=bold, size=size, color=color) if _INLINE.search(label) else _run(label, bold=bold, size=size, color=color, style='Hyperlink')}"
                    "</w:hyperlink>"
                )
            elif (url := match.group("autolink")) is not None:
                rel_id = self.hyperlink(url)
                runs.append(
                    f'<w:hyperlink r:id="{rel_id}">'
                    f"{_run(url, size=size, style='Hyperlink')}</w:hyperlink>"
                )
            elif (code := match.group("code")) is not None:
                runs.append(_run(code, bold=bold, mono=True, size=size, color=color))
            elif (strong := match.group("strong_em")) is not None:
                runs.append(_run(strong, bold=True, italic=True, size=size, color=color))
            elif (emphasis := match.group("bold") or match.group("bold_alt")) is not None:
                runs.append(_run(emphasis, bold=True, size=size, color=color))
            elif (struck := match.group("strike")) is not None:
                runs.append(_run(struck, bold=bold, strike=True, size=size, color=color))
            elif (marked := match.group("mark")) is not None:
                runs.append(_run(marked, bold=bold, mark=True, size=size, color=color))
            else:
                italic = match.group("italic") or match.group("italic_alt") or ""
                runs.append(_run(italic, bold=bold, italic=True, size=size, color=color))
            position = match.end()
        if position < len(text):
            runs.append(_run(text[position:], bold=bold, size=size, color=color))
        return "".join(runs) or _run("", bold=bold, size=size, color=color)


def _is_rtl(text: str) -> bool:
    """Right-to-left when the script leans that way, not on the first letter.

    Technical Arabic prose is full of Latin product names; deciding per
    paragraph on the balance of strong characters keeps those paragraphs
    right-aligned instead of flipping on a stray "Kubernetes".
    """
    rtl = len(_RTL_CHARS.findall(text))
    ltr = len(re.findall(r"[A-Za-z]", text))
    return rtl > 0 and rtl >= ltr


def _table_cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    # A escaped pipe is content, not a column boundary.
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]


def _alignments(rule: str) -> list[str]:
    result = []
    for cell in _table_cells(rule):
        left, right = cell.startswith(":"), cell.endswith(":")
        result.append("center" if left and right else "right" if right else "")
    return result


class _Blocks:
    """Line-oriented block parser.

    Markdown's block grammar is regular enough that a single pass with a
    little lookahead handles everything here; the state that survives between
    lines is the current list nesting and the paragraph being accumulated.
    """

    def __init__(self, document: _Document, theme: _DocTheme):
        self.doc = document
        self.theme = theme
        self.out: list[str] = []
        self.pending: list[str] = []
        self.list_ids: dict[int, int] = {}
        self.in_list = False

    # -- helpers -----------------------------------------------------------

    def emit(self, xml: str) -> None:
        self.out.append(xml)

    def flush(self) -> None:
        if not self.pending:
            return
        # Wrapped lines join with a space; a hard break already ended its line,
        # so the space the join adds after it has to come back off.
        text = " ".join(self.pending).replace("\n ", "\n")
        self.pending.clear()
        self.emit(
            _paragraph(self.doc.inline(text), rtl=_is_rtl(text))
        )

    def end_list(self) -> None:
        self.in_list = False
        self.list_ids.clear()

    def numbering(self, level: int, ordered: bool) -> tuple[int, int]:
        if not ordered:
            return level, 1
        # Deeper levels restart whenever their parent moves on, which is what
        # dropping the stale ids below the current level accomplishes.
        for depth in [d for d in self.list_ids if d > level]:
            del self.list_ids[depth]
        if level not in self.list_ids or not self.in_list:
            self.list_ids[level] = self.doc.next_ordered_id()
        return level, self.list_ids[level]

    # -- the pass ----------------------------------------------------------

    def run(self, markdown: str) -> str:
        lines = _COMMENT.sub(
            lambda m: "\n" if "pagebreak" not in m.group(0).lower() else m.group(0),
            markdown.replace("\r\n", "\n").replace("\r", "\n"),
        ).split("\n")
        lines = [line.replace("\t", "    ") for line in lines]

        index = 0
        while index < len(lines):
            raw = lines[index]
            line = raw.strip()
            indent = len(raw) - len(raw.lstrip(" "))
            level = min(indent // 2, 8)

            if _PAGE_BREAK.match(line):
                self.flush()
                self.end_list()
                self.emit("<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>")
                index += 1
                continue

            if fence := _FENCE.match(raw):
                self.flush()
                self.end_list()
                marker = fence.group(1)[:3]
                index += 1
                code: list[str] = []
                while index < len(lines) and not lines[index].strip().startswith(marker):
                    code.append(lines[index][indent:] if lines[index][:indent].isspace() else lines[index])
                    index += 1
                self.emit(self._code(code))
                index += 1
                continue

            if not line:
                self.flush()
                index += 1
                continue

            # Setext headings are only headings when there is a line above to
            # be the heading; otherwise `---` is a rule.
            if (setext := _SETEXT.match(raw)) and self.pending:
                text = " ".join(self.pending)
                self.pending.clear()
                self.emit(self._heading(1 if setext.group(1)[0] == "=" else 2, text))
                index += 1
                continue

            if _RULE.match(raw):
                self.flush()
                self.end_list()
                self.emit(_paragraph("", style="HorizontalRule"))
                index += 1
                continue

            if heading := _HEADING.fullmatch(line):
                self.flush()
                self.end_list()
                self.emit(self._heading(len(heading.group(1)), heading.group(2)))
                index += 1
                continue

            if line.startswith(">"):
                self.flush()
                self.end_list()
                index = self._blockquote(lines, index)
                continue

            if "|" in line and index + 1 < len(lines) and _TABLE_RULE.match(lines[index + 1]) and "|" in lines[index + 1]:
                self.flush()
                self.end_list()
                index = self._table(lines, index)
                continue

            if task := _TASK.fullmatch(line):
                self.flush()
                checked = task.group(1).lower() == "x"
                self.emit(self._task(level, checked, task.group(2)))
                self.in_list = True
                index += 1
                continue

            if bullet := _BULLET.fullmatch(line):
                self.flush()
                index = self._item(lines, index, level, ordered=False, text=bullet.group(1))
                continue

            if numbered := _NUMBERED.fullmatch(line):
                self.flush()
                index = self._item(lines, index, level, ordered=True, text=numbered.group(2))
                continue

            # Four spaces of indent with no list in sight is a code block.
            if indent >= 4 and not self.in_list and not self.pending:
                self.flush()
                code = []
                while index < len(lines) and (not lines[index].strip() or lines[index].startswith("    ")):
                    code.append(lines[index][4:])
                    index += 1
                while code and not code[-1].strip():
                    code.pop()
                self.emit(self._code(code))
                continue

            self.end_list()
            self.pending.append(_BREAK_TAG.sub("\n", raw.rstrip()) + ("\n" if raw.endswith("  ") or raw.rstrip().endswith("\\") else ""))
            if self.pending[-1].rstrip("\n").endswith("\\"):
                self.pending[-1] = self.pending[-1].rstrip("\n")[:-1] + "\n"
            index += 1

        self.flush()
        return "".join(self.out) or _paragraph(_run(""))

    # -- block builders ----------------------------------------------------

    def _heading(self, level: int, text: str) -> str:
        level = min(level, 6)
        self.doc.headings += 1
        size = _HEADINGS[level]
        return _paragraph(
            self.doc.inline(text, bold=True, size=size),
            style=f"Heading{level}",
            rtl=_is_rtl(text),
        )

    def _code(self, lines: list[str]) -> str:
        runs = []
        for position, line in enumerate(lines):
            if position:
                runs.append("<w:r><w:br/></w:r>")
            runs.append(_run(line, mono=True))
        return _paragraph("".join(runs) or _run("", mono=True), style="Code")

    def _task(self, level: int, checked: bool, text: str) -> str:
        # A checkbox is a glyph, not a numbering format, so these keep the
        # manual hanging indent that real lists no longer need.
        box = "\u2612\t" if checked else "\u2610\t"
        return _paragraph(
            _run(box) + self.doc.inline(text),
            style="ListParagraph",
            indent=720 * (level + 1),
            hanging=True,
            rtl=_is_rtl(text),
        )

    def _item(self, lines: list[str], index: int, level: int, *, ordered: bool, text: str) -> int:
        ilvl, num_id = self.numbering(level, ordered)
        parts = [text]
        # Continuation lines belong to the item they are indented under.
        index += 1
        while index < len(lines):
            nxt = lines[index]
            stripped = nxt.strip()
            if not stripped or stripped.startswith((">", "#", "|", "```", "~~~")):
                break
            if _BULLET.fullmatch(stripped) or _NUMBERED.fullmatch(stripped):
                break
            if len(nxt) - len(nxt.lstrip(" ")) < level * 2 + 2:
                break
            parts.append(stripped)
            index += 1
        joined = " ".join(parts)
        self.emit(
            _paragraph(
                self.doc.inline(joined),
                style="ListParagraph",
                num=(ilvl, num_id),
                rtl=_is_rtl(joined),
            )
        )
        self.in_list = True
        return index

    def _blockquote(self, lines: list[str], index: int) -> int:
        """A quote is a paragraph per blank line, indented by its `>` depth."""
        groups: list[tuple[int, list[str]]] = []
        while index < len(lines) and lines[index].strip().startswith(">"):
            stripped = lines[index].strip()
            depth = len(stripped) - len(stripped.lstrip(">"))
            text = stripped.lstrip(">").strip()
            if not text:
                groups.append((depth, []))
            elif groups and groups[-1][0] == depth and groups[-1][1]:
                groups[-1][1].append(text)
            else:
                groups.append((depth, [text]))
            index += 1

        for depth, parts in groups:
            if not parts:
                continue
            text = " ".join(parts)
            self.emit(
                _paragraph(
                    self.doc.inline(text),
                    style="Quote",
                    indent=360 * depth,
                    rtl=_is_rtl(text),
                )
            )
        return index

    def _table(self, lines: list[str], index: int) -> int:
        header = _table_cells(lines[index])
        alignments = _alignments(lines[index + 1])
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            rows.append(_table_cells(lines[index]))
            index += 1

        columns = max([len(header), *(len(row) for row in rows)] or [1])
        alignments += [""] * (columns - len(alignments))
        width = _CONTENT_TWIPS // columns
        grid = "".join(f'<w:gridCol w:w="{width}"/>' for _ in range(columns))
        theme = self.theme

        def cell(text: str, position: int, head: bool, zebra: bool = False) -> str:
            if head:
                fill = theme.accent
                ink = "FFFFFF"
            elif zebra:
                fill = theme.code_fill
                ink = ""
            else:
                fill = ""
                ink = ""
            shading = (
                f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
            )
            return (
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shading}'
                '<w:vAlign w:val="center"/></w:tcPr>'
                + _paragraph(
                    self.doc.inline(text, bold=head, color=ink),
                    align=alignments[position],
                    rtl=_is_rtl(text),
                    spacing=80 if head else 60,
                )
                + "</w:tc>"
            )

        def row(cells: list[str], head: bool, zebra: bool = False) -> str:
            cells = cells + [""] * (columns - len(cells))
            properties = (
                "<w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>"
                if head
                else "<w:trPr><w:cantSplit/></w:trPr>"
            )
            return (
                f"<w:tr>{properties}"
                + "".join(
                    cell(text, position, head, zebra)
                    for position, text in enumerate(cells)
                )
                + "</w:tr>"
            )

        borders = "".join(
            f'<w:{edge} w:val="single" w:sz="4" w:space="0" w:color="{theme.rule}"/>'
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        # A right-to-left table reads from the rightmost column, which is a
        # property of the table rather than of the text inside it.
        bidi = (
            "<w:bidiVisual/>"
            if _is_rtl(" ".join(header + [text for row in rows for text in row]))
            else ""
        )
        self.emit(
            f"<w:tbl><w:tblPr>{bidi}"
            f'<w:tblW w:w="{_CONTENT_TWIPS}" w:type="dxa"/>'
            f"<w:tblBorders>{borders}</w:tblBorders>"
            '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="120" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" '
            'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
            f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>"
            + row(header, True)
            + "".join(
                row(cells, False, zebra=(row_index % 2 == 1))
                for row_index, cells in enumerate(rows)
            )
            + "</w:tbl>"
            # A table may not be the last block in a body; Word wants a
            # paragraph after it to anchor the cursor.
            + _paragraph("")
        )
        return index


# --------------------------------------------------------------------------
# Front matter
# --------------------------------------------------------------------------


def _front_matter(markdown: str) -> tuple[str, dict[str, str]]:
    if not markdown.startswith("---"):
        return markdown, {}
    lines = markdown.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return markdown, {}
    meta: dict[str, str] = {}
    for position in range(1, len(lines)):
        if lines[position].strip() in ("---", "..."):
            return "\n".join(lines[position + 1 :]), meta
        key, separator, value = lines[position].partition(":")
        if separator:
            meta[key.strip().lower()] = value.strip().strip("\"'")
    return markdown, {}


def _toc(depth: int = 3) -> str:
    """A field, not a rendered list — Word fills it in on open or on F9."""
    return _paragraph(
        _run("Contents", bold=True, size=36), style="TOCHeading"
    ) + _paragraph(
        '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> TOC \\o "1-{depth}" \\h \\z \\u </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + _run("Right-click and choose Update Field to build the table of contents.", italic=True)
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def build_docx(
    markdown: str,
    *,
    title: str = "",
    author: str = "",
    theme: str | None = None,
    toc: bool = False,
    page_numbers: bool = False,
    base_dir: str | None = None,
    images: dict[str, bytes] | None = None,
    rtl: bool = False,
) -> bytes:
    """A Word document carrying the given Markdown as formatted paragraphs.

    `toc` inserts a table-of-contents field ahead of the body, `page_numbers`
    a centred page number in the footer, and `rtl` sets the whole section
    right-to-left for documents that are Arabic or Hebrew throughout —
    individual paragraphs are detected on their own either way. `images`
    supplies picture bytes by their Markdown source, for callers that have
    them in hand; anything not supplied is read relative to `base_dir`.

    Explicit kwargs override YAML front matter for `theme`, `toc`,
    `page_numbers` / `pages`, and `rtl` (used by convert-from-upload tools).
    """
    markdown, meta = _front_matter(markdown)
    title = title or meta.get("title", "")
    author = author or meta.get("author", "")
    theme = _resolve_theme(theme or meta.get("theme"))
    toc = toc or _truthy(meta.get("toc"))
    page_numbers = page_numbers or _truthy(
        meta.get("page_numbers") or meta.get("pages")
    )
    rtl = rtl or _truthy(meta.get("rtl"))

    document_parts = _Document(base_dir, images)
    body = _Blocks(document_parts, theme).run(markdown)

    heading = (
        _paragraph(document_parts.inline(title, bold=True, size=theme.title_size), style="Title", rtl=_is_rtl(title))
        if title and meta.get("title")
        else ""
    )
    contents = _toc() if toc and document_parts.headings else ""

    footer_reference = (
        '<w:footerReference w:type="default" r:id="rId3"/>' if page_numbers else ""
    )
    section = (
        f"<w:sectPr>{footer_reference}"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"'
        ' w:header="708" w:footer="708" w:gutter="0"/>'
        f'<w:cols w:space="708"/>{"<w:bidi/>" if rtl else ""}</w:sectPr>'
    )

    document = (
        _DECL + f'<w:document xmlns:w="{_W}" xmlns:r="{_REL}" xmlns:wp="{_WP}" '
        f'xmlns:a="{_A}" xmlns:pic="{_PIC}"><w:body>'
        f"{heading}{contents}{body}{section}</w:body></w:document>"
    )

    document_rels = (
        _DECL + f'<Relationships xmlns="{_PKG}">'
        f'<Relationship Id="rId1" Type="{_REL}/styles" Target="styles.xml"/>'
        f'<Relationship Id="rId2" Type="{_REL}/numbering" Target="numbering.xml"/>'
        + (
            f'<Relationship Id="rId3" Type="{_REL}/footer" Target="footer1.xml"/>'
            if page_numbers
            else ""
        )
        + f'<Relationship Id="rId4" Type="{_REL}/settings" Target="settings.xml"/>'
        + "".join(document_parts.rels)
        + "</Relationships>"
    )

    overrides = []
    if page_numbers:
        overrides.append(
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # `[Content_Types].xml` must be the first part in the package.
        archive.writestr(
            "[Content_Types].xml",
            _content_types(document_parts.extensions, overrides),
        )
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("docProps/core.xml", _core_properties(title, author))
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/styles.xml", _styles_xml(theme))
        archive.writestr("word/numbering.xml", _numbering(document_parts.ordered_ids))
        archive.writestr("word/settings.xml", _settings(toc))
        if page_numbers:
            archive.writestr("word/footer1.xml", _FOOTER)
        for name, data in document_parts.media.items():
            archive.writestr(f"word/media/{name}", data)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()
