import unittest

from docx import Document

from src.models import DocumentContext
from src.renderer import Renderer


class RendererPublicationTimeTests(unittest.TestCase):
    def test_missing_publication_time_is_rendered_as_time_unknown(self):
        sample = {
            "reference_id": "S1",
            "title": "发布时间缺失的公开网页",
            "pub_time": "",
            "time_basis": "unknown",
        }
        context = DocumentContext(
            template_id="event_report",
            title="测试报告",
            metadata={"key_samples": [sample]},
        )
        document = Document()

        Renderer()._append_key_samples(document, context)

        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("发布时间：时间未知", text)
        self.assertEqual(sample["pub_time"], "")


if __name__ == "__main__":
    unittest.main()
