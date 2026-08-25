"""
/***************************************************************************

 QGIS Swiss Locator Plugin
 Copyright (C) 2025 Denis Rouzaud

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import xml.etree.ElementTree as ET

# Capabilities and metadata documents are fetched from remote servers -- among
# them arbitrary third party WMS servers advertised by opendata.swiss -- so
# they have to be treated as untrusted input.
#
# xml.etree.ElementTree neither resolves external entities nor retrieves
# external DTDs (it reports an undefined entity instead), so it is not exposed
# to XXE. It does expand *internal* entities though, which leaves it open to
# entity expansion denial of service ("billion laughs", quadratic blowup).
# Internal entities can only be declared in a DOCTYPE, so refusing documents
# that carry one closes that hole.
#
# defusedxml would be the obvious alternative, but it is not part of a standard
# QGIS installation, and the hardening it would add on top of the above is a
# DOCTYPE ban -- which is exactly what the TreeBuilder below implements.

ParseError = ET.ParseError


class ForbiddenXmlError(ET.ParseError):
    """An XML document used a construct we refuse to process.

    Subclasses ``xml.etree.ElementTree.ParseError`` so that callers already
    handling malformed XML also handle hostile XML.
    """

    def __init__(self, message):
        super().__init__(message)
        self.position = (0, 0)


class _NoDoctypeTreeBuilder(ET.TreeBuilder):
    """TreeBuilder aborting on any DOCTYPE declaration.

    Both the C and the pure Python parser call ``doctype()`` on their target
    before the document element is built, so raising here stops parsing before
    any entity gets expanded.
    """

    def doctype(self, name, pubid, system):
        raise ForbiddenXmlError(f"DOCTYPE declarations are not allowed: {name}")


def _parser() -> ET.XMLParser:
    return ET.XMLParser(target=_NoDoctypeTreeBuilder())


def fromstring(text) -> ET.Element:
    """Parse an XML document from a string or bytes, return its root element."""
    parser = _parser()
    parser.feed(text)
    return parser.close()


def parse_file(source) -> ET.Element:
    """Parse an XML document from a file path or file object, return its root element."""
    return ET.parse(source, parser=_parser()).getroot()
