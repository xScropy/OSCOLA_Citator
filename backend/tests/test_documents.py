"""Document check: footnote extraction, citation recognition, corrections, shortening and the page index."""
import io
import json
import zipfile

import pytest

from app.documents.analyze import analyze
from app.documents.extract import DocumentError, Extracted, Footnote, extract
from app.documents.parse import parse_segment, split_segments

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# (page the footnote is cited on, [(text, italic)])
NOTES = [
    (1, [("Donoghue v. Stevenson", True), (" [1932] AC 562 (HL) 580 (Lord Atkin).", False)]),
    (1, [("ibid 581", False)]),
    (2, [("Timothy Endicott, ", False), ("Administrative Law", True), (" (4th edn, OUP 2018) 45; Vienna Convention on the Law of Treaties (adopted 23 May 1969, entered into force 27 January 1980) 1155 UNTS 331 (VCLT) art 31.", False)]),
    (2, [("Donoghue", True), (" (n 2) 599; Endicott (n 3) 50.", False)]),
    (3, [("As Lord Bridge explained in ", False), ("Caparo Industries plc v Dickman", True), (" [1990] 2 AC 605 (HL) 618, the test has three stages; see also Human Rights Act 1998, s 6.", False)]),
    (4, [("Donoghue v Stevenson", True), (" [1932] AC 562 (HL) 583.", False)]),
    (4, [("See ", False), ("Donoghue v Stevenson", True), (" [1932] AC 562 (HL) 584; VCLT art 32.", False)]),
    (6, [("Paul Craig, ‘Theory, “Pure Theory” and Values in Public Law’ [2005] PL 440, 442.", False)]),
]


def make_docx(rendered_breaks: bool = True) -> bytes:
    def run(text, italic=False):
        props = "<w:rPr><w:i/></w:rPr>" if italic else ""
        return f'<w:r>{props}<w:t xml:space="preserve">{text}</w:t></w:r>'

    body, page = [], 1
    for index, (note_page, _) in enumerate(NOTES, start=1):
        breaks = ""
        while page < note_page:
            breaks += "<w:r><w:lastRenderedPageBreak/></w:r>" if rendered_breaks else ""
            page += 1
        body.append(f'<w:p>{breaks}{run(f"Paragraph {index} of the argument.")}<w:r><w:footnoteReference w:id="{index + 1}"/></w:r></w:p>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}<w:sectPr/></w:body></w:document>'
    notes = ['<w:footnote w:type="separator" w:id="0"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>', '<w:footnote w:type="continuationSeparator" w:id="1"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>']
    for index, (_, runs) in enumerate(NOTES, start=1):
        text = "".join(run(t, i) for t, i in runs)
        notes.append(f'<w:footnote w:id="{index + 1}"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r>{run(" ")}{text}</w:p></w:footnote>')
    footnotes = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes xmlns:w="{W_NS}">{"".join(notes)}</w:footnotes>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
        z.writestr("word/footnotes.xml", footnotes)
    return buffer.getvalue()


def make_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for page in range(1, 7):
        pdf.setFont("Times-Roman", 12)
        for line in range(12):
            pdf.drawString(72, 770 - line * 18, f"Body text of page {page}, line {line + 1}, set in the main text size of the memorial.")
        y = 150
        for number, (note_page, runs) in enumerate(NOTES, start=1):
            if note_page != page:
                continue
            x = 72
            pdf.setFont("Times-Roman", 8)
            pdf.drawString(x, y, f"{number} ")
            x += pdf.stringWidth(f"{number} ", "Times-Roman", 8)
            for text, italic in runs:
                font = "Times-Italic" if italic else "Times-Roman"
                words = text.split(" ")
                for i, word in enumerate(words):
                    piece = word + (" " if i < len(words) - 1 else "")
                    width = pdf.stringWidth(piece, font, 8)
                    if x + width > 520:  # wrap long footnotes
                        x, y = 72, y - 10
                    pdf.setFont(font, 8)
                    pdf.drawString(x, y, piece)
                    x += width
            y -= 12
        pdf.setFont("Times-Roman", 12)
        pdf.drawCentredString(297, 40, str(page))
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def revised(result):
    return {n["number"]: n["revised"]["text"] for n in result["footnotes"]}


def authority(result, title):
    return next(a for a in result["authorities"] if title in a["metadata"]["title"])


def test_parser_reads_common_oscola_citations():
    case = parse_segment("See also Corr v IBC Vehicles Ltd [2008] UKHL 13, [2008] 1 AC 884 [11]–[15]")
    assert case["form"] == "full" and case["signal"] == "See also "
    assert case["metadata"] == {"type": "case", "title": "Corr v IBC Vehicles Ltd", "neutral_citation": "[2008] UKHL 13", "report_citation": "[2008] 1 AC 884", "year": "2008"}
    assert case["pinpoint"] == {"kind": "para", "value": "11–15"}
    article = parse_segment("Joseph Raz, ‘The Rule of Law and Its Virtue’ (1977) 93 LQR 195, 198")
    assert article["metadata"]["journal"] == "LQR" and article["metadata"]["volume"] == "93" and article["pinpoint"]["value"] == "198"
    assert parse_segment("Human Rights Act 1998, s 6(1)")["metadata"]["type"] == "legislation"
    assert parse_segment("Endicott (n 4) 50") == {"signal": "", "body": "Endicott (n 4) 50", "form": "short", "lead": "Endicott", "note": 4, "pinpoint": {"kind": "page", "value": "50"}, "suffix": ""}
    assert parse_segment("Ibid.")["form"] == "ibid"
    # prose is never mistaken for a citation
    assert parse_segment("This point is controversial and has been doubted by several writers")["form"] == "unknown"
    assert parse_segment("In Donoghue v Stevenson [1932] AC 562 the House held otherwise")["form"] == "unknown"
    text = "See Donoghue v Stevenson [1932] AC 562 (HL); Caparo Industries plc v Dickman [1990] 2 AC 605 (HL) 618. See also Endicott (n 4) 50."
    assert [text[a:b] for a, b in split_segments(text)] == ["See Donoghue v Stevenson [1932] AC 562 (HL)", "Caparo Industries plc v Dickman [1990] 2 AC 605 (HL) 618", "See also Endicott (n 4) 50"]


@pytest.mark.parametrize("builder,kind", [(make_docx, "docx"), (make_pdf, "pdf")])
def test_extraction_finds_every_footnote_with_its_page(builder, kind):
    extracted = extract(builder(), f"memorial.{kind}")
    assert extracted.kind == kind and extracted.pages_available
    assert [n.number for n in extracted.footnotes] == list(range(1, 9))
    assert [n.page for n in extracted.footnotes] == [str(p) for p, _ in NOTES]
    for note, (_, runs) in zip(extracted.footnotes, NOTES):
        assert note.text == "".join(t for t, _ in runs)
    first = extracted.footnotes[0]
    assert "".join(ch for ch, flag in zip(first.text, first.italic) if flag) == "Donoghue v. Stevenson"


@pytest.mark.parametrize("builder", [make_docx, make_pdf])
def test_authorities_corrections_and_page_index(builder):
    result = analyze(extract(builder(), "memorial"), "oscola")
    assert result["stats"]["authorities"] == 6 and result["stats"]["unrecognised"] == 0
    donoghue = authority(result, "Donoghue")
    # full citation, ibid, short form, bare repeat: every page is indexed
    assert donoghue["locations"] == "1–2, 4"
    assert [o["form"] for o in donoghue["occurrences"]] == ["full", "ibid", "short", "full", "full"]
    assert [o["pinpoint"]["value"] for o in donoghue["occurrences"]] == ["580", "581", "599", "583", "584"]
    assert authority(result, "Caparo")["occurrences"][0]["form"] == "mention"  # cited inside a sentence
    assert authority(result, "Vienna")["locations"] == "2, 4"

    text = revised(result)
    assert text[1] == "Donoghue v Stevenson [1932] AC 562 (HL) 580 (Lord Atkin)."  # 'v.' corrected, judge kept
    assert text[2] == "ibid 581."  # closing full stop added
    assert text[4] == "Donoghue (n 1) 599; Endicott (n 3) 50."  # wrong cross-reference corrected
    assert text[5] == "".join(t for t, _ in NOTES[4][1])  # prose left exactly as written
    assert text[7] == "See Donoghue v Stevenson [1932] AC 562 (HL) 584; VCLT (n 3) art 32."
    change = result["footnotes"][3]["citations"][0]["change"]
    assert change["types"] == ["cross-reference"] and change["suggested"]["html"] == "<i>Donoghue</i> (n 1) 599"

    table = {s["heading"]: [(e["text"], e["pages"]) for e in s["entries"]] for s in result["table"]["sections"]}
    assert list(table) == ["Treaties and International Instruments", "Cases and Judicial Decisions", "Legislation", "Books and Academic Publications"]
    assert table["Cases and Judicial Decisions"] == [("Caparo Industries plc v Dickman [1990] 2 AC 605 (HL)", "3"), ("Donoghue v Stevenson [1932] AC 562 (HL)", "1–2, 4")]
    assert ("Craig P, ‘Theory, “Pure Theory” and Values in Public Law’ [2005] PL 440", "6") in table["Books and Academic Publications"]


def test_shorten_all_but_the_first_citation():
    extracted = extract(make_docx(), "memorial.docx")
    text = revised(analyze(extracted, "oscola", {"shorten": True}))
    assert text[1].startswith("Donoghue v Stevenson [1932] AC 562 (HL) 580")  # first citation stays in full
    assert text[2] == "ibid 581."
    assert text[6] == "Donoghue (n 1) 583."
    assert text[7] == "See ibid 584; VCLT (n 3) art 32."
    without_ibid = revised(analyze(extracted, "oscola", {"shorten": True, "use_ibid": False}))
    assert without_ibid[2] == "Donoghue (n 1) 581." and without_ibid[7].startswith("See Donoghue (n 1) 584")


def test_user_can_reject_or_rewrite_a_correction():
    extracted = extract(make_docx(), "memorial.docx")
    result = analyze(extracted, "oscola", {"skip": ["1:0", "2:end"], "overrides": {"4:0": "Donoghue (n 1) 599–600"}})
    text = revised(result)
    assert text[1] == "Donoghue v. Stevenson [1932] AC 562 (HL) 580 (Lord Atkin)." and text[2] == "ibid 581"
    assert text[4].startswith("Donoghue (n 1) 599–600;")
    assert result["footnotes"][0]["citations"][0]["change"]["accepted"] is False


def test_unknown_page_numbers_fall_back_to_footnotes():
    extracted = extract(make_docx(rendered_breaks=False), "memorial.docx")
    assert not extracted.pages_available and any("page breaks" in w for w in extracted.warnings)
    result = analyze(extracted, "oscola")
    assert result["table"]["location_heading"] == "Footnote" and authority(result, "Donoghue")["locations"] == "1–2, 4, 6–7"


def test_invalid_uploads_are_rejected():
    for data, name in [(b"hello", "notes.txt"), (b"\xd0\xcf\x11\xe0old word", "old.doc"), (b"PK\x03\x04not a zip", "fake.docx")]:
        with pytest.raises(DocumentError):
            extract(data, name)


def test_api_analyse_export_and_add_to_library(auth):
    docx = make_docx()
    upload = lambda: {"file": ("memorial.docx", docx, "application/octet-stream")}  # noqa: E731
    assert auth.post("/api/documents/analyze", files={"file": ("x.txt", b"plain text", "text/plain")}).status_code == 422
    result = auth.post("/api/documents/analyze", files=upload(), data={"style": "oscola"}).json()
    assert result["document"] == {"kind": "docx", "footnotes": 8, "pages": None, "pages_available": True, "location_unit": "page", "name": "memorial.docx"}
    assert "revised_runs" not in result["footnotes"][0]

    # a source already in the library is recognised
    donoghue = authority(result, "Donoghue")
    saved = auth.post("/api/references", json={"metadata": donoghue["metadata"], "retrieved": donoghue["metadata"], "source": {"name": "Extracted from memorial.docx", "reliable": False}}).json()
    assert saved["verification"]["status"] == "partially_verified"
    again = auth.post("/api/documents/analyze", files=upload()).json()
    assert authority(again, "Donoghue")["library_id"] == saved["id"] and again["stats"]["in_library"] == 1

    options = json.dumps({"shorten": True})
    corrected = auth.post("/api/documents/export", files=upload(), data={"output": "corrected", "options": options})
    assert corrected.status_code == 200 and "memorial-corrected.docx" in corrected.headers["content-disposition"]
    reread = extract(corrected.content, "memorial-corrected.docx")
    assert [n.text for n in reread.footnotes][:2] == ["Donoghue v Stevenson [1932] AC 562 (HL) 580 (Lord Atkin).", "ibid 581."]
    assert reread.footnotes[5].text == "Donoghue (n 1) 583."
    assert reread.footnotes[4].text == "".join(t for t, _ in NOTES[4][1])
    first = reread.footnotes[0]
    assert "".join(ch for ch, flag in zip(first.text, first.italic) if flag) == "Donoghue v Stevenson"
    from docx import Document
    Document(io.BytesIO(corrected.content))  # still a valid Word file
    with zipfile.ZipFile(io.BytesIO(corrected.content)) as z:
        xml = z.read("word/footnotes.xml").decode()
        assert xml.count("<w:footnoteRef/>") == 8 and 'w:type="separator"' in xml
    # analysing the corrected file finds nothing left to fix
    assert analyze(reread, "oscola", {"shorten": True})["stats"]["footnotes_changed"] == 0

    table = auth.post("/api/documents/export", files=upload(), data={"output": "table", "format": "txt"})
    assert "Table of Authorities" in table.text and "Donoghue v Stevenson [1932] AC 562 (HL) " in table.text and " 1–2, 4" in table.text
    for fmt in ("docx", "pdf"):
        assert len(auth.post("/api/documents/export", files=upload(), data={"output": "table", "format": fmt}).content) > 1000
    notes = auth.post("/api/documents/export", files=upload(), data={"output": "footnotes", "format": "txt"})
    assert "4. Donoghue (n 1) 599; Endicott (n 3) 50." in notes.text
    pdf_upload = {"file": ("memorial.pdf", make_pdf(), "application/pdf")}
    assert auth.post("/api/documents/export", files=pdf_upload, data={"output": "corrected"}).status_code == 422
