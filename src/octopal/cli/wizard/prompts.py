from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from octopal.cli.wizard.models import (
    WizardConfirmParams,
    WizardMultiSelectParams,
    WizardSelectOption,
    WizardSelectParams,
    WizardTextParams,
)

OCTO_SILVER = "#6aafae"
OCTO_BLUE = "#0f4e5d"
OCTO_WHITE = "#ebebeb"
SURFACE_BLUE = "#5fa8c8"


class WizardPrompter:
    def intro(self, title: str, body: str | None = None) -> None:
        raise NotImplementedError

    def note(self, title: str, lines: Sequence[str]) -> None:
        raise NotImplementedError

    def select[T](self, params: WizardSelectParams[T]) -> T:
        raise NotImplementedError

    def multiselect[T](self, params: WizardMultiSelectParams[T]) -> list[T]:
        raise NotImplementedError

    def text(self, params: WizardTextParams) -> str:
        raise NotImplementedError

    def confirm(self, params: WizardConfirmParams) -> bool:
        raise NotImplementedError


@dataclass(slots=True)
class RichWizardPrompter(WizardPrompter):
    console: Console
    accent: str = OCTO_WHITE
    surface: str = SURFACE_BLUE

    def intro(self, title: str, body: str | None = None) -> None:
        rendered = title if not body else f"{title}\n{body}"
        self.console.print(
            Panel(
                rendered,
                border_style=self.surface,
                padding=(1, 2),
            )
        )
        self.console.print()

    def note(self, title: str, lines: Sequence[str]) -> None:
        self.console.print()
        self.console.print(
            Panel(
                "\n".join(lines),
                title=f"[bold]{title}[/bold]",
                border_style=self.surface,
                padding=(1, 2),
            )
        )
        self.console.print()

    def select[T](self, params: WizardSelectParams[T]) -> T:
        try:
            return _inquirer_select(params)
        except Exception:
            return self._fallback_select(params)

    def multiselect[T](self, params: WizardMultiSelectParams[T]) -> list[T]:
        try:
            return _inquirer_multiselect(params)
        except Exception:
            return self._fallback_multiselect(params)

    def text(self, params: WizardTextParams) -> str:
        try:
            return _inquirer_text(params)
        except Exception:
            return self._fallback_text(params)

    def confirm(self, params: WizardConfirmParams) -> bool:
        try:
            return _inquirer_confirm(params)
        except Exception:
            return Confirm.ask(params.message, default=params.initial_value)

    def _fallback_select[T](self, params: WizardSelectParams[T]) -> T:
        visible_options = [option for option in params.options if option.enabled]
        for index, option in enumerate(visible_options, start=1):
            hint = f" [dim]- {option.hint}[/dim]" if option.hint else ""
            self.console.print(f"  {index}. {option.label}{hint}")

        default_index = 1
        if params.initial_value is not None:
            for index, option in enumerate(visible_options, start=1):
                if option.value == params.initial_value:
                    default_index = index
                    break

        selected_idx = IntPrompt.ask(
            params.message,
            choices=[str(i) for i in range(1, len(visible_options) + 1)],
            default=default_index,
        )
        return visible_options[selected_idx - 1].value

    def _fallback_multiselect[T](self, params: WizardMultiSelectParams[T]) -> list[T]:
        self.console.print(f"[bold]{params.message}[/bold]")
        self.console.print("[dim]Enter comma-separated numbers. Leave blank for none.[/dim]")
        visible_options = [option for option in params.options if option.enabled]
        initial_values = set(params.initial_values)

        default_indices: list[str] = []
        for index, option in enumerate(visible_options, start=1):
            selected = option.value in initial_values
            marker = "[green]x[/green]" if selected else " "
            hint = f" [dim]- {option.hint}[/dim]" if option.hint else ""
            self.console.print(f"  [{marker}] {index}. {option.label}{hint}")
            if selected:
                default_indices.append(str(index))

        raw = Prompt.ask("Selections", default=",".join(default_indices))
        if not raw.strip():
            return []

        selected: list[T] = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            index = int(chunk)
            selected.append(visible_options[index - 1].value)
        return selected

    def _fallback_text(self, params: WizardTextParams) -> str:
        return Prompt.ask(
            params.message,
            default=params.initial_value,
            password=params.secret,
        )


def _choice_name[T](option: WizardSelectOption[T]) -> str:
    return f"{option.label} - {option.hint}" if option.hint else option.label


def _inquirer_select[T](params: WizardSelectParams[T]) -> T:
    from InquirerPy import inquirer

    choices = [
        {
            "name": _choice_name(option),
            "value": option.value,
            "enabled": option.value == params.initial_value,
        }
        for option in params.options
        if option.enabled
    ]
    prompt = inquirer.fuzzy if params.searchable else inquirer.select
    return prompt(
        message=f"{params.message}:",
        choices=choices,
        default=params.initial_value,
    ).execute()


def _inquirer_multiselect[T](params: WizardMultiSelectParams[T]) -> list[T]:
    from InquirerPy import inquirer

    choices = [
        {
            "name": _choice_name(option),
            "value": option.value,
            "enabled": option.value in set(params.initial_values),
        }
        for option in params.options
        if option.enabled
    ]
    if params.searchable:
        result = inquirer.checkbox(
            message=f"{params.message}:",
            choices=choices,
            instruction="Space to toggle, arrows to move, enter to confirm, type to filter.",
        ).execute()
        return list(result)

    result = inquirer.checkbox(
        message=f"{params.message}:",
        choices=choices,
        instruction="Space to toggle, arrows to move, enter to confirm.",
    ).execute()
    return list(result)


def _inquirer_text(params: WizardTextParams) -> str:
    from InquirerPy import inquirer

    prompt = inquirer.secret if params.secret else inquirer.text
    return prompt(
        message=f"{params.message}:",
        default=params.initial_value,
        validate=(lambda value: params.validate(value) is None) if params.validate else None,
        invalid_message=(
            params.validate(params.initial_value or "")
            if params.validate and params.initial_value
            else "Invalid value"
        ),
    ).execute()


def _inquirer_confirm(params: WizardConfirmParams) -> bool:
    from InquirerPy import inquirer

    return inquirer.confirm(
        message=f"{params.message}:",
        default=params.initial_value,
    ).execute()


def create_wizard_prompter(console: Console | None = None) -> WizardPrompter:
    return RichWizardPrompter(console=console or Console())
