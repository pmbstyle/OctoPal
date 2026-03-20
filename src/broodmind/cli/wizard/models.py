from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from broodmind.infrastructure.config.models import BroodMindConfig

T = TypeVar("T")


@dataclass(slots=True)
class WizardSelectOption(Generic[T]):
    value: T
    label: str
    hint: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class WizardSelectParams(Generic[T]):
    message: str
    options: Sequence[WizardSelectOption[T]]
    initial_value: T | None = None
    searchable: bool = False


@dataclass(slots=True)
class WizardMultiSelectParams(Generic[T]):
    message: str
    options: Sequence[WizardSelectOption[T]]
    initial_values: Sequence[T] = ()
    searchable: bool = False


@dataclass(slots=True)
class WizardTextParams:
    message: str
    initial_value: str | None = None
    placeholder: str | None = None
    secret: bool = False
    validate: Callable[[str], str | None] | None = None


@dataclass(slots=True)
class WizardConfirmParams:
    message: str
    initial_value: bool = True


RunSection = Callable[[BroodMindConfig], None]
RenderStatus = Callable[[BroodMindConfig], str | None]


@dataclass(slots=True)
class WizardSection:
    key: str
    title: str
    quick_enabled: bool = True
    render_status: RenderStatus | None = None
    run: RunSection | None = None
    help_lines: list[str] = field(default_factory=list)
