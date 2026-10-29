import io
from uuid import uuid4
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from app.core.exporting import csv_bytes,pdf_bytes
from app.reports.schemas import ReportInput


def test_pdf_is_paginated_extractable_and_escapes_control_characters():
    data=pdf_bytes(["Nexa (demo) \\ source"]+[f"Revenue INR 150562.00 / row {index}" for index in range(130)])
    reader=PdfReader(io.BytesIO(data))
    assert len(reader.pages)==3
    text="\n".join(page.extract_text() for page in reader.pages)
    assert "Nexa (demo) \\ source" in text and "row 129" in text and "Page 3 of 3" in text
    assert pdf_bytes(["same"])==pdf_bytes(["same"])


def test_csv_retains_unicode_and_defuses_formulas_without_changing_negative_numbers():
    data=csv_bytes([["नैक्सा","=HYPERLINK(\"bad\")","-12.50","+1+cmd","@sum(x)"]]).decode("utf-8-sig")
    assert "नैक्सा" in data and "'=HYPERLINK" in data and "'-12.50" not in data and "'+1+cmd" in data
    text=PdfReader(io.BytesIO(pdf_bytes(["नैक्सा"])) ).pages[0].extract_text()
    assert "\\u0928" in text


@pytest.mark.parametrize("changes",[{}, {"snapshot_id":str(uuid4()),"model_run_id":str(uuid4())},{"snapshot_id":str(uuid4()),"business_id":str(uuid4())},{"snapshot_id":str(uuid4()),"lead_days":14},{"kind":"scenario_comparison","scenario_run_ids":[str(uuid4())]},{"kind":"sales_forecast","model_run_id":str(uuid4()),"horizon":31}])
def test_report_rejects_missing_mixed_or_out_of_range_sources(changes):
    with pytest.raises(ValidationError):ReportInput.model_validate({"name":"Test report","kind":"revenue_expenses"}|changes)
