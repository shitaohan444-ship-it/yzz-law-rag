import io
import unittest
import zipfile

from app.ingest.parser import _sanitize_docx

_CONTENT_TYPES = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
    "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
    "<Default Extension='xml' ContentType='application/xml'/>"
    "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
    "</Types>"
)
_ROOT_RELS = (
    "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
    "<Relationship Id='r1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>"
    "</Relationships>"
)
_DOCUMENT = (
    "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
    "<w:body><w:p><w:r><w:t>hello world</w:t></w:r></w:p></w:body></w:document>"
)


def _build_docx(document_rels: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", _DOCUMENT)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
    return buffer.getvalue()


def _rels_with(*relationships: str) -> str:
    return (
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        + "".join(relationships)
        + "</Relationships>"
    )


class SanitizeDocxTests(unittest.TestCase):
    def test_drops_relationship_pointing_to_missing_part_double_quotes(self) -> None:
        # 真实 docx（Word/WPS）属性用双引号
        broken = _build_docx(
            _rels_with(
                '<Relationship Id="r9" Type="http://schemas.microsoft.com/office/2007/relationships/userCustomization" Target="userCustomization/customUI.xml"/>'
            )
        )
        from docx import Document

        with self.assertRaises(Exception):
            Document(io.BytesIO(broken))

        fixed = _sanitize_docx(broken)
        document = Document(io.BytesIO(fixed))
        self.assertIn("hello world", "".join(p.text for p in document.paragraphs))
        rels = zipfile.ZipFile(io.BytesIO(fixed)).read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertNotIn("userCustomization", rels)

    def test_drops_relationship_pointing_to_missing_part_single_quotes(self) -> None:
        broken = _build_docx(
            _rels_with(
                "<Relationship Id='r9' Type='http://schemas.microsoft.com/office/2007/relationships/userCustomization' Target='userCustomization/customUI.xml'/>"
            )
        )
        from docx import Document

        with self.assertRaises(Exception):
            Document(io.BytesIO(broken))

        fixed = _sanitize_docx(broken)
        document = Document(io.BytesIO(fixed))
        self.assertIn("hello world", "".join(p.text for p in document.paragraphs))
        rels = zipfile.ZipFile(io.BytesIO(fixed)).read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertNotIn("userCustomization", rels)

    def test_keeps_external_relationship_even_if_target_absent(self) -> None:
        external = (
            '<Relationship Id="r5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            'Target="https://example.com/x" TargetMode="External"/>'
        )
        source = _build_docx(_rels_with(external))
        fixed = _sanitize_docx(source)
        rels = zipfile.ZipFile(io.BytesIO(fixed)).read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertIn("example.com", rels)

    def test_keeps_relationship_to_existing_part(self) -> None:
        healthy = _build_docx(_rels_with())  # 无悬空引用
        self.assertEqual(_sanitize_docx(healthy), healthy)  # 原样返回

    def test_non_zip_input_returned_unchanged(self) -> None:
        payload = b"not a zip at all"
        self.assertEqual(_sanitize_docx(payload), payload)


if __name__ == "__main__":
    unittest.main()
