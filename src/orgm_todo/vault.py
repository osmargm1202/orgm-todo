"""Operaciones de dominio cuyo estado es Markdown dentro del vault."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import VaultConfig
from .markdown import (
    DATE_RE,
    Document,
    Item,
    MarkdownError,
    append_id,
    escape_cell,
    exact_wikilink,
    new_id,
    normalize,
    parse_document,
    replace_item_line,
    replace_wikilink,
    validate_name,
)


class VaultError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    document: str
    title: str
    item: Item


@dataclass(frozen=True)
class SummaryEntry:
    title: str
    document: str
    text: str
    checked: bool | None
    due: str | None
    invalid_date: bool


class Vault:
    def __init__(self, config: VaultConfig):
        self.config = config

    def _directory(self, key: str) -> Path:
        return self.config.path(key)

    def _files(self, key: str) -> list[Path]:
        directory = self._directory(key)
        return sorted(directory.glob("*.md"), key=lambda file: normalize(file.stem))

    def _named_file(self, key: str, name: str, *, required: bool = True) -> Path:
        name = validate_name(name)
        candidates = [file for file in self._files(key) if normalize(file.stem) == normalize(name)]
        if len(candidates) > 1:
            raise VaultError(f"Destino ambiguo para {name}")
        if not candidates:
            if required:
                raise VaultError(f"No existe: {name}")
            return self._directory(key) / f"{name}.md"
        return candidates[0]

    def _document(self, project: str | None = None) -> Document:
        return parse_document(self.config.general_path if project is None else self._named_file("projects", project))

    @staticmethod
    def _check_collision(directory: Path, name: str) -> None:
        if any(normalize(file.stem) == normalize(name) for file in directory.glob("*.md")):
            raise VaultError(f"Ya existe: {name}")

    @staticmethod
    def _write_new(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def list_clients(self, archived: bool = False) -> list[str]:
        return [file.stem for file in self._files("archive_clients" if archived else "clients")]

    def create_client(self, name: str, fields: dict[str, str]) -> None:
        name = validate_name(name)
        self._check_collision(self._directory("clients"), name)
        normalized: dict[str, tuple[str, str]] = {}
        for field, value in fields.items():
            field, value = validate_name(field), escape_cell(value)
            key = normalize(field)
            if key in normalized and normalized[key][1] != value:
                raise VaultError(f"Campo duplicado con valores distintos: {field}")
            normalized[key] = (field, value)
        rows = "".join(f"| {escape_cell(field)} | {value} |\n" for field, value in normalized.values())
        self._write_new(
            self._directory("clients") / f"{name}.md",
            f"# {name}\n\n## Datos\n\n| Campo | Valor |\n| --- | --- |\n{rows}\n## Proyectos\n",
        )

    @staticmethod
    def _find_table(doc: Document, section_name: str) -> tuple[int, int] | None:
        section = doc.section(section_name)
        if section is None:
            return None
        start, end = doc.section_bounds(section)
        first = next((i for i in range(start + 1, end) if doc.lines[i].strip()), None)
        if first is None or "|" not in doc.lines[first] or first + 1 >= end or "|" not in doc.lines[first + 1]:
            return None
        table_end = first + 2
        while table_end < end and doc.lines[table_end].lstrip().startswith("|"):
            table_end += 1
        return first, table_end

    @staticmethod
    def _cells(line: str) -> list[str]:
        raw = line.strip()
        if not raw.startswith("|") or not raw.endswith("|"):
            raise VaultError("Tabla mal formada")
        return [cell.strip().replace("\\|", "|") for cell in raw[1:-1].split("|")]

    def _update_fields(self, path: Path, set_fields: dict[str, str], remove_fields: set[str]) -> None:
        doc = parse_document(path)
        overlap = set(map(normalize, set_fields)) & set(map(normalize, remove_fields))
        if overlap:
            raise VaultError("No puede establecer y quitar el mismo campo")
        section = doc.section("Datos")
        table = self._find_table(doc, "Datos")
        lines = doc.lines.copy()
        if table is None:
            insertion = len(lines) if section is None else doc.section_bounds(section)[1]
            block = [f"## Datos{doc.newline}", doc.newline, f"| Campo | Valor |{doc.newline}", f"| --- | --- |{doc.newline}"]
            lines[insertion:insertion] = block
            doc.replace(lines)
            doc = parse_document(path)
            table = self._find_table(doc, "Datos")
            assert table is not None
            lines = doc.lines.copy()
        first, end = table
        existing: dict[str, tuple[int, str, str]] = {}
        for index in range(first + 2, end):
            cells = self._cells(lines[index])
            if len(cells) != 2:
                raise VaultError("Tabla de Datos mal formada")
            key = normalize(cells[0])
            if key in existing:
                raise VaultError("Tabla de Datos ambigua")
            existing[key] = (index, cells[0], cells[1])
        delete: list[int] = []
        additions: list[str] = []
        for field in remove_fields:
            found = existing.get(normalize(field))
            if found:
                delete.append(found[0])
        for field, value in set_fields.items():
            field, value = validate_name(field), escape_cell(value)
            found = existing.get(normalize(field))
            line = f"| {escape_cell(field)} | {value} |{doc.newline}"
            if found:
                lines[found[0]] = line
            else:
                additions.append(line)
        for index in reversed(delete):
            del lines[index]
        insertion = end - len(delete)
        lines[insertion:insertion] = additions
        doc.replace(lines)

    def update_client(self, name: str, fields: dict[str, str], remove: set[str]) -> None:
        self._update_fields(self._named_file("clients", name), fields, remove)

    def _add_link(self, path: Path, header_name: str, target: str) -> None:
        doc = parse_document(path)
        if any(exact_wikilink(line, target) for line in doc.lines):
            return
        header = doc.section(header_name)
        lines = doc.lines.copy()
        if header is None:
            if lines and lines[-1].strip():
                lines.append(doc.newline)
            lines.extend([f"## {header_name}{doc.newline}", f"- [[{target}]]{doc.newline}"])
        else:
            _, end = doc.section_bounds(header)
            lines.insert(end, f"- [[{target}]]{doc.newline}")
        doc.replace(lines)

    def _remove_link(self, path: Path, target: str) -> None:
        doc = parse_document(path)
        lines = [line for line in doc.lines if not exact_wikilink(line, target)]
        if lines != doc.lines:
            doc.replace(lines)

    def _client_for_project(self, project: str) -> str:
        path = self._named_file("projects", project)
        doc = parse_document(path)
        table = self._find_table(doc, "Datos")
        if table:
            for index in range(table[0] + 2, table[1]):
                cells = self._cells(doc.lines[index])
                if len(cells) == 2 and normalize(cells[0]) == "cliente":
                    match = re.fullmatch(r"\[\[([^\]|#]+).*", cells[1])
                    return match.group(1) if match else cells[1]
        raise VaultError(f"Proyecto sin Cliente válido: {project}")

    def list_projects(self, archived: bool = False) -> list[str]:
        return [file.stem for file in self._files("archive_projects" if archived else "projects")]

    def create_project(self, name: str, client: str, titles: list[str]) -> None:
        name, client = validate_name(name), validate_name(client)
        client_path = self._named_file("clients", client)
        self._check_collision(self._directory("projects"), name)
        seen: set[str] = set()
        for title in titles:
            title = validate_name(title)
            if normalize(title) in seen:
                raise VaultError(f"Título duplicado: {title}")
            seen.add(normalize(title))
        sections = titles or ["Pendiente"]
        content = (
            f"# {name}\n\n## Datos\n\n| Campo | Valor |\n| --- | --- |\n"
            f"| Cliente | [[{client_path.stem}]] |\n| Estado | Activo |\n| Creado | {date.today().isoformat()} |\n"
        )
        content += "".join(f"\n## {title}\n" for title in sections)
        self._write_new(self._directory("projects") / f"{name}.md", content)
        self._add_link(self.config.general_path, f"[[{client_path.stem}]]", name)
        self._add_link(client_path, "Proyectos", name)

    def update_project(self, name: str, client: str | None = None, status: str | None = None) -> None:
        path = self._named_file("projects", name)
        old_client = self._client_for_project(name)
        fields: dict[str, str] = {}
        if client is not None:
            new_client = self._named_file("clients", client).stem
            fields["Cliente"] = f"[[{new_client}]]"
        if status is not None:
            fields["Estado"] = escape_cell(status)
        if fields:
            self._update_fields(path, fields, set())
        if client is not None and normalize(old_client) != normalize(new_client):
            self._remove_link(self.config.general_path, name)
            self._remove_link(self._named_file("clients", old_client), name)
            self._add_link(self.config.general_path, f"[[{new_client}]]", name)
            self._add_link(self._named_file("clients", new_client), "Proyectos", name)

    def archive_project(self, name: str) -> None:
        source = self._named_file("projects", name)
        destination = self._directory("archive_projects") / source.name
        if destination.exists():
            raise VaultError(f"Ya existe en el baúl: {source.stem}")
        client = self._client_for_project(source.stem)
        self._update_fields(source, {"Estado": "Completado"}, set())
        source.replace(destination)
        self._remove_link(self.config.general_path, source.stem)
        self._remove_link(self._named_file("clients", client), source.stem)

    def restore_project(self, name: str) -> None:
        source = self._named_file("archive_projects", name)
        destination = self._directory("projects") / source.name
        if destination.exists():
            raise VaultError(f"Ya existe activo: {source.stem}")
        doc = parse_document(source)
        table = self._find_table(doc, "Datos")
        client = ""
        if table:
            for i in range(table[0] + 2, table[1]):
                cells = self._cells(doc.lines[i])
                if len(cells) == 2 and normalize(cells[0]) == "cliente":
                    client = re.sub(r"^\[\[([^\]|#]+).*", r"\1", cells[1])
        if not client:
            raise VaultError("Proyecto archivado sin Cliente válido")
        self._named_file("clients", client)
        source.replace(destination)
        self._update_fields(destination, {"Estado": "Activo"}, set())
        self._add_link(self.config.general_path, f"[[{client}]]", destination.stem)
        self._add_link(self._named_file("clients", client), "Proyectos", destination.stem)

    def archive_client(self, name: str) -> None:
        source = self._named_file("clients", name)
        if any(normalize(self._client_for_project(project)) == normalize(source.stem) for project in self.list_projects()):
            raise VaultError("No puede archivar un cliente con proyectos activos")
        destination = self._directory("archive_clients") / source.name
        if destination.exists():
            raise VaultError(f"Ya existe en el baúl: {source.stem}")
        source.replace(destination)

    def _rename_links(self, old: str, new: str) -> None:
        orgm = self.config.vault / "ORGM"
        for path in [self.config.general_path, *orgm.rglob("*.md")]:
            if not path.exists():
                continue
            doc = parse_document(path)
            lines = [replace_wikilink(line, old, new) for line in doc.lines]
            if lines != doc.lines:
                doc.replace(lines)

    def rename_client(self, old: str, new: str) -> None:
        source = self._named_file("clients", old)
        new = validate_name(new)
        self._check_collision(self._directory("clients"), new)
        self._rename_links(source.stem, new)
        source.replace(source.with_name(f"{new}.md"))

    def rename_project(self, old: str, new: str) -> None:
        source = self._named_file("projects", old)
        new = validate_name(new)
        self._check_collision(self._directory("projects"), new)
        self._rename_links(source.stem, new)
        source.replace(source.with_name(f"{new}.md"))

    def add_title(self, title: str, project: str | None = None) -> None:
        title = validate_name(title)
        doc = self._document(project)
        if doc.section(title):
            raise VaultError(f"Título ya existe: {title}")
        lines = doc.lines.copy()
        if lines and lines[-1].strip():
            lines.append(doc.newline)
        lines.append(f"## {title}{doc.newline}")
        doc.replace(lines)

    def rename_title(self, old: str, new: str, project: str | None = None) -> None:
        new = validate_name(new)
        doc = self._document(project)
        current = doc.section(old)
        if current is None:
            raise VaultError(f"No existe el título: {old}")
        if doc.section(new):
            raise VaultError(f"Título ya existe: {new}")
        lines = doc.lines.copy()
        lines[current.line] = f"{'#' * current.level} {new}{doc.newline}"
        doc.replace(lines)

    def delete_title(self, title: str, project: str | None = None, force: bool = False) -> None:
        doc = self._document(project)
        header = doc.section(title)
        if header is None:
            raise VaultError(f"No existe el título: {title}")
        start, end = doc.section_bounds(header)
        if any(line.strip() for line in doc.lines[start + 1 : end]) and not force:
            raise VaultError("El título no está vacío; use --force")
        lines = doc.lines.copy()
        del lines[start:end]
        doc.replace(lines)

    def _select(self, selector: str, project: str | None, task: bool | None = None) -> tuple[Document, Item]:
        doc = self._document(project)
        wanted = selector.removeprefix("^").casefold()
        candidates = [item for item in doc.items if (task is None or (item.checked is not None) == task)]
        exact = [item for item in candidates if item.ident == wanted]
        matches = exact or [item for item in candidates if wanted in item.text.casefold()]
        if len(matches) != 1:
            candidates_text = "; ".join(f"{project or 'General'} / {item.title} / {item.ident or 'línea ' + str(item.line + 1)}" for item in matches)
            action = "No se encontró" if not matches else f"Selector ambiguo: {candidates_text}"
            raise VaultError(action)
        return doc, matches[0]

    @staticmethod
    def _line_for_item(item: Item, *, text: str | None = None, checked: bool | None = None, due: str | None | object = ..., ident: str | None = None) -> str:
        content = text if text is not None else item.text
        chosen_due = item.due if due is ... else due
        line = f"{item.indent}{item.marker}"
        if item.checked is not None:
            line += f"[{'x' if (item.checked if checked is None else checked) else ' '}] "
        line += content
        if chosen_due:
            line += f" 📅 {chosen_due}"
        return append_id(line + "\n", ident or item.ident)

    def _ensure_title(self, doc: Document, title: str, create: bool) -> Document:
        if doc.section(title):
            return doc
        if not create:
            raise VaultError(f"No existe el título destino: {title}")
        self.add_title(title, None if doc.path == self.config.general_path else doc.path.stem)
        return parse_document(doc.path)

    def add_note(self, text: str, title: str = "Pendiente", project: str | None = None) -> str:
        if not text.strip() or "\n" in text or "\r" in text:
            raise VaultError("La nota debe ocupar una sola línea")
        doc = self._ensure_title(self._document(project), title, True)
        header = doc.section(title)
        assert header
        _, end = doc.section_bounds(header)
        ident = new_id()
        lines = doc.lines.copy()
        lines.insert(end, f"- {text.strip()} ^{ident}{doc.newline}")
        doc.replace(lines)
        return ident

    def add_task(self, text: str, title: str = "Pendiente", project: str | None = None, due: str | None = None) -> str:
        if not text.strip() or "\n" in text or "\r" in text:
            raise VaultError("La tarea debe ocupar una sola línea")
        if due:
            date.fromisoformat(due)
        doc = self._ensure_title(self._document(project), title, True)
        header = doc.section(title)
        assert header
        _, end = doc.section_bounds(header)
        ident = new_id()
        suffix = f" 📅 {due}" if due else ""
        lines = doc.lines.copy()
        lines.insert(end, f"- [ ] {text.strip()}{suffix} ^{ident}{doc.newline}")
        doc.replace(lines)
        return ident

    def list_entries(self, project: str | None = None, task: bool | None = None) -> list[Entry]:
        docs = [self._document(project)] if project is not None else [self._document()]
        return [Entry(doc.path.stem, item.title, item) for doc in docs for item in doc.items if task is None or (item.checked is not None) == task]

    def update_note(self, selector: str, text: str, project: str | None = None) -> str:
        doc, item = self._select(selector, project, False)
        if not text.strip() or "\n" in text or "\r" in text:
            raise VaultError("La nota debe ocupar una sola línea")
        replace_item_line(doc, item, self._line_for_item(item, text=text.strip()))
        return item.ident or ""

    def update_task(self, selector: str, project: str | None = None, text: str | None = None, due: str | None | object = ...) -> str:
        doc, item = self._select(selector, project, True)
        if text is not None and (not text.strip() or "\n" in text or "\r" in text):
            raise VaultError("La tarea debe ocupar una sola línea")
        if due is not ... and due is not None:
            date.fromisoformat(str(due))
        replace_item_line(doc, item, self._line_for_item(item, text=text.strip() if text else None, due=due))
        return item.ident or ""

    def set_task_state(self, selector: str, checked: bool, project: str | None = None) -> str:
        doc, item = self._select(selector, project, True)
        raw = re.sub(r"(\[)[ xX](\])", rf"\1{'x' if checked else ' '}\2", item.raw, count=1)
        if item.ident is None:
            raw = append_id(raw)
        replace_item_line(doc, item, raw)
        return item.ident or ""

    def move_item(self, selector: str, title: str, project: str | None = None, task: bool | None = None) -> str:
        doc, item = self._select(selector, project, task)
        target = doc.section(title)
        if target is None:
            raise VaultError(f"No existe el título destino: {title}")
        _, end = doc.section_bounds(target)
        lines = doc.lines.copy()
        block = lines[item.line:item.end]
        del lines[item.line:item.end]
        if end > item.line:
            end -= item.end - item.line
        lines[end:end] = block
        doc.replace(lines)
        return item.ident or ""

    def delete_item(self, selector: str, project: str | None = None, task: bool | None = None) -> str:
        doc, item = self._select(selector, project, task)
        lines = doc.lines.copy()
        del lines[item.line:item.end]
        doc.replace(lines)
        return item.ident or ""

    def recurring_tasks(self, text: str, every: str, start: date, until: date, title: str = "Pendiente", project: str | None = None) -> list[str]:
        if every not in {"semana", "mes"} or until < start:
            raise VaultError("Recurrencia inválida")
        dates: list[date] = []
        current = start
        day = start.day
        while current <= until:
            dates.append(current)
            if every == "semana":
                current += timedelta(days=7)
            else:
                month = current.month % 12 + 1
                year = current.year + (current.month == 12)
                current = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        return [self.add_task(text, title, project, occurrence.isoformat()) for occurrence in dates]

    def summaries(
        self,
        title: str | None = None,
        project: str | None = None,
        include_done: bool = False,
        include_undated: bool = False,
        start: date | None = None,
        until: date | None = None,
    ) -> list[SummaryEntry]:
        docs = [self._document(project)] if project else [self._document(), *(parse_document(path) for path in self._files("projects"))]
        results: list[SummaryEntry] = []
        wanted = normalize(title) if title else None
        for doc in docs:
            name = "General" if doc.path == self.config.general_path else doc.path.stem
            headers = [header for header in doc.headers if wanted is None or normalize(header.text) == wanted]
            for header in headers:
                if header.level == 1 and normalize(header.text) == normalize(doc.path.stem):
                    continue
                for item in doc.section_items(header):
                    if item.checked is True and not include_done:
                        continue
                    parsed: date | None = None
                    invalid = False
                    if item.due:
                        try:
                            parsed = date.fromisoformat(item.due)
                        except ValueError:
                            invalid = True
                    temporal = start is not None or until is not None
                    if temporal and (parsed is None or (start and parsed < start) or (until and parsed > until)):
                        if not (item.due is None and include_undated):
                            continue
                    results.append(SummaryEntry(header.text, name, item.text, item.checked, item.due, invalid))
                if wanted and not doc.section_items(header):
                    results.append(SummaryEntry(header.text, name, "", None, None, False))
        return results
