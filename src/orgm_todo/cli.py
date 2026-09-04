"""Interfaz de línea de comandos para orgm-todo."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from .config import ConfigError, config_path, initialize, load_config, save_config
from .markdown import MarkdownError
from .vault import Entry, SummaryEntry, Vault, VaultError

app = typer.Typer(no_args_is_help=True, help="Seguimiento ORGM directamente sobre notas Obsidian.")
cliente_app = typer.Typer(no_args_is_help=True)
proyecto_app = typer.Typer(no_args_is_help=True)
titulo_app = typer.Typer(no_args_is_help=True)
nota_app = typer.Typer(no_args_is_help=True)
tarea_app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(cliente_app, name="client")
app.add_typer(proyecto_app, name="project")
app.add_typer(titulo_app, name="title")
app.add_typer(nota_app, name="note")
app.add_typer(tarea_app, name="task")
app.add_typer(config_app, name="config")
console = Console()
error_console = Console(stderr=True)


def fail(error: Exception) -> None:
    error_console.print(f"[red]{escape(str(error))}[/red]")
    raise typer.Exit(1)


def vault() -> Vault:
    try:
        return Vault(load_config())
    except ConfigError as exc:
        fail(exc)


def run(fn):
    try:
        return fn()
    except (VaultError, MarkdownError, ValueError) as exc:
        fail(exc)


def fields_from(
    data: list[str], empresa: str | None, contacto: str | None, telefono: str | None, correo: str | None, direccion: str | None
) -> dict[str, str]:
    fields: dict[str, tuple[str, str]] = {}

    def add(key: str, value: str) -> None:
        display = key.strip()
        if not display:
            raise VaultError("--dato requiere un campo")
        normalized = " ".join(display.split()).casefold()
        existing = fields.get(normalized)
        if existing is not None:
            if existing[1] != value:
                raise VaultError(f"Campo duplicado: {display}")
            return
        fields[normalized] = (display, value)

    for pair in data:
        if "=" not in pair:
            raise VaultError("--dato debe tener formato CAMPO=VALOR")
        key, value = pair.split("=", 1)
        add(key, value)
    for key, value in {"Empresa": empresa, "Contacto": contacto, "Teléfono": telefono, "Correo": correo, "Dirección": direccion}.items():
        if value is not None:
            add(key, value)
    return {key: value for key, value in fields.values()}


@app.command()
def init(vault_path: Annotated[Path | None, typer.Option("--vault")] = None) -> None:
    """Inicializa la estructura faltante y guarda el vault."""
    try:
        config = initialize(vault_path)
    except ConfigError as exc:
        fail(exc)
    console.print(f"Vault configurado: [bold]{escape(str(config.vault))}[/bold]")


@config_app.command("show")
def config_show() -> None:
    """Muestra la configuración guardada."""
    try:
        config = load_config()
    except ConfigError as exc:
        fail(exc)
    console.print(f"vault = {config.vault}\nconfig = {config_path()}")

@config_app.command("set-vault")
def config_vault(path: Path) -> None:
    """Cambia el vault configurado."""
    try:
        config = save_config(path)
    except ConfigError as exc:
        fail(exc)
    console.print(f"Vault configurado: {config.vault}")


@cliente_app.command("create")
def client_create(
    nombre: str,
    dato: Annotated[list[str], typer.Option("--data")] = [],
    empresa: Annotated[str | None, typer.Option("--company")] = None,
    contacto: Annotated[str | None, typer.Option("--contact")] = None,
    telefono: Annotated[str | None, typer.Option("--phone")] = None,
    correo: Annotated[str | None, typer.Option("--email")] = None,
    direccion: Annotated[str | None, typer.Option("--address")] = None,
) -> None:
    run(lambda: vault().create_client(nombre, fields_from(dato, empresa, contacto, telefono, correo, direccion)))
    console.print(f"Cliente creado: {escape(nombre)}")


@cliente_app.command("list")
def client_list() -> None:
    names = run(lambda: vault().list_clients())
    for name in names:
        console.print(escape(name))


@cliente_app.command("view")
def client_show(nombre: str) -> None:
    path = run(lambda: vault()._named_file("clients", nombre))
    console.print(path.read_text(encoding="utf-8"), end="")


@cliente_app.command("update")
def client_update(
    nombre: str,
    dato: Annotated[list[str], typer.Option("--data")] = [],
    quitar_dato: Annotated[list[str], typer.Option("--remove-data")] = [],
) -> None:
    run(lambda: vault().update_client(nombre, fields_from(dato, None, None, None, None, None), set(quitar_dato)))
    console.print(f"Cliente actualizado: {escape(nombre)}")


@cliente_app.command("rename")
def client_rename(actual: str, nuevo: str) -> None:
    run(lambda: vault().rename_client(actual, nuevo))
    console.print(f"Cliente renombrado: {escape(nuevo)}")


@cliente_app.command("archive")
def client_archive(nombre: str) -> None:
    run(lambda: vault().archive_client(nombre))
    console.print(f"Cliente archivado: {escape(nombre)}")


@proyecto_app.command("create")
def project_create(nombre: str, cliente: Annotated[str, typer.Option("--client")], titulo: Annotated[list[str], typer.Option("--title")] = []) -> None:
    run(lambda: vault().create_project(nombre, cliente, titulo))
    console.print(f"Proyecto creado: {escape(nombre)}")


@proyecto_app.command("list")
def project_list() -> None:
    for name in run(lambda: vault().list_projects()):
        console.print(escape(name))


@proyecto_app.command("view")
def project_show(nombre: str) -> None:
    path = run(lambda: vault()._named_file("projects", nombre))
    console.print(path.read_text(encoding="utf-8"), end="")


@proyecto_app.command("update")
def project_update(
    nombre: str,
    cliente: Annotated[str | None, typer.Option("--client")] = None,
    estado: Annotated[str | None, typer.Option("--status")] = None,
) -> None:
    run(lambda: vault().update_project(nombre, cliente, estado))
    console.print(f"Proyecto actualizado: {escape(nombre)}")


@proyecto_app.command("rename")
def project_rename(actual: str, nuevo: str) -> None:
    run(lambda: vault().rename_project(actual, nuevo))
    console.print(f"Proyecto renombrado: {escape(nuevo)}")


@proyecto_app.command("archive")
def project_archive(nombre: str) -> None:
    run(lambda: vault().archive_project(nombre))
    console.print(f"Proyecto archivado: {escape(nombre)}")


@proyecto_app.command("restore")
def project_restore(nombre: str) -> None:
    run(lambda: vault().restore_project(nombre))
    console.print(f"Proyecto restaurado: {escape(nombre)}")


@titulo_app.command("add")
def title_add(titulo: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().add_title(titulo, proyecto))


@titulo_app.command("rename")
def title_rename(actual: str, nuevo: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().rename_title(actual, nuevo, proyecto))


@titulo_app.command("delete")
def title_delete(titulo: str, proyecto: Annotated[str | None, typer.Option("--project")] = None, force: bool = False) -> None:
    run(lambda: vault().delete_title(titulo, proyecto, force))


@nota_app.command("add")
def note_add(texto: str, titulo: Annotated[str, typer.Option("--title")] = "Pendiente", proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    ident = run(lambda: vault().add_note(texto, titulo, proyecto))
    console.print(ident)


def print_entries(entries: list[Entry]) -> None:
    for entry in entries:
        state = "[x] " if entry.item.checked else "[ ] " if entry.item.checked is False else ""
        due = f" 📅 {entry.item.due}" if entry.item.due else ""
        ident = f" ^{entry.item.ident}" if entry.item.ident else ""
        console.print(f"{escape(entry.document)} / {escape(entry.title)}: {state}{escape(entry.item.text)}{due}{ident}")


@nota_app.command("list")
def note_list(proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    print_entries(run(lambda: vault().list_entries(proyecto, False)))


@nota_app.command("update")
def note_update(selector: str, texto: Annotated[str, typer.Option("--text")], proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().update_note(selector, texto, proyecto))


@nota_app.command("move")
def note_move(selector: str, titulo: Annotated[str, typer.Option("--title")], proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().move_item(selector, titulo, proyecto, False))


@nota_app.command("delete")
def note_delete(selector: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().delete_item(selector, proyecto, False))


@tarea_app.command("add")
def task_add(
    texto: str,
    titulo: Annotated[str, typer.Option("--title")] = "Pendiente",
    proyecto: Annotated[str | None, typer.Option("--project")] = None,
    fecha: Annotated[str | None, typer.Option("--date")] = None,
    cada: Annotated[str | None, typer.Option("--every")] = None,
    desde: Annotated[str | None, typer.Option("--from")] = None,
    hasta: Annotated[str | None, typer.Option("--to")] = None,
) -> None:
    def action():
        store = vault()
        if cada:
            if fecha or not desde or not hasta:
                raise VaultError("--every requires --from and --to; it cannot be combined with --date")
            return store.recurring_tasks(texto, cada, date.fromisoformat(desde), date.fromisoformat(hasta), titulo, proyecto)
        if desde or hasta:
            raise VaultError("--from and --to require --every")
        return [store.add_task(texto, titulo, proyecto, fecha)]
    for ident in run(action):
        console.print(ident)


@tarea_app.command("list")
def task_list(proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    print_entries(run(lambda: vault().list_entries(proyecto, True)))


@tarea_app.command("complete")
def task_complete(selector: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().set_task_state(selector, True, proyecto))


@tarea_app.command("pending")
def task_pending(selector: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().set_task_state(selector, False, proyecto))


@tarea_app.command("update")
def task_update(
    selector: str,
    proyecto: Annotated[str | None, typer.Option("--project")] = None,
    texto: Annotated[str | None, typer.Option("--text")] = None,
    fecha: Annotated[str | None, typer.Option("--date")] = None,
    sin_fecha: Annotated[bool, typer.Option("--no-date")] = False,
) -> None:
    if fecha and sin_fecha:
        fail(VaultError("--date and --no-date cannot be combined"))
    due: str | None | object = ... if not sin_fecha and fecha is None else None if sin_fecha else fecha
    run(lambda: vault().update_task(selector, proyecto, texto, due))


@tarea_app.command("move")
def task_move(selector: str, titulo: Annotated[str, typer.Option("--title")], proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().move_item(selector, titulo, proyecto, True))


@tarea_app.command("delete")
def task_delete(selector: str, proyecto: Annotated[str | None, typer.Option("--project")] = None) -> None:
    run(lambda: vault().delete_item(selector, proyecto, True))


def period(hoy: bool, semana: bool, mes: str | None, desde: str | None, hasta: str | None) -> tuple[date | None, date | None, str]:
    chosen = sum(bool(value) for value in (hoy, semana, mes, desde or hasta))
    if chosen > 1 or (desde is None) != (hasta is None):
        raise VaultError("Use one time filter only; --from requires --to")
    now = date.today()
    if hoy:
        return now, now, f"Hoy ({now})"
    if semana:
        start = now - timedelta(days=now.weekday())
        return start, start + timedelta(days=6), f"Semana {start} a {start + timedelta(days=6)}"
    if mes:
        start = date.fromisoformat(f"{mes}-01")
        end = date(start.year, start.month, __import__("calendar").monthrange(start.year, start.month)[1])
        return start, end, f"Mes {mes}"
    if desde:
        start, end = date.fromisoformat(desde), date.fromisoformat(hasta or "")
        if end < start:
            raise VaultError("--to cannot be earlier than --from")
        return start, end, f"{start} a {end}"
    return None, None, "Todas las fechas"


@app.command("summary")
def summary(
    titulo: Annotated[str | None, typer.Option("--title")] = None,
    proyecto: Annotated[str | None, typer.Option("--project")] = None,
    incluir_sin_fecha: Annotated[bool, typer.Option("--include-undated")] = False,
    hoy: Annotated[bool, typer.Option("--today")] = False,
    semana: Annotated[bool, typer.Option("--week")] = False,
    mes: Annotated[str | None, typer.Option("--month")] = None,
    desde: Annotated[str | None, typer.Option("--from")] = None,
    hasta: Annotated[str | None, typer.Option("--to")] = None,
) -> None:
    start, end, label = run(lambda: period(hoy, semana, mes, desde, hasta))
    entries: list[SummaryEntry] = run(lambda: vault().summaries(titulo, proyecto, incluir_sin_fecha, start, end))
    populated = [entry for entry in entries if entry.text]
    if not entries:
        console.print("Sin pendientes para el filtro indicado")
        return
    console.print(Panel(f"{escape(label)} — {len(populated)} elementos", title="Resumen"))
    groups: dict[str, dict[str, list[SummaryEntry]]] = {}
    for entry in entries:
        groups.setdefault(entry.title, {}).setdefault(entry.document, []).append(entry)
    for heading, documents in groups.items():
        table = Table(title=escape(heading), show_header=True)
        table.add_column("Proyecto")
        table.add_column("Elemento")
        table.add_column("Fecha")
        for document, items in documents.items():
            for entry in items:
                if not entry.text:
                    table.add_row(escape(document), "Sin elementos", "")
                    continue
                state = "[x] " if entry.checked else "[ ] " if entry.checked is False else "• "
                label_date = (entry.due or "") + (" (inválida)" if entry.invalid_date else "")
                table.add_row(escape(document), escape(state + entry.text), escape(label_date))
        console.print(table)


if __name__ == "__main__":
    app()
