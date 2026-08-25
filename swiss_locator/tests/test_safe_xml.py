"""
Unit tests for the hardened XML parsing helpers.

Capabilities documents are fetched from remote servers, so parsing must reject
entity expansion attacks instead of expanding them.  These tests do NOT require
network access nor QGIS.
"""

import os
import tempfile
import unittest

from swiss_locator.utils import safe_xml

WMS_CAPABILITIES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<WMS_Capabilities xmlns="http://www.opengis.net/wms" version="1.3.0">'
    "<Layer><Name>ch.test.layer</Name><Title>Test &amp; Layer</Title></Layer>"
    "</WMS_Capabilities>"
)
WMS_NS = "{http://www.opengis.net/wms}"

BILLION_LAUGHS = (
    '<?xml version="1.0"?>'
    '<!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
    "<lolz>&lol1;</lolz>"
)
XXE = '<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><r>&xxe;</r>'
EXTERNAL_DTD = '<!DOCTYPE r SYSTEM "http://example.invalid/evil.dtd"><r/>'


class TestFromString(unittest.TestCase):
    def test_parses_str(self):
        root = safe_xml.fromstring(WMS_CAPABILITIES)
        self.assertEqual(root.tag, f"{WMS_NS}WMS_Capabilities")
        self.assertEqual(root.get("version"), "1.3.0")

    def test_parses_bytes(self):
        root = safe_xml.fromstring(WMS_CAPABILITIES.encode("utf-8"))
        self.assertEqual(root.tag, f"{WMS_NS}WMS_Capabilities")

    def test_keeps_namespaces_and_predefined_entities(self):
        root = safe_xml.fromstring(WMS_CAPABILITIES)
        self.assertEqual(root.find(f".//{WMS_NS}Name").text, "ch.test.layer")
        self.assertEqual(root.find(f".//{WMS_NS}Title").text, "Test & Layer")

    def test_malformed_raises_parse_error(self):
        with self.assertRaises(safe_xml.ParseError):
            safe_xml.fromstring("<unclosed>")


class TestForbiddenConstructs(unittest.TestCase):
    def assert_rejected(self, document):
        with self.assertRaises(safe_xml.ForbiddenXmlError):
            safe_xml.fromstring(document)

    def test_rejects_billion_laughs(self):
        self.assert_rejected(BILLION_LAUGHS)

    def test_rejects_external_entity(self):
        self.assert_rejected(XXE)

    def test_rejects_external_dtd(self):
        self.assert_rejected(EXTERNAL_DTD)

    def test_rejects_plain_doctype(self):
        self.assert_rejected("<!DOCTYPE html><html/>")

    def test_forbidden_error_is_a_parse_error(self):
        """Callers only catching ParseError still handle hostile documents."""
        self.assertTrue(issubclass(safe_xml.ForbiddenXmlError, safe_xml.ParseError))
        with self.assertRaises(safe_xml.ParseError):
            safe_xml.fromstring(BILLION_LAUGHS)


class TestParseFile(unittest.TestCase):
    def write_temp(self, content):
        handle, path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.unlink, path)
        return path

    def test_parses_path(self):
        root = safe_xml.parse_file(self.write_temp(WMS_CAPABILITIES))
        self.assertEqual(root.tag, f"{WMS_NS}WMS_Capabilities")

    def test_parses_file_object(self):
        with open(self.write_temp(WMS_CAPABILITIES), "rb") as f:
            self.assertEqual(safe_xml.parse_file(f).tag, f"{WMS_NS}WMS_Capabilities")

    def test_rejects_billion_laughs(self):
        path = self.write_temp(BILLION_LAUGHS)
        with self.assertRaises(safe_xml.ForbiddenXmlError):
            safe_xml.parse_file(path)


if __name__ == "__main__":
    unittest.main()
