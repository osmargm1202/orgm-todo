"""Parser tolerante y parches mínimos para Markdown escrito a mano."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

HEADER_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\r?\n)?$")
ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-*+] |\d+[.)] )(?:(?P<box>\[(?P<state> |x|X)\][ \t]+))?(?P<body>.*?)(?P<ending>\r?\n)?$"
)
ID_RE = re.compile(r"(?:\s+\^)(orgm-[0-9a-fA-F]{8})(?=\s*$)")
DATE_RE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")


class MarkdownError(ValueError):
    pass


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_name(value: str) -> str:
    value = value.strip()
    if not value or value in {".", ".."} or value.startswith("."):
        raise MarkdownError("El nombre no puede estar vacío, ser oculto, . o ..")
    if any(c in value for c in "/\\\r\n") or any(ord(c) < 32 for c in value):
        raise MarkdownError("El nombre contiene caracteres no permitidos")
    return value


def escape_cell(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise MarkdownError("Las celdas no admiten saltos de línea")
    return value.replace("|", "\\|")


@dataclass(frozen=True)
class Header:
    line: int
    level: int
    text: str


@dataclass(frozen=True)
class Item:
    line: int
    end: int
    title: str
    text: str
    raw: str
    indent: str
    marker: str
    checked: bool | None
    ident: str | None
    due: str | None


@dataclass
class Document:
    path: Path
    text: str
    lines: list[str]
    digest: str
    newline: str
    bom: str
    headers: list[Header]
    items: list[Item]

    def section(self, name: str) -> Header | None:
        target = normalize(name)
        for header in self.headers:
            if normalize(header.text) == target:
                return header
        return None

    def section_bounds(self, header: Header) -> tuple[int, int]:
        end = len(self.lines)
        for candidate in self.headers:
            if candidate.line > header.line and candidate.level <= header.level:
                end = candidate.line
                break
        return header.line, end

    def section_items(self, header: Header | None) -> list[Item]:
        if header is None:
            return [item for item in self.items if item.title == "General"]
        start, end = self.section_bounds(header)
        return [item for item in self.items if start < item.line < end]

    def replace(self, lines: list[str]) -> None:
        new = self.bom + "".join(lines)
        current = self.path.read_bytes()
        if hashlib.sha256(current).hexdigest() != self.digest:
            raise MarkdownError(f"Cambio concurrente detectado en {self.path}")
        encoded = new.encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=f".{self.path.name}.", delete=False) as tmp:
            tmp.write(encoded)
            temporary = Path(tmp.name)
        try:
            if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:
                raise MarkdownError(f"Cambio concurrente detectado en {self.path}")
            os.replace(temporary, self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _ignored_lines(lines: list[str]) -> set[int]:
    ignored: set[int] = set()
    if lines and lines[0].lstrip("\ufeff").strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in {"---", "..."}:
                ignored.update(range(index + 1))
                break
    fenced = False
    for index, line in enumerate(lines):
        if index in ignored:
            continue
        if re.match(r"^[ \t]*(```|~~~)", line):
            ignored.add(index)
            fenced = not fenced
        elif fenced:
            ignored.add(index)
    return ignored


def parse_document(path: str | Path) -> Document:
    file = Path(path)
    try:
        raw_bytes = file.read_bytes()
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarkdownError(f"UTF-8 inválido en {file}") from exc
    bom = "\ufeff" if raw.startswith("\ufeff") else ""
    text = raw[len(bom):]
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    ignored = _ignored_lines(lines)
    headers: list[Header] = []
    for index, line in enumerate(lines):
        if index in ignored:
            continue
        match = HEADER_RE.match(line)
        if match:
            headers.append(Header(index, len(match.group(1)), match.group(2).strip()))
    documentary_h1 = headers[0] if headers and headers[0].level == 1 and normalize(headers[0].text) == normalize(file.stem) else None
    items: list[Item] = []
    for index, line in enumerate(lines):
        if index in ignored:
            continue
        match = ITEM_RE.match(line)
        if not match:
            continue
        prior = [h for h in headers if h.line < index and h is not documentary_h1]
        title = prior[-1].text if prior else "General"
        end = index + 1
        indent = len(match.group("indent").expandtabs(4))
        cursor = end
        while cursor < len(lines):
            continuation = lines[cursor]
            if not continuation.strip():
                cursor += 1
                continue
            leading = continuation[: len(continuation) - len(continuation.lstrip(" \t"))]
            if len(leading.expandtabs(4)) <= indent:
                break
            end = cursor + 1
            cursor += 1
        body = match.group("body").rstrip("\r\n")
        ident_match = ID_RE.search(body)
        ident = ident_match.group(1).lower() if ident_match else None
        visible = ID_RE.sub("", body).rstrip()
        due_match = DATE_RE.search(visible)
        due = due_match.group(1) if due_match else None
        visible = DATE_RE.sub("", visible).rstrip()
        state = match.group("state")
        items.append(Item(index, end, title, visible, line, match.group("indent"), match.group("marker"), None if state is None else state.casefold() == "x", ident, due))
    return Document(file, text, lines, hashlib.sha256(raw_bytes).hexdigest(), newline, bom, headers, items)


def new_id() -> str:
    return f"orgm-{uuid.uuid4().hex[:8]}"


def append_id(line: str, ident: str | None = None) -> str:
    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    body = line[: -len(ending)] if ending else line
    return f"{body} ^{ident or new_id()}{ending}"


def replace_item_line(document: Document, item: Item, line: str) -> None:
    lines = document.lines.copy()
    lines[item.line] = line
    document.replace(lines)


def exact_wikilink(line: str, target: str) -> bool:
    marker = r"(?:[-*+][ \t]+|\d+[.)][ \t]+)"
    return re.fullmatch(rf"[ \t]*{marker}\[\[{re.escape(target)}\]\][ \t]*(?:\r?\n)?", line) is not None


def replace_wikilink(text: str, old: str, new: str) -> str:
    return re.sub(rf"\[\[{re.escape(old)}(?=\]\]|[|#])", f"[[{new}", text)
