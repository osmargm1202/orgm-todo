# orgm-todo

CLI de seguimiento ORGM sobre un vault de Obsidian. Los archivos Markdown son la única fuente de verdad: no usa base de datos, caché ni regeneración de notas. Las ediciones hechas directamente en Obsidian siguen siendo válidas.

## Instalación

```sh
rtk uv tool install git+https://github.com/osmargm1202/orgm-todo.git
```

Actualizar:

```sh
rtk uv tool install --force git+https://github.com/osmargm1202/orgm-todo.git
```

Desinstalar:

```sh
rtk uv tool uninstall orgm-todo
```

## Configuración

Inicialice el vault una vez. Solo crea elementos ausentes y conserva todo el contenido existente:

```sh
orgm-todo init --vault /ruta/al/vault
```

La ruta se guarda en `$XDG_CONFIG_HOME/orgm-todo/config.toml` (o `~/.config/orgm-todo/config.toml`). Si se omite `--vault`, `init` busca la ruta configurada, el directorio actual si tiene `.obsidian/`, o el único vault abierto de Obsidian.

La estructura administrada es:

```text
General.md
ORGM/Clientes/
ORGM/Proyectos/
ORGM/Baul/Clientes/
ORGM/Baul/Proyectos/
AGENTS.md
```

`AGENTS.md` conserva cualquier texto manual fuera de su bloque `orgm-todo`. `.trash/` nunca se toca.

```sh
orgm-todo config mostrar
orgm-todo config vault /ruta/otro-vault
```

## Markdown compatible

Use encabezados ATX, viñetas y casillas normales:

```md
## Correcciones
- Nota manual
- [ ] Revisar plano 📅 2026-10-30
```

El CLI reconoce `-`, `*`, `+` y listas numeradas; casillas `[ ]`, `[x]` y `[X]`; fechas `📅 YYYY-MM-DD`; enlaces `[[Nota]]`; y tablas pipe. Mantiene saltos de línea, BOM, indentación y contenido desconocido. Al crear o modificar una entrada añade un identificador estable `^orgm-xxxxxxxx`. Las entradas manuales sin ID siguen apareciendo en listas y resúmenes.

## Clientes y proyectos

```sh
orgm-todo cliente crear ERIC --telefono 809-555-0100 --dato "Empresa=ORGM"
orgm-todo cliente listar
orgm-todo cliente ver ERIC
orgm-todo cliente actualizar ERIC --dato "Correo=eric@example.com" --quitar-dato Teléfono
orgm-todo cliente renombrar ERIC "ERIC SA"
orgm-todo cliente archivar "ERIC SA"

orgm-todo proyecto crear "Proyecto 1" --cliente "ERIC SA" --titulo Correcciones --titulo Compras
orgm-todo proyecto listar
orgm-todo proyecto ver "Proyecto 1"
orgm-todo proyecto actualizar "Proyecto 1" --estado En pausa
orgm-todo proyecto actualizar "Proyecto 1" --cliente "Otro cliente"
orgm-todo proyecto renombrar "Proyecto 1" "Proyecto nuevo"
orgm-todo proyecto archivar "Proyecto nuevo"
orgm-todo proyecto restaurar "Proyecto nuevo"
```

Al crear, restaurar, cambiar de cliente o renombrar, se actualizan únicamente los wikilinks exactos de `General.md` y las notas de cliente. Un cliente con proyectos activos no se puede archivar.

## Títulos, notas y tareas

Sin `--proyecto`, estos comandos operan **solo** en `General.md`. Sin `--titulo`, crean/usan `Pendiente`.

```sh
orgm-todo titulo agregar Correcciones --proyecto "Proyecto nuevo"
orgm-todo titulo renombrar Correcciones "Correcciones HVAC" --proyecto "Proyecto nuevo"
orgm-todo titulo eliminar "Correcciones HVAC" --proyecto "Proyecto nuevo" --force

orgm-todo nota agregar "Confirmar cotización" --titulo Correcciones --proyecto "Proyecto nuevo"
orgm-todo nota listar --proyecto "Proyecto nuevo"
orgm-todo nota actualizar orgm-a1b2c3d4 --texto "Confirmar cotización final" --proyecto "Proyecto nuevo"
orgm-todo nota mover orgm-a1b2c3d4 --titulo Pendiente --proyecto "Proyecto nuevo"
orgm-todo nota eliminar orgm-a1b2c3d4 --proyecto "Proyecto nuevo"

orgm-todo tarea agregar "Informe mensual" --titulo Correcciones --proyecto "Proyecto nuevo" --fecha 2026-10-30
orgm-todo tarea listar --proyecto "Proyecto nuevo"
orgm-todo tarea completar orgm-a1b2c3d4 --proyecto "Proyecto nuevo"
orgm-todo tarea pendiente orgm-a1b2c3d4 --proyecto "Proyecto nuevo"
orgm-todo tarea actualizar orgm-a1b2c3d4 --texto "Informe corregido" --fecha 2026-11-01 --proyecto "Proyecto nuevo"
orgm-todo tarea actualizar orgm-a1b2c3d4 --sin-fecha --proyecto "Proyecto nuevo"
orgm-todo tarea mover orgm-a1b2c3d4 --titulo Pendiente --proyecto "Proyecto nuevo"
orgm-todo tarea eliminar orgm-a1b2c3d4 --proyecto "Proyecto nuevo"
```

Un selector se resuelve primero como ID exacto y después como subcadena única, sin distinguir mayúsculas. Ante una coincidencia ambigua no modifica el archivo e informa candidatos.

### Recurrencia visible

Cada ocurrencia se materializa como una casilla Markdown con fecha e ID propios. No hay reglas ocultas:

```sh
orgm-todo tarea agregar "Informe mensual" --proyecto "Proyecto nuevo" --titulo Correcciones \
  --cada mes --desde 2026-09-30 --hasta 2026-11-30
orgm-todo tarea agregar "Reunión semanal" --cada semana --desde 2026-10-01 --hasta 2026-10-31
```

`semana` suma siete días. `mes` conserva el día inicial y usa el último día disponible en meses más cortos.

## Resúmenes

```sh
orgm-todo resumen --titulo Correcciones
orgm-todo resumen --titulo Correcciones --semana
orgm-todo resumen --titulo Correcciones --mes 2026-10
orgm-todo resumen --desde 2026-10-01 --hasta 2026-10-31
orgm-todo resumen --proyecto "Proyecto nuevo" --incluir-hechas --incluir-sin-fecha
```

Los filtros temporales son inclusivos. `--semana` significa lunes a domingo local. Las tareas hechas se excluyen por defecto; las notas y tareas sin fecha entran en filtros temporales solo con `--incluir-sin-fecha`. Los resúmenes ignoran clientes, baúles, `.trash/` y `.obsidian/`.
