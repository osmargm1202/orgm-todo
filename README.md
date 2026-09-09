# orgm-todo

CLI para seguimiento ORGM directamente sobre un vault de Obsidian. Markdown es la única fuente de verdad: no usa base de datos, caché ni regeneración destructiva de notas.

## Installation

Requiere Python 3.13+ y [uv](https://docs.astral.sh/uv/).

Versión estable desde PyPI (disponible después de la primera publicación):

```sh
uv tool install orgm-todo
```

Actualizar:

```sh
uv tool upgrade orgm-todo
```

### Versión de desarrollo

Instalar directamente desde Git:

```sh
uv tool install git+https://github.com/osmargm1202/orgm-todo.git
```

Actualizar o reinstalar:

```sh
uv tool install --force git+https://github.com/osmargm1202/orgm-todo.git
```

## Quick start

Usa un vault de Obsidian existente, con su directorio `.obsidian/`:

```sh
orgm-todo init --vault /path/to/vault
orgm-todo menu
orgm-todo --help
```

Continúa con [clientes](#clients), [proyectos y títulos](#projects-and-titles),
[notas y tareas](#notes-and-tasks), [recurrencia](#recurrence) o [resumen](#summary).
Para cambiar el vault, consulta [configuración](#setup).

## Setup

```sh
orgm-todo init --vault /path/to/vault
orgm-todo config show
orgm-todo config set-vault /path/to/another-vault
```

`init` crea solo los elementos ausentes: `General.md`, directorios bajo `ORGM/` y el bloque administrado de `AGENTS.md`. Todo texto manual fuera de ese bloque se conserva. La configuración se guarda en `$XDG_CONFIG_HOME/orgm-todo/config.toml`.

## Vault model

- `General.md` es un índice manual de áreas, clientes y proyectos. Sus enlaces `[[...]]` **no** aparecen en `summary`.
- Cada proyecto activo vive en `ORGM/Proyectos/` y conserva notas, datos y tareas Markdown editables directamente en Obsidian.
- Solo una casilla pendiente `- [ ]` es una tarea visible en `summary`. Las notas y las casillas `- [x]` no aparecen allí.
- Archivar mueve el proyecto a `ORGM/Baul/Proyectos/` y oculta sus enlaces. Restaurar devuelve la nota íntegra y vuelve a indexarla bajo su cliente en `General.md` y en la nota del cliente.

El parser respeta BOM, LF/CRLF, frontmatter, fences Markdown, indentación, listas, IDs y valores de tabla escapados. Las mutaciones usan reemplazo atómico y detectan cambios concurrentes.

## Commands

Todos los comandos y opciones de la CLI están en inglés.

### Interactive menu

```sh
orgm-todo menu
```

El menú Questionary expone clientes, proyectos, títulos, notas, tareas, resumen y configuración. Cada operación solicita sus datos, muestra mensajes de resultado y vuelve al submenú desde el que se inició. `Esc` cancela el prompt actual y vuelve al menú anterior; `Exit` cierra la interfaz.

### Clients

```sh
orgm-todo client create ERIC --phone 809-555-0100 --data "Company=ORGM"
orgm-todo client list
orgm-todo client view ERIC
orgm-todo client update ERIC --data "Email=eric@example.com" --remove-data Phone
orgm-todo client rename ERIC "ERIC SA"
orgm-todo client archive "ERIC SA"
```

Opciones rápidas de creación: `--company`, `--contact`, `--phone`, `--email`, `--address`. `--data FIELD=VALUE` acepta campos adicionales.

### Projects and titles

```sh
orgm-todo project create "Project 1" --client ERIC --title Correcciones --title Compras
orgm-todo project list
orgm-todo project view "Project 1"
orgm-todo project update "Project 1" --status "On hold"
orgm-todo project update "Project 1" --client "Another client"
orgm-todo project rename "Project 1" "New project"
orgm-todo project archive "New project"
orgm-todo project restore "New project"

orgm-todo title add Correcciones --project "New project"
orgm-todo title rename Correcciones "HVAC corrections" --project "New project"
orgm-todo title delete "HVAC corrections" --project "New project" --force
```

### Notes and tasks

Sin `--project`, estos comandos operan sobre `General.md`; sin `--title`, usan `Pendiente`.

Las notas generales son compartidas y no pertenecen a ningún proyecto:

```sh
orgm-todo note add "Nota para todos"
orgm-todo note list
```

Guarda el ID `orgm-xxxxxxxx` devuelto por `note add`. La lista muestra
`General / Pendiente: Nota para todos`. Para borrarla, sustituye el ID del ejemplo
por el recibido:

```sh
orgm-todo note delete orgm-xxxxxxxx
```

En el menú, entra en `Notes` y selecciona `General` cuando se solicite el proyecto.
Para una nota ligada a un proyecto existente, usa `--project "Nombre"` al agregar,
listar o borrar. Ejemplos de operaciones sobre proyectos:

```sh
orgm-todo note add "Confirm quotation" --project "New project" --title Correcciones
orgm-todo note list --project "New project"
orgm-todo note update orgm-a1b2c3d4 --text "Confirm final quotation" --project "New project"
orgm-todo note move orgm-a1b2c3d4 --title Pendiente --project "New project"
orgm-todo note delete orgm-a1b2c3d4 --project "New project"

orgm-todo task add "Monthly report" --project "New project" --title Correcciones --date 2026-10-30
orgm-todo task list --project "New project"
orgm-todo task complete orgm-a1b2c3d4 --project "New project"
orgm-todo task pending orgm-a1b2c3d4 --project "New project"
orgm-todo task update orgm-a1b2c3d4 --text "Corrected report" --date 2026-11-01 --project "New project"
orgm-todo task update orgm-a1b2c3d4 --no-date --project "New project"
orgm-todo task move orgm-a1b2c3d4 --title Pendiente --project "New project"
orgm-todo task delete orgm-a1b2c3d4 --project "New project"
```

A selector resolves first as exact `orgm-xxxxxxxx` ID, then as a unique case-insensitive text substring. Ambiguous selectors make no changes.

### Recurrence

```sh
orgm-todo task add "Monthly report" --project "New project" --title Correcciones \
  --every month --from 2026-09-30 --to 2026-11-30
orgm-todo task add "Weekly meeting" --every week --from 2026-10-01 --to 2026-10-31
```

Each occurrence becomes an independent dated Markdown task with its own ID. `week` adds seven days; `month` retains the initial day and uses the final valid day of shorter months.

### Summary

```sh
orgm-todo summary
orgm-todo summary --title Correcciones
orgm-todo summary --project "New project" --week
orgm-todo summary --month 2026-10
orgm-todo summary --from 2026-10-01 --to 2026-10-31 --include-undated
```

`summary` scans active projects only. It groups pending tasks by title and project; completed tasks, notes, client files, archived projects and all `General.md` index links are excluded. Time ranges are inclusive; `--week` is Monday through Sunday in local time.

## Publicación manual (mantenedor)

Desde la raíz del repositorio:

```sh
uv build --no-sources --clear --force-pep517
uv publish --dry-run dist/*
```

`--force-pep517` obliga a uv 0.11.28 a usar el backend declarado
`uv_build>=0.12.5,<0.13.0`, en lugar de su backend rápido integrado. Se generan
el wheel y el archivo fuente de la versión `0.1.0` en `dist/`.
El modo `--dry-run` valida la publicación sin subir los artefactos.

Después de configurar `UV_PUBLISH_TOKEN` de forma segura **fuera del repositorio**:

```sh
uv publish dist/*
```

Esta preparación valida los artefactos, pero no publica la versión ni maneja
credenciales. Comprueba la disponibilidad y los permisos del nombre `orgm-todo`
en PyPI antes de publicar; un nombre disponible no queda reservado por el dry-run.

## Licencia

[PolyForm Noncommercial License 1.0.0](LICENSE)
(`PolyForm-Noncommercial-1.0.0`): licencia **source-available**, no open source
aprobada por OSI. Permite los fines no comerciales definidos en sus términos;
al redistribuir, deben propagarse los términos y el aviso de atribución
`Required Notice: Copyright 2026 osmar (https://github.com/osmargm1202).`

El texto de `LICENSE` rige los permisos y obligaciones. Incluye exclusión de
garantía y responsabilidad hasta donde permita la ley; no garantiza inmunidad
frente a reclamaciones ni gastos legales.
