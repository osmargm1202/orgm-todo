"""Interactive Questionary interface for orgm-todo."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import questionary
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.table import Table

from .config import ConfigError, load_config, save_config
from .markdown import MarkdownError
from .vault import Entry, SummaryEntry, Vault, VaultError


class Prompter:
    """Questionary adapter; ``None`` consistently means Escape/back."""

    @staticmethod
    def _ask(prompt: object) -> object | None:
        application = prompt.application  # type: ignore[union-attr]

        @application.key_bindings.add(Keys.Escape)
        def cancel(event: object) -> None:
            event.app.exit(result=None)  # type: ignore[union-attr]

        try:
            return prompt.ask()  # type: ignore[union-attr]
        except (EOFError, KeyboardInterrupt):
            return None

    def select(self, message: str, choices: list[str]) -> str | None:
        return self._ask(questionary.select(message, choices=choices))  # type: ignore[return-value]

    def text(self, message: str, default: str = "") -> str | None:
        return self._ask(questionary.text(message, default=default))  # type: ignore[return-value]

    def confirm(self, message: str, default: bool = False) -> bool | None:
        return self._ask(questionary.confirm(message, default=default))  # type: ignore[return-value]


class Menu:
    def __init__(self, prompter: Prompter | None = None, console: Console | None = None):
        self.prompter = prompter or Prompter()
        self.console = console or Console()

    def vault(self) -> Vault:
        return Vault(load_config())

    def pause(self) -> None:
        self.prompter.text("Press Enter to return (Esc goes back)")

    def call(self, action: Callable[[], object], success: str | None = None) -> None:
        try:
            result = action()
            if success:
                self.console.print(f"[green]{success}[/green]")
            if isinstance(result, str) and result.startswith("orgm-"):
                self.console.print(result)
        except (ConfigError, MarkdownError, VaultError, ValueError) as exc:
            self.console.print(f"[red]{exc}[/red]")
        self.pause()

    def fields(self) -> dict[str, str] | None:
        result: dict[str, str] = {}
        while True:
            field = self.prompter.text("Data field (blank to finish)")
            if field is None:
                return None
            if not field:
                return result
            value = self.prompter.text(f"Value for {field}")
            if value is None:
                return None
            result[field] = value

    def project_name(self, allow_general: bool = False) -> str | None:
        try:
            choices = self.vault().list_projects()
        except ConfigError as exc:
            self.console.print(f"[red]{exc}[/red]")
            return None
        if allow_general:
            choices.insert(0, "General")
        choices.append("Type a project name…")
        choice = self.prompter.select("Project", choices)
        if choice is None:
            return None
        if choice == "General":
            return ""
        if choice == "Type a project name…":
            return self.prompter.text("Project name")
        return choice

    def show_entries(self, entries: list[Entry]) -> None:
        table = Table(title="Entries")
        table.add_column("Project")
        table.add_column("Title")
        table.add_column("Entry")
        for entry in entries:
            state = "[ ] " if entry.item.checked is False else "[x] " if entry.item.checked else ""
            due = f" 📅 {entry.item.due}" if entry.item.due else ""
            ident = f" ^{entry.item.ident}" if entry.item.ident else ""
            table.add_row(entry.document, entry.title, f"{state}{entry.item.text}{due}{ident}")
        self.console.print(table)

    def client_menu(self) -> None:
        while (choice := self.prompter.select("Clients", ["Create", "List", "View", "Update", "Rename", "Archive", "Back"])) not in {None, "Back"}:
            if choice == "List":
                self.call(lambda: self.console.print("\n".join(self.vault().list_clients()) or "No active clients"))
            elif choice == "Create":
                name = self.prompter.text("Client name")
                fields = self.fields() if name is not None else None
                if name and fields is not None:
                    self.call(lambda: self.vault().create_client(name, fields), "Client created")
            elif choice == "View":
                name = self.prompter.text("Client name")
                if name:
                    self.call(lambda: self.console.print(self.vault()._named_file("clients", name).read_text(encoding="utf-8")))
            elif choice == "Update":
                name = self.prompter.text("Client name")
                fields = self.fields() if name else None
                if name and fields is not None:
                    self.call(lambda: self.vault().update_client(name, fields, set()), "Client updated")
            elif choice == "Rename":
                old, new = self.prompter.text("Current name"), self.prompter.text("New name")
                if old and new:
                    self.call(lambda: self.vault().rename_client(old, new), "Client renamed")
            elif choice == "Archive":
                name = self.prompter.text("Client name")
                if name and self.prompter.confirm(f"Archive {name}?"):
                    self.call(lambda: self.vault().archive_client(name), "Client archived")

    def project_menu(self) -> None:
        while (choice := self.prompter.select("Projects", ["Create", "List", "View", "Update", "Rename", "Archive", "Restore", "Back"])) not in {None, "Back"}:
            if choice == "List":
                self.call(lambda: self.console.print("\n".join(self.vault().list_projects()) or "No active projects"))
            elif choice == "Create":
                name, client = self.prompter.text("Project name"), self.prompter.text("Client")
                titles = self.titles() if name and client else None
                if name and client and titles is not None:
                    self.call(lambda: self.vault().create_project(name, client, titles), "Project created")
            elif choice == "View":
                name = self.project_name()
                if name:
                    self.call(lambda: self.console.print(self.vault()._named_file("projects", name).read_text(encoding="utf-8")))
            elif choice == "Update":
                name = self.project_name()
                if name:
                    client = self.prompter.text("New client (blank to keep)")
                    status = self.prompter.text("New status (blank to keep)")
                    self.call(lambda: self.vault().update_project(name, client or None, status or None), "Project updated")
            elif choice == "Rename":
                name, new = self.project_name(), self.prompter.text("New project name")
                if name and new:
                    self.call(lambda: self.vault().rename_project(name, new), "Project renamed")
            elif choice == "Archive":
                name = self.project_name()
                if name and self.prompter.confirm(f"Archive {name}?"):
                    self.call(lambda: self.vault().archive_project(name), "Project archived")
            elif choice == "Restore":
                archived = self.vault().list_projects(archived=True)
                name = self.prompter.select("Archived project", archived + ["Back"])
                if name and name != "Back":
                    self.call(lambda: self.vault().restore_project(name), "Project restored")

    def titles(self) -> list[str] | None:
        values: list[str] = []
        while True:
            title = self.prompter.text("Title (blank to finish)")
            if title is None:
                return None
            if not title:
                return values
            values.append(title)

    def title_menu(self) -> None:
        while (choice := self.prompter.select("Titles", ["Add", "Rename", "Delete", "Back"])) not in {None, "Back"}:
            selected = self.project_name(allow_general=True)
            if selected is None:
                continue
            project = selected or None
            if choice == "Add":
                title = self.prompter.text("Title")
                if title:
                    self.call(lambda: self.vault().add_title(title, project), "Title added")
            elif choice == "Rename":
                old, new = self.prompter.text("Current title"), self.prompter.text("New title")
                if old and new:
                    self.call(lambda: self.vault().rename_title(old, new, project), "Title renamed")
            elif choice == "Delete":
                title = self.prompter.text("Title")
                if title and self.prompter.confirm(f"Force delete {title}?"):
                    self.call(lambda: self.vault().delete_title(title, project, True), "Title deleted")

    def note_menu(self) -> None:
        while (choice := self.prompter.select("Notes", ["Add", "List", "Update", "Move", "Delete", "Back"])) not in {None, "Back"}:
            selected = self.project_name(allow_general=True)
            if selected is None:
                continue
            project = selected or None
            if choice == "List":
                self.call(lambda: self.show_entries(self.vault().list_entries(project, False)))
            elif choice == "Add":
                text, title = self.prompter.text("Note"), self.prompter.text("Title", default="Pendiente")
                if text and title:
                    self.call(lambda: self.vault().add_note(text, title, project), "Note added")
            elif choice == "Update":
                selector, text = self.prompter.text("Note ID or text"), self.prompter.text("New text")
                if selector and text:
                    self.call(lambda: self.vault().update_note(selector, text, project), "Note updated")
            elif choice == "Move":
                selector, title = self.prompter.text("Note ID or text"), self.prompter.text("Destination title")
                if selector and title:
                    self.call(lambda: self.vault().move_item(selector, title, project, False), "Note moved")
            elif choice == "Delete":
                selector = self.prompter.text("Note ID or text")
                if selector and self.prompter.confirm("Delete this note?"):
                    self.call(lambda: self.vault().delete_item(selector, project, False), "Note deleted")

    def task_menu(self) -> None:
        while (choice := self.prompter.select("Tasks", ["Add", "List", "Complete", "Pending", "Update", "Move", "Delete", "Back"])) not in {None, "Back"}:
            selected = self.project_name(allow_general=True)
            if selected is None:
                continue
            project = selected or None
            if choice == "List":
                self.call(lambda: self.show_entries(self.vault().list_entries(project, True)))
            elif choice == "Add":
                text, title = self.prompter.text("Task"), self.prompter.text("Title", default="Pendiente")
                if text and title:
                    every = self.prompter.select("Repeat", ["None", "week", "month"])
                    if every is None:
                        continue
                    if every == "None":
                        due = self.prompter.text("Date YYYY-MM-DD (blank for none)")
                        self.call(lambda: self.vault().add_task(text, title, project, due or None), "Task added")
                    else:
                        start, end = self.prompter.text("From YYYY-MM-DD"), self.prompter.text("To YYYY-MM-DD")
                        if start and end:
                            self.call(lambda: self.vault().recurring_tasks(text, every, date.fromisoformat(start), date.fromisoformat(end), title, project), "Tasks added")
            elif choice in {"Complete", "Pending"}:
                selector = self.prompter.text("Task ID or text")
                if selector:
                    self.call(lambda: self.vault().set_task_state(selector, choice == "Complete", project), f"Task marked {choice.lower()}")
            elif choice == "Update":
                selector = self.prompter.text("Task ID or text")
                text = self.prompter.text("New text (blank to keep)")
                due = self.prompter.text("New date YYYY-MM-DD ('-' to remove; blank to keep)")
                if selector:
                    due_value: str | None | object = None if due == "-" else due if due else ...
                    self.call(lambda: self.vault().update_task(selector, project, text or None, due_value), "Task updated")
            elif choice == "Move":
                selector, title = self.prompter.text("Task ID or text"), self.prompter.text("Destination title")
                if selector and title:
                    self.call(lambda: self.vault().move_item(selector, title, project, True), "Task moved")
            elif choice == "Delete":
                selector = self.prompter.text("Task ID or text")
                if selector and self.prompter.confirm("Delete this task?"):
                    self.call(lambda: self.vault().delete_item(selector, project, True), "Task deleted")

    def summary(self) -> None:
        title = self.prompter.text("Title filter (blank for all)")
        selected = self.project_name(allow_general=True)
        if title is None or selected is None:
            return
        project = selected or None
        period = self.prompter.select("Time filter", ["All", "Today", "This week", "Month", "Range"])
        if period is None:
            return
        start = until = None
        if period == "Today":
            start = until = date.today()
        elif period == "This week":
            start = date.today() - timedelta(days=date.today().weekday())
            until = start + timedelta(days=6)
        elif period == "Month":
            value = self.prompter.text("Month YYYY-MM")
            if not value:
                return
            start = date.fromisoformat(f"{value}-01")
            until = date(start.year, start.month + 1, 1) - timedelta(days=1) if start.month < 12 else date(start.year, 12, 31)
        elif period == "Range":
            first, last = self.prompter.text("From YYYY-MM-DD"), self.prompter.text("To YYYY-MM-DD")
            if not first or not last:
                return
            start, until = date.fromisoformat(first), date.fromisoformat(last)
        include_undated = self.prompter.confirm("Include undated tasks?", default=False)
        if include_undated is None:
            return
        try:
            entries = self.vault().summaries(title or None, project, include_undated, start, until)
            self.console.print("No pending tasks for this filter" if not entries else "")
            for entry in entries:
                self.console.print(f"{entry.title} / {entry.document}: [ ] {entry.text}" if entry.text else f"{entry.title} / {entry.document}: no pending tasks")
        except (ConfigError, MarkdownError, VaultError, ValueError) as exc:
            self.console.print(f"[red]{exc}[/red]")
        self.pause()

    def config_menu(self) -> None:
        while (choice := self.prompter.select("Configuration", ["Show", "Set vault", "Back"])) not in {None, "Back"}:
            if choice == "Show":
                self.call(lambda: self.console.print(f"vault = {load_config().vault}"))
            elif choice == "Set vault":
                path = self.prompter.text("Vault path")
                if path:
                    self.call(lambda: save_config(path), "Vault configured")

    def run(self) -> None:
        actions: dict[str, Callable[[], None]] = {
            "Clients": self.client_menu,
            "Projects": self.project_menu,
            "Titles": self.title_menu,
            "Notes": self.note_menu,
            "Tasks": self.task_menu,
            "Summary": self.summary,
            "Configuration": self.config_menu,
        }
        while (choice := self.prompter.select("orgm-todo", [*actions, "Exit"])) not in {None, "Exit"}:
            actions[choice]()


def run_interactive() -> None:
    Menu().run()
