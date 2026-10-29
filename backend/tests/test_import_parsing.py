import io
import pytest
from openpyxl import Workbook
from app.data.imports import parse_file
from app.data.router import csv_text


def workbook_bytes(rows):
    book=Workbook()
    for row in rows:
        book.active.append(row)
    output=io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_csv_json_and_xlsx_preserve_mapped_values():
    columns,rows=parse_file("data.csv",b'Code,Name\nC1,"A, B"\n')
    assert columns==["Code","Name"] and rows==[{"Code":"C1","Name":"A, B"}]
    assert parse_file("data.json",b'[{"amount":0.1234,"is_demo":true}]')[1][0]["amount"]=="0.1234"
    assert parse_file("data.xlsx",workbook_bytes([["Code","Amount"],["C1",12.5]]))[1][0]["Amount"]=="12.5"


@pytest.mark.parametrize("filename,data",[("a.csv",b"Name,Name\nx,y"),("a.csv",b"Name\nx,y"),("a.json",b'{"name":"x"}'),("a.json",b'[{"nested":{}}]'),("a.json",b'[{"value":NaN}]'),("a.xls",b"x"),("a.csv",b"Name\n\xff"),("a.csv",b"")])
def test_reject_malformed_and_unsupported_imports(filename,data):
    with pytest.raises(ValueError):
        parse_file(filename,data)


def test_formulas_and_excess_rows_are_rejected():
    with pytest.raises(ValueError,match="formulas"):
        parse_file("data.xlsx",workbook_bytes([["name"],["=2+2"]]))
    with pytest.raises(ValueError,match="1000"):
        parse_file("data.csv",("name\n"+"x\n"*1001).encode())
    with pytest.raises(ValueError,match="2 MiB"):
        parse_file("data.csv",b"x"*(2*1024*1024+1))


def test_exports_neutralize_spreadsheet_commands_without_corrupting_numbers():
    text=csv_text([{"name":"=2+2","quantity":"-1.000","other":"+cmd"}])
    assert "'=2+2" in text and "'+cmd" in text and "-1.000" in text
