"""Parser tests for apply_removals.py. Fake data only; run with: python3 -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import apply_removals as ar

NOTICE = """This message is from Texas DPS Public SOR.
The below records have been removed.
Record(s):
    DOE,JANE Q   1980-01-02   00123456
    ROE,XX   1970-05-06   4567890
    SMITH,JOHN III   1990-12-31   50330284
    DOE,JANE Q   1980-01-02   00123456

If you have any questions regarding this notice, please contact TxSOR@dps.texas.gov.
"""


class ParseNoticeTest(unittest.TestCase):
    def test_plain_text(self):
        recs = ar.parse_notice(NOTICE)
        self.assertEqual([r[2] for r in recs], ["00123456", "04567890", "50330284"])
        self.assertEqual(recs[2][0], "SMITH,JOHN III")

    def test_html(self):
        html_body = "<p>Record(s):<br>DOE,JANE&nbsp;Q 1980-01-02 00123456<br>ROE,XX 1970-05-06 04567890</p>"
        self.assertEqual([r[2] for r in ar.parse_notice(html_body)], ["00123456", "04567890"])

    def test_ignores_text_before_marker(self):
        text = "Ref 2026-01-01 12345678\nRecord(s):\n  DOE,A 1980-01-02 00123456\n"
        self.assertEqual([r[2] for r in ar.parse_notice(text)], ["00123456"])

    def test_empty(self):
        self.assertEqual(ar.parse_notice("nothing here"), [])

    def test_hash_is_order_independent(self):
        a = ar.parse_notice(NOTICE)
        self.assertEqual(ar.notice_hash(a), ar.notice_hash(list(reversed(a))))


class ReadNoticeTest(unittest.TestCase):
    HEADERS = "From: TxSOR <noreply@dps.texas.gov>\r\nSubject: Removal\r\nMIME-Version: 1.0\r\n"
    DPS = ["00123456", "04567890", "50330284"]

    def dps(self, data):
        return [r[2] for r in ar.parse_notice(ar.read_notice(data))]

    def test_plain_file_unchanged(self):
        self.assertEqual(self.dps(NOTICE.encode()), self.DPS)

    def test_eml_plain_quoted_printable(self):
        eml = self.HEADERS + "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n" + NOTICE.replace("\n", "\r\n")
        self.assertEqual(self.dps(eml.encode()), self.DPS)

    def test_eml_html_base64(self):
        import base64
        body = base64.b64encode(("<p>Record(s):<br>" + "<br>".join(
            ["DOE,JANE Q 1980-01-02 00123456", "ROE,XX 1970-05-06 04567890", "SMITH,JOHN III 1990-12-31 50330284"]) + "</p>").encode()).decode()
        eml = self.HEADERS + "Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n" + body
        self.assertEqual(self.dps(eml.encode()), self.DPS)

    def test_eml_multipart(self):
        eml = (self.HEADERS + 'Content-Type: multipart/alternative; boundary="b"\r\n\r\n'
               '--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n' + NOTICE.replace("\n", "\r\n") +
               '--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>unrelated</p>\r\n--b--\r\n')
        self.assertEqual(self.dps(eml.encode()), self.DPS)


if __name__ == "__main__":
    unittest.main()
