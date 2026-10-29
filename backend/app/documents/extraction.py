"""Bounded extraction; never execute files, macros, formulas or embedded links."""
import io
import re
from dataclasses import dataclass
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from pypdf import PdfReader

from app.data.imports import MAX_BYTES, parse_file
from app.documents.ocr import pdf_pages

SUPPORTED = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}
MAX_TEXT = 200_000
MAX_CHUNKS = 300


@dataclass
class Section:
    text: str
    page: int | None = None
    heading: str | None = None
    kind: str = "prose"


def validate_upload(filename: str, raw: bytes):
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED or not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a nonempty PDF, DOCX, TXT, CSV or XLSX file up to 2 MiB")
    if extension == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("The file is not a PDF")
    if extension in {".docx", ".xlsx"}:
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                files = archive.infolist()
                if len(files) > 2000 or sum(f.file_size for f in files) > 20 * 1024 * 1024:
                    raise ValueError("Expanded document exceeds 20 MiB or 2000 entries")
                if any("vbaproject" in f.filename.lower() or "externallinks/" in f.filename.lower() for f in files):
                    raise ValueError("Macros and external spreadsheet links are unsupported")
                if extension == ".docx" and "word/document.xml" not in archive.namelist():
                    raise ValueError("The file is not a DOCX document")
        except BadZipFile as error:
            raise ValueError("The document archive is invalid") from error
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in raw:
        raise ValueError("The content check rejected this test signature")


def extract(filename: str, raw: bytes) -> list[Section]:
    validate_upload(filename, raw)
    extension = PurePath(filename).suffix.lower()
    sections = []
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are unsupported")
        if len(reader.pages) > 100:
            raise ValueError("PDFs may contain at most 100 pages")
        ocr = None
        for number, page in enumerate(reader.pages, 1):
            # Refuse very large decompressed content streams before text extraction.
            contents = page.get_contents()
            if contents and len(contents.get_data()) > 5 * 1024 * 1024:
                raise ValueError("A PDF page exceeds the processing limit")
            text = page.extract_text() or ""
            if not text.strip():
                ocr = pdf_pages(raw) if ocr is None else ocr
                text = ocr.get(number, "")
                if not text.strip():
                    raise ValueError("OCR did not return text for the scanned page")
            sections.append(Section(text, page=number))
    elif extension == ".docx":
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(io.BytesIO(raw)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        body = root.find("w:body", ns)
        if body is None:
            raise ValueError("DOCX body is missing")
        heading = None
        for node in body:
            if node.tag.endswith("}p"):
                text = "".join(item.text or "" for item in node.findall(".//w:t", ns))
                style = node.find("w:pPr/w:pStyle", ns)
                if style is not None and "heading" in next(iter(style.attrib.values()), "").lower():
                    heading = text[:200]
                if text.strip():
                    sections.append(Section(text, heading=heading))
            elif node.tag.endswith("}tbl"):
                for row in node.findall("w:tr", ns):
                    cells = [" ".join(part.text or "" for part in cell.findall(".//w:t", ns)) for cell in row.findall("w:tc", ns)]
                    sections.append(Section(" | ".join(cells), heading=heading, kind="table"))
    elif extension in {".csv", ".xlsx"}:
        columns, rows = parse_file(filename, raw)
        for row in rows:
            sections.append(Section(" | ".join(f"{key}: {row[key]}" for key in columns), heading="Table", kind="table"))
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("TXT files must use UTF-8") from error
        heading = None
        for paragraph in re.split(r"\n\s*\n", text):
            if paragraph.lstrip().startswith("#"):
                heading = paragraph.splitlines()[0].lstrip("# ")[:200]
            if paragraph.strip():
                sections.append(Section(paragraph, heading=heading))
    if not sections or sum(len(section.text) for section in sections) > MAX_TEXT:
        raise ValueError("Document must contain extractable text, at most 200000 characters")
    for section in sections:
        section.text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", section.text).strip()
    return sections


def chunk_sections(sections: list[Section], size=1200, overlap=150) -> list[Section]:
    if not 300 <= size <= 3000 or not 0 <= overlap < size // 2:
        raise ValueError("Unsupported chunk size/overlap")
    chunks = []
    for section in sections:
        text = section.text.strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    end = boundary
            chunks.append(Section(text[start:end], section.page, section.heading, section.kind))
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("Document exceeds 300 chunks; split it into smaller files")
            if end >= len(text):
                break
            start = end - min(overlap, end - start - 1)
    return chunks
