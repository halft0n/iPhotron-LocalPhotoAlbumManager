#!/usr/bin/env python3
"""Extract Qt translation calls from Python sources into Qt Linguist TS files."""

from __future__ import annotations

import argparse
import ast
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCES = (
    Path("src/iPhoto/gui"),
    Path("src/maps"),
)


@dataclass(frozen=True)
class MessageKey:
    context: str
    source: str
    comment: str | None = None
    numerus: bool = False


@dataclass(frozen=True)
class FixedContextHelper:
    context: str
    source_parameter: str
    comment: str | None = None


class TranslationCallVisitor(ast.NodeVisitor):
    """Collect literal Qt translation calls from a Python module."""

    def __init__(self) -> None:
        self.messages: list[MessageKey] = []
        self._translate_aliases: set[str] = {"tr"}
        self._helper_contexts: list[dict[str, FixedContextHelper]] = [{}]

    def visit_Module(self, node: ast.Module) -> None:
        self._helper_contexts.append(_fixed_context_helpers(node.body))
        self.generic_visit(node)
        self._helper_contexts.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._helper_contexts.append(_fixed_context_helpers(node.body))
        self.generic_visit(node)
        self._helper_contexts.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_qcore_translate_attr(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._translate_aliases.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and _is_qcore_translate_attr(node.value):
            if isinstance(node.target, ast.Name):
                self._translate_aliases.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_translation_call(node):
            message = _message_from_call(node)
            if message is not None:
                self.messages.append(message)
        else:
            message = self._message_from_fixed_context_helper_call(node)
            if message is not None:
                self.messages.append(message)
        self.generic_visit(node)

    def _is_translation_call(self, node: ast.Call) -> bool:
        if _is_qcore_translate_attr(node.func):
            return True
        return isinstance(node.func, ast.Name) and node.func.id in self._translate_aliases

    def _message_from_fixed_context_helper_call(self, node: ast.Call) -> MessageKey | None:
        helper = self._fixed_context_helper(node.func)
        if helper is None:
            return None

        source = _literal_string(_arg(node, 0, helper.source_parameter))
        if source is None:
            return None

        return MessageKey(
            context=helper.context,
            source=source,
            comment=helper.comment,
            numerus=_has_plural_argument(node),
        )

    def _fixed_context_helper(self, node: ast.AST) -> FixedContextHelper | None:
        name: str | None = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        if name is None:
            return None

        for helpers in reversed(self._helper_contexts):
            helper = helpers.get(name)
            if helper is not None:
                return helper
        return None


def _is_qcore_translate_attr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "translate"
        and isinstance(node.value, ast.Name)
        and node.value.id == "QCoreApplication"
    )


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_int(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return -node.operand.value
    return None


def _function_parameters(node: ast.FunctionDef) -> list[str]:
    return [arg.arg for arg in node.args.posonlyargs + node.args.args]


def _fixed_context_helpers(nodes: list[ast.stmt]) -> dict[str, FixedContextHelper]:
    helpers: dict[str, FixedContextHelper] = {}
    for node in nodes:
        if not isinstance(node, ast.FunctionDef):
            continue
        helper = _fixed_context_helper_from_function(node)
        if helper is not None:
            helpers[node.name] = helper
    return helpers


def _fixed_context_helper_from_function(node: ast.FunctionDef) -> FixedContextHelper | None:
    parameters = _function_parameters(node)
    source_parameters = [name for name in parameters if name != "self"]
    if not source_parameters:
        return None

    source_parameter = source_parameters[0]
    for statement in node.body:
        if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
            continue
        context = _literal_string(_arg(statement.value, 0, "context"))
        source = _arg(statement.value, 1, "source_text")
        if (
            context is None
            or not isinstance(source, ast.Name)
            or source.id != source_parameter
        ):
            continue
        if not _is_qcore_translate_attr(statement.value.func):
            continue
        return FixedContextHelper(
            context=context,
            source_parameter=source_parameter,
            comment=_literal_string(_arg(statement.value, 2, "disambiguation")),
        )
    return None


def _keyword_value(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _arg(node: ast.Call, index: int, keyword: str) -> ast.AST | None:
    if len(node.args) > index:
        return node.args[index]
    return _keyword_value(node, keyword)


def _has_plural_argument(node: ast.Call) -> bool:
    n_arg = _arg(node, 3, "n")
    if n_arg is None:
        return False
    n_value = _literal_int(n_arg)
    return n_value is None or n_value >= 0


def _message_from_call(node: ast.Call) -> MessageKey | None:
    context = _literal_string(_arg(node, 0, "context"))
    source = _literal_string(_arg(node, 1, "source_text"))
    if context is None or source is None:
        return None

    comment_node = _arg(node, 2, "disambiguation")
    comment = _literal_string(comment_node)

    return MessageKey(
        context=context,
        source=source,
        comment=comment,
        numerus=_has_plural_argument(node),
    )


def extract_messages(sources: list[Path]) -> list[MessageKey]:
    messages: OrderedDict[MessageKey, None] = OrderedDict()
    for source in _iter_python_files(sources):
        visitor = TranslationCallVisitor()
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except SyntaxError as exc:
            raise RuntimeError(f"Unable to parse {source}: {exc}") from exc
        visitor.visit(tree)
        for message in visitor.messages:
            messages.setdefault(message, None)
    return list(messages)


def _iter_python_files(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        if not source.exists():
            continue
        if source.is_file() and source.suffix == ".py":
            files.append(source)
            continue
        if source.is_dir():
            files.extend(path for path in source.rglob("*.py") if path.is_file())
    return sorted(files)


def update_ts(path: Path, messages: list[MessageKey], *, language: str | None = None) -> None:
    if path.exists():
        tree = ET.parse(path)  # noqa: S314 - TS files are local project resources.
        root = tree.getroot()
    else:
        root = ET.Element("TS", {"version": "2.1"})
        tree = ET.ElementTree(root)

    root.set("version", root.get("version") or "2.1")
    if language and not root.get("language"):
        root.set("language", language)

    contexts = _context_map(root)
    for message in messages:
        context = contexts.get(message.context)
        if context is None:
            context = ET.SubElement(root, "context")
            ET.SubElement(context, "name").text = message.context
            contexts[message.context] = context
        _ensure_message(context, message)

    _indent(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    _normalise_ts_header(path)


def _context_map(root: ET.Element) -> dict[str, ET.Element]:
    contexts: dict[str, ET.Element] = {}
    for context in root.findall("context"):
        name = context.findtext("name")
        if name:
            contexts[name] = context
    return contexts


def _ensure_message(context: ET.Element, message: MessageKey) -> None:
    existing = _find_message(context, message)
    if existing is not None:
        if message.numerus:
            existing.set("numerus", "yes")
        return

    element = ET.SubElement(context, "message")
    if message.numerus:
        element.set("numerus", "yes")
    ET.SubElement(element, "source").text = message.source
    if message.comment is not None:
        ET.SubElement(element, "comment").text = message.comment
    translation = ET.SubElement(element, "translation")
    translation.set("type", "unfinished")


def _find_message(context: ET.Element, message: MessageKey) -> ET.Element | None:
    for element in context.findall("message"):
        if element.findtext("source") != message.source:
            continue
        comment = element.findtext("comment")
        if (comment or None) == message.comment:
            return element
    return None


def _indent(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "    "
    child_indent = "\n" + (level + 1) * "    "
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = child_indent
        for child in children:
            _indent(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def _normalise_ts_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.startswith("<?xml"):
        _, _, body = text.partition("\n")
    else:
        body = text
    if body.startswith("<!DOCTYPE TS>\n"):
        body = body.removeprefix("<!DOCTYPE TS>\n")
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n' + body,
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        type=Path,
        dest="sources",
        help="Python file or directory to scan. May be passed multiple times.",
    )
    parser.add_argument(
        "--ts",
        action="append",
        type=Path,
        required=True,
        dest="ts_files",
        help="Qt Linguist TS file to update. May be passed multiple times.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    sources = args.sources if args.sources else list(DEFAULT_SOURCES)
    messages = extract_messages(sources)
    if not messages:
        print("No translation calls were extracted.", file=sys.stderr)
        return 1

    for ts_file in args.ts_files:
        update_ts(ts_file, messages)

    print(f"Extracted {len(messages)} translation messages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
