"""Bounded CSV and paginated PDF exports without executing HTML or templates."""
import csv
import io
import textwrap
from decimal import Decimal,InvalidOperation


def safe_cell(value):
    if value is None:return ""
    text=str(value)
    if text.lstrip().startswith(("=","+","-","@")):
        try:
            if not Decimal(text).is_finite():raise InvalidOperation()
        except (InvalidOperation,ValueError):return "'"+text
    return text


def csv_bytes(rows):
    out=io.StringIO();writer=csv.writer(out)
    for row in rows:writer.writerow([safe_cell(value) for value in row])
    return out.getvalue().encode("utf-8-sig")


def pdf_bytes(lines):
    # Standard Courier/WinAnsi keeps numeric reports portable. Characters outside
    # that repertoire remain visible as Unicode escapes; CSV preserves Unicode.
    wrapped=[]
    for line in lines:
        encoded=str(line).encode("cp1252",errors="backslashreplace").decode("cp1252")
        wrapped.extend(textwrap.wrap(encoded,width=90,replace_whitespace=False,drop_whitespace=False) or [""])
    if len(wrapped)>5800:raise ValueError("PDF report exceeds the 100-page limit; use CSV or a smaller report")
    pages=[wrapped[index:index+58] for index in range(0,len(wrapped),58)] or [[""]]
    objects=[b"",b"",b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    page_ids=[]
    for page_number,body in enumerate(pages,1):
        page_id=len(objects)+1;content_id=page_id+1;page_ids.append(page_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        def literal(text):
            return text.replace("\\","\\\\").replace("(","\\(").replace(")","\\)").replace("\r"," ").replace("\n"," ").encode("cp1252")
        commands=[b"BT /F1 9 Tf 12 TL 36 800 Td"]
        for line in body:commands.extend([b"("+literal(line)+b") Tj",b"T*"])
        commands.extend([b"ET",b"BT /F1 8 Tf 36 28 Td ("+literal(f"NEXORA TWIN | Page {page_number} of {len(pages)}")+b") Tj ET"])
        stream=b"\n".join(commands)
        objects.append(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream")
    objects[0]=b"<< /Type /Catalog /Pages 2 0 R >>"
    kids=" ".join(f"{number} 0 R" for number in page_ids)
    objects[1]=f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode()
    out=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n");offsets=[0]
    for index,obj in enumerate(objects,1):
        offsets.append(len(out));out.extend(f"{index} 0 obj\n".encode()+obj+b"\nendobj\n")
    crossref=len(out);out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{crossref}\n%%EOF\n".encode())
    return bytes(out)
