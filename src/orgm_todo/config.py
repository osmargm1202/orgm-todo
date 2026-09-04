"""Configuración y inicialización no destructiva de vaults Obsidian."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIRNAME = "orgm-todo"
CONFIG_FILENAME = "config.toml"
DEFAULTS = {
    "general": "General.md",
    "clients": "ORGM/Clientes",
    "projects": "ORGM/Proyectos",
    "archive_projects": "ORGM/Baul/Proyectos",
    "archive_clients": "ORGM/Baul/Clientes",
}
MANAGED_START = "<!-- orgm-todo:start -->"
MANAGED_END = "<!-- orgm-todo:end -->"
MANAGED_AGENTS = """<!-- orgm-todo:start -->
# orgm-todo

- Use únicamente la estructura activa de este vault; ignore `.trash/`.
- Conserve contenido desconocido y edite el intervalo mínimo necesario.
- Use enlaces `[[Nota]]`, encabezados Markdown, viñetas `-`, casillas `- [ ]`/`- [x]`, tablas de datos y fechas `📅 YYYY-MM-DD`.
- Archive proyectos terminados en `ORGM/Baul/Proyectos/`.
<!-- orgm-todo:end -->
"""


class ConfigError(ValueError):
    """Una configuración o vault no es utilizable."""


@dataclass(frozen=True)
class VaultConfig:
    vault: Path
    general: str = DEFAULTS["general"]
    clients: str = DEFAULTS["clients"]
    projects: str = DEFAULTS["projects"]
    archive_projects: str = DEFAULTS["archive_projects"]
    archive_clients: str = DEFAULTS["archive_clients"]

    @property
    def general_path(self) -> Path:
        return self.vault / self.general

    def path(self, key: str) -> Path:
        return self.vault / getattr(self, key)


def config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / CONFIG_DIRNAME / CONFIG_FILENAME


def validate_vault(vault: str | Path) -> Path:
    path = Path(vault).expanduser().resolve()
    if not path.is_dir():
        raise ConfigError(f"El vault no es un directorio: {path}")
    if not (path / ".obsidian").is_dir():
        raise ConfigError(f"No se encontró .obsidian/ en: {path}")
    return path


def _saved_vault() -> Path | None:
    path = config_path()
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return validate_vault(data["vault"])
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, ConfigError):
        return None


def _open_obsidian_vaults() -> list[Path]:
    path = Path.home() / ".config/obsidian/obsidian.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    vaults = data.get("vaults", {}) if isinstance(data, dict) else {}
    result: list[Path] = []
    if isinstance(vaults, dict):
        for item in vaults.values():
            if isinstance(item, dict) and item.get("open") and isinstance(item.get("path"), str):
                try:
                    result.append(validate_vault(item["path"]))
                except ConfigError:
                    pass
    return result


def resolve_vault(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return validate_vault(explicit)
    saved = _saved_vault()
    if saved is not None:
        return saved
    current = Path.cwd()
    if (current / ".obsidian").is_dir():
        return validate_vault(current)
    candidates = _open_obsidian_vaults()
    if len(candidates) == 1:
        return candidates[0]
    raise ConfigError("No hay un vault configurado de forma única; use --vault PATH.")


def save_config(vault: str | Path) -> VaultConfig:
    root = validate_vault(vault)
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join([f'vault = "{root}"', *(f'{key} = "{value}"' for key, value in DEFAULTS.items())]) + "\n"
    target.write_text(text, encoding="utf-8")
    return VaultConfig(root)


def load_config() -> VaultConfig:
    path = config_path()
    if not path.is_file():
        raise ConfigError("No hay configuración; ejecute `orgm-todo init --vault PATH`.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        root = validate_vault(data["vault"])
        values = {key: str(data.get(key, default)) for key, default in DEFAULTS.items()}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, ConfigError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"Configuración inválida: {path}") from exc
    return VaultConfig(root, **values)


def _update_agents(path: Path) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    start, end = old.find(MANAGED_START), old.find(MANAGED_END)
    if start != -1 and end != -1 and end >= start:
        end += len(MANAGED_END)
        new = old[:start] + MANAGED_AGENTS.rstrip("\n") + old[end:]
    elif start != -1 or end != -1:
        raise ConfigError(f"Bloque administrado ambiguo en {path}")
    elif old:
        newline = "\r\n" if "\r\n" in old else "\n"
        new = old + newline * 2 + MANAGED_AGENTS
    else:
        new = MANAGED_AGENTS
    if new != old:
        path.write_text(new, encoding="utf-8")


def initialize(vault: str | Path | None = None) -> VaultConfig:
    root = resolve_vault(vault)
    config = save_config(root)
    for relative in (config.clients, config.projects, config.archive_projects, config.archive_clients):
        (root / relative).mkdir(parents=True, exist_ok=True)
    general = config.general_path
    if not general.exists():
        general.write_text("# General\n\n## Pendiente\n", encoding="utf-8")
    _update_agents(root / "AGENTS.md")
    return config
