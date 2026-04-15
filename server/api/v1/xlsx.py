"""
Minimal .xlsx builder using only stdlib (zipfile + xml).
No openpyxl or xlsxwriter required.
"""
import io
import zipfile


def build_xlsx(headers: list[str], rows: list[list]) -> bytes:
    def _esc(v) -> str:
        if v is None:
            return ""
        return (
            str(v)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    ss: list[str] = []
    ss_idx: dict[str, int] = {}

    def _si(val: str) -> int:
        if val not in ss_idx:
            ss_idx[val] = len(ss)
            ss.append(val)
        return ss_idx[val]

    sheet_rows = []
    hcells = "".join(
        f'<c r="{chr(65 + i)}1" t="s" s="1"><v>{_si(h)}</v></c>'
        for i, h in enumerate(headers)
    )
    sheet_rows.append(f'<row r="1">{hcells}</row>')

    for ri, row in enumerate(rows, start=2):
        cells = []
        for ci, val in enumerate(row):
            col = chr(65 + ci)
            ref = f"{col}{ri}"
            if val is None or val == "":
                cells.append(f'<c r="{ref}"/>')
            else:
                idx = _si(str(val))
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        sheet_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')

    sheet_data = "\n".join(sheet_rows)
    ss_items = "".join(
        f'<si><t xml:space="preserve">{_esc(s)}</t></si>' for s in ss
    )

    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            '<sheet name="Conversaciones" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{sheet_data}</sheetData>"
            "</worksheet>"
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            f' count="{len(ss)}" uniqueCount="{len(ss)}">'
            f"{ss_items}</sst>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<fonts><font/><font><b/></font></fonts>"
            "<fills><fill/><fill/></fills>"
            "<borders><border/></borders>"
            "<cellStyleXfs><xf/></cellStyleXfs>"
            "<cellXfs>"
            '<xf fontId="0"/>'
            '<xf fontId="1"/>'
            "</cellXfs>"
            "</styleSheet>"
        ),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))
    return buf.getvalue()
