"""XML loading, paragraph iteration, and in-place replacement of `<p>`
inner content with a prebuilt XML fragment string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from lxml import etree


def load(path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(strip_cdata=False, remove_blank_text=False)
    return etree.parse(str(path), parser)


def iter_text_paragraphs(
    tree: etree._ElementTree,
) -> Iterator[tuple[etree._Element, str]]:
    """Yield (p_element, inner_text) for every `<p>` (in document order, any
    namespace) that contains only text. Paragraphs with child elements are
    skipped — see README limitations.
    """
    for el in tree.iter():
        tag = etree.QName(el).localname
        if tag != "p":
            continue
        if len(el) > 0:
            continue  # has child elements; skip
        text = el.text or ""
        if not text.strip():
            continue
        yield el, text


def replace_inner_with_fragment(p_element: etree._Element, fragment: str) -> None:
    """Replace the text content of `p_element` with the parsed children of
    the given XML fragment string. Tail and attributes of `p_element` are
    preserved.
    """
    wrapped = f"<wrapper>{fragment}</wrapper>"
    wrapper = etree.fromstring(wrapped)
    p_element.text = wrapper.text
    # Remove any pre-existing children (defensive; for text-only <p> this is a no-op).
    for child in list(p_element):
        p_element.remove(child)
    for child in wrapper:
        p_element.append(child)


def save(tree: etree._ElementTree, path: Path) -> None:
    xml_bytes = etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", pretty_print=False
    )
    path.write_bytes(xml_bytes)
