from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from orgm_todo.cli import app
from orgm_todo.config import ConfigError, config_path, initialize, load_config
from orgm_todo.markdown import MarkdownError, parse_document
from orgm_todo.vault import Vault, VaultError

runner = CliRunner()


@pytest.fixture()
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Vault]:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    config = initialize(root)
    return root, Vault(config)


def test_initialize_preserves_manual_agents_and_only_creates_missing(configured: tuple[Path, Vault]) -> None:
    root, _ = configured
    agents = root / "AGENTS.md"
    agents.write_text("manual\n\n<!-- orgm-todo:start -->\nviejo\n<!-- orgm-todo:end -->\n", encoding="utf-8")
    initialize(root)
    content = agents.read_text(encoding="utf-8")
    assert content.startswith("manual\n")
    assert "viejo" not in content
    assert "ignore `.trash/`" in content
    assert (root / "General.md").read_text(encoding="utf-8") == "# General\n\n## Pendiente\n"


def test_initialize_appends_managed_agents_without_changing_manual_bytes(configured: tuple[Path, Vault]) -> None:
    root, _ = configured
    agents = root / "AGENTS.md"
    manual = "Reglas manuales\n\n\n"
    agents.write_text(manual, encoding="utf-8")
    initialize(root)
    content = agents.read_text(encoding="utf-8")
    assert content.startswith(manual)
    assert content[len(manual) :].startswith("\n\n<!-- orgm-todo:start -->")


def test_load_config_rejects_escaping_and_symlinked_paths(configured: tuple[Path, Vault]) -> None:
    root, _ = configured
    saved = config_path()
    original = saved.read_text(encoding="utf-8")
    saved.write_text(original.replace('projects = "ORGM/Proyectos"', 'projects = "../../outside"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="no permitida"):
        load_config()
    outside = root.parent / "outside"
    outside.mkdir()
    (root / "ORGM/escape").symlink_to(outside, target_is_directory=True)
    saved.write_text(original.replace('projects = "ORGM/Proyectos"', 'projects = "ORGM/escape"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="fuera del vault"):
        load_config()


def test_parser_preserves_frontmatter_crlf_and_detects_concurrent_change(tmp_path: Path) -> None:
    path = tmp_path / "Documento.md"
    original = "---\r\ntitle: x\r\n---\r\n# Documento\r\n\r\n## Título\r\n- [X] tarea 📅 2026-02-01\r\n"
    path.write_bytes(original.encode())
    doc = parse_document(path)
    assert len(doc.items) == 1
    assert doc.items[0].checked is True and doc.items[0].title == "Título"
    path.write_text("otro", encoding="utf-8")
    with pytest.raises(MarkdownError, match="concurrente"):
        doc.replace(doc.lines)


def test_client_project_indexes_and_archive_restore(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {"Teléfono": "809-555-0100"})
    store.create_project("Proyecto 1", "ERIC", ["Correcciones"])
    assert "[[Proyecto 1]]" in (root / "General.md").read_text(encoding="utf-8")
    assert "[[Proyecto 1]]" in (root / "ORGM/Clientes/ERIC.md").read_text(encoding="utf-8")
    with pytest.raises(VaultError, match="proyectos activos"):
        store.archive_client("ERIC")
    store.archive_project("Proyecto 1")
    assert not (root / "ORGM/Proyectos/Proyecto 1.md").exists()
    assert "[[Proyecto 1]]" not in (root / "General.md").read_text(encoding="utf-8")
    store.restore_project("Proyecto 1")
    assert (root / "ORGM/Proyectos/Proyecto 1.md").exists()
    assert "| Estado | Activo |" in (root / "ORGM/Proyectos/Proyecto 1.md").read_text(encoding="utf-8")


def test_tasks_manual_notes_selectors_moves_and_recurrence(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {})
    store.create_project("Proyecto 1", "ERIC", ["Correcciones", "Pendiente"])
    ids = store.recurring_tasks("Informe", "mes", date(2026, 9, 30), date(2026, 11, 30), "Correcciones", "Proyecto 1")
    assert len(ids) == 3
    project = root / "ORGM/Proyectos/Proyecto 1.md"
    project.write_text(project.read_text(encoding="utf-8").replace("## Correcciones\n", "## Correcciones\n- Nota manual\n"), encoding="utf-8")
    entries = store.list_entries("Proyecto 1", None)
    october = next(entry.item for entry in entries if entry.item.due == "2026-10-30")
    store.set_task_state(october.ident or "", True, "Proyecto 1")
    store.set_task_state(october.ident or "", False, "Proyecto 1")
    store.move_item(october.ident or "", "Pendiente", "Proyecto 1", True)
    assert "- Nota manual\n" in project.read_text(encoding="utf-8")
    with pytest.raises(VaultError, match="Selector ambiguo"):
        store._select("Informe", "Proyecto 1", True)


def test_rename_updates_exact_wikilinks_without_plain_text(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {})
    store.create_project("Proyecto 1", "ERIC", [])
    general = root / "General.md"
    general.write_text(general.read_text(encoding="utf-8") + "Texto Proyecto 1 sin enlace\n", encoding="utf-8")
    store.rename_project("Proyecto 1", "Proyecto Nuevo")
    content = general.read_text(encoding="utf-8")
    assert "[[Proyecto Nuevo]]" in content
    assert "Texto Proyecto 1 sin enlace" in content
    store.rename_client("ERIC", "ERIC SA")
    assert "[[ERIC SA]]" in (root / "ORGM/Proyectos/Proyecto Nuevo.md").read_text(encoding="utf-8")


def test_summary_filters_and_empty_title(configured: tuple[Path, Vault]) -> None:
    _, store = configured
    store.create_client("ERIC", {})
    store.create_project("Proyecto 1", "ERIC", ["Correcciones"])
    store.add_task("Fechada", "Correcciones", "Proyecto 1", "2026-10-30")
    store.add_note("Manual", "Correcciones", "Proyecto 1")
    entries = store.summaries("Correcciones", None, False, False, date(2026, 10, 1), date(2026, 10, 31))
    assert [entry.text for entry in entries] == ["Fechada"]
    entries = store.summaries("Correcciones", None, False, True, date(2026, 10, 1), date(2026, 10, 31))
    assert {entry.text for entry in entries} == {"Fechada", "Manual"}
    assert store.summaries("Correcciones", None, False, False, date(2026, 12, 1), date(2026, 12, 31)) == []


def test_summary_includes_project_with_empty_requested_title(configured: tuple[Path, Vault]) -> None:
    _, store = configured
    store.create_client("ERIC", {})
    store.create_project("Farallon 42", "ERIC", ["Diseño de climatización"])
    entries = store.summaries("Diseño de climatización")
    assert [(entry.document, entry.text) for entry in entries] == [("Farallon 42", "")]


def test_cli_init_and_task_commands_use_isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert runner.invoke(app, ["init", "--vault", str(root)]).exit_code == 0
    assert runner.invoke(app, ["cliente", "crear", "ERIC"]).exit_code == 0
    assert runner.invoke(app, ["proyecto", "crear", "Proyecto 1", "--cliente", "ERIC", "--titulo", "Correcciones"]).exit_code == 0
    result = runner.invoke(app, ["tarea", "agregar", "Informe", "--proyecto", "Proyecto 1", "--titulo", "Correcciones", "--cada", "mes", "--desde", "2026-09-30", "--hasta", "2026-11-30"])
    assert result.exit_code == 0, result.output
    assert result.output.count("orgm-") == 3


def test_cli_normalizes_duplicate_client_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert runner.invoke(app, ["init", "--vault", str(root)]).exit_code == 0
    equal = runner.invoke(app, ["cliente", "crear", "ERIC", "--dato", "Correo=x", "--dato", " correo =x"])
    assert equal.exit_code == 0, equal.output
    assert (root / "ORGM/Clientes/ERIC.md").read_text(encoding="utf-8").count("| Correo | x |") == 1
    conflict = runner.invoke(app, ["cliente", "crear", "CONFLICTO", "--dato", "Correo=x", "--correo", "y"])
    assert conflict.exit_code == 1
    assert "Campo duplicado" in conflict.output
    assert not (root / "ORGM/Clientes/CONFLICTO.md").exists()



def test_cli_config_show_and_change_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = tmp_path / "primero", tmp_path / "segundo"
    (first / ".obsidian").mkdir(parents=True)
    (second / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert runner.invoke(app, ["init", "--vault", str(first)]).exit_code == 0
    shown = runner.invoke(app, ["config", "mostrar"])
    assert shown.exit_code == 0 and f"vault = {first}" in shown.output
    changed = runner.invoke(app, ["config", "vault", str(second)])
    assert changed.exit_code == 0, changed.output
    shown = runner.invoke(app, ["config", "mostrar"])
    assert shown.exit_code == 0 and f"vault = {second}" in shown.output

def test_numbered_preexisting_index_is_not_duplicated_and_is_removed(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {})
    general = root / "General.md"
    general.write_text("# General\n\n## [[ERIC]]\n\n1. [[Proyecto 1]]\n", encoding="utf-8")
    store.create_project("Proyecto 1", "ERIC", [])
    assert general.read_text(encoding="utf-8").count("[[Proyecto 1]]") == 1
    store.archive_project("Proyecto 1")
    assert "[[Proyecto 1]]" not in general.read_text(encoding="utf-8")




def test_project_index_accepts_bare_client_heading(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {})
    general = root / "General.md"
    general.write_text("# General\n\n## ERIC\n", encoding="utf-8")
    store.create_project("Proyecto 1", "ERIC", [])
    text = general.read_text(encoding="utf-8")
    assert text.count("## ERIC") == 1
    assert "- [[Proyecto 1]]" in text


def test_summary_includes_items_before_first_heading(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    (root / "General.md").write_text("# General\n\n- [ ] Sin título 📅 2026-10-30\n", encoding="utf-8")
    entries = store.summaries("General", start=date(2026, 10, 1), until=date(2026, 10, 31))
    assert [(entry.title, entry.text) for entry in entries] == [("General", "Sin título")]
def test_task_state_changes_only_checkbox_character_with_crlf(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    general = root / "General.md"
    original = "# General\r\n\r\n## Correcciones\r\n* [X]  rara   tarea 📅 2026-10-30 ^orgm-12345678\r\n"
    general.write_bytes(original.encode("utf-8"))
    store.set_task_state("orgm-12345678", False)
    expected = original.replace("[X]", "[ ]")
    assert general.read_bytes() == expected.encode("utf-8")


def test_data_table_supports_escaped_pipes_and_rejects_malformed_without_writing(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    store.create_client("ERIC", {"Empresa": "A|B"})
    path = root / "ORGM/Clientes/ERIC.md"
    store.update_client("ERIC", {"Teléfono": "809-555-0100"}, set())
    content = path.read_text(encoding="utf-8")
    assert "| Empresa | A\\|B |" in content
    assert "| Teléfono | 809-555-0100 |" in content
    path.write_text("# ERIC\n\n## Datos\n\n| Campo | Valor |\n| --- |\n| Empresa | A\\|B |\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(VaultError, match="Tabla mal formada"):
        store.update_client("ERIC", {"Teléfono": "809-555-0100"}, set())
    assert path.read_bytes() == before


def test_move_and_delete_include_indented_task_continuations(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    general = root / "General.md"
    general.write_text(
        "# General\n\n## Origen\n- [ ] Mover ^orgm-11111111\n  detalle manual\n\n  segundo detalle\n"
        "- [ ] Eliminar ^orgm-22222222\n    detalle eliminado\n\n    segundo eliminado\n"
        "- [ ] Conservar ^orgm-33333333\n\n## Destino\n",
        encoding="utf-8",
    )
    store.move_item("orgm-11111111", "Destino", task=True)
    moved = general.read_text(encoding="utf-8")
    assert "## Origen\n- [ ] Eliminar" in moved
    assert "## Destino\n- [ ] Mover ^orgm-11111111\n  detalle manual\n\n  segundo detalle\n" in moved
    store.delete_item("orgm-22222222", task=True)
    deleted = general.read_text(encoding="utf-8")
    assert "Eliminar" not in deleted
    assert "detalle eliminado" not in deleted
    assert "- [ ] Conservar ^orgm-33333333" in deleted


def test_updates_preserve_crlf_and_manual_spacing(configured: tuple[Path, Vault]) -> None:
    root, store = configured
    general = root / "General.md"
    original = (
        "# General\r\n\r\n## Correcciones\r\n"
        "*   nota vieja  ^orgm-11111111\r\n"
        "  + [X]   tarea vieja   📅   2026-10-30  ^orgm-22222222\r\n"
    )
    general.write_bytes(original.encode("utf-8"))
    store.update_note("orgm-11111111", "nota nueva")
    store.update_task("orgm-22222222", text="tarea nueva", due="2026-11-01")
    expected = (
        "# General\r\n\r\n## Correcciones\r\n"
        "*   nota nueva  ^orgm-11111111\r\n"
        "  + [X]   tarea nueva   📅   2026-11-01  ^orgm-22222222\r\n"
    )
    assert general.read_bytes() == expected.encode("utf-8")
