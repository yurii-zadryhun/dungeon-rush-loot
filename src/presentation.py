from __future__ import annotations

import time

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import EXCEPTIONAL_SKILLS
from .domain import Action, Comparison, ComparisonStatus


class ComparisonFormatter:
    @staticmethod
    def summary(comparison: Comparison, verbose: bool) -> str:
        title = ComparisonFormatter.title(comparison)
        style = ComparisonFormatter.style(comparison)

        summary = Text(title, style=f"bold {style}")

        if verbose:
            return Text.assemble(summary, Text(f' · {comparison.message}', style="yellow"))

        return summary

    @staticmethod
    def title(comparison: Comparison) -> str:
        if comparison.status is not ComparisonStatus.OK:
            return "🟡 CHECK OCR"

        if comparison.rejected:
            return "🔴 SELL · REJECTED"

        if comparison.equipped_score is None or comparison.candidate_score is None:
            return "🔴 SELL?" if comparison.action is Action.SELL else "🟢 EQUIP?"

        equipped, candidate = round(comparison.equipped_score.total), round(comparison.candidate_score.total)

        if comparison.action is Action.EQUIP:
            return f"🟢 EQUIP ({equipped} < {candidate})"

        return f"🔴 SELL ({equipped} > {candidate})" if equipped != candidate else f"🔴 SELL ({equipped} ≥ {candidate})"

    @staticmethod
    def style(comparison: Comparison) -> str:
        if comparison.status is not ComparisonStatus.OK:
            return 'yellow'
        if comparison.action is Action.EQUIP:
            return 'bright_green'
        return 'bright_red'


class ConsolePresenter:
    def __init__(self, verbose: bool = False, console: Console | None = None) -> None:
        self.verbose = verbose
        self.console = console or Console()

    def result(self, comparison: Comparison) -> None:
        summary = ComparisonFormatter.summary(comparison, self.verbose or comparison.status is not ComparisonStatus.OK)
        scoresAvailable = comparison.equipped_score and comparison.candidate_score

        self.newLine()
        self._print(summary)
        if scoresAvailable: self._score_table(comparison)
        self.newLine()

    def newLine(self) -> None:
        self.console.print()

    def foreground(self, active: bool) -> None:
        message = "OCR resumed" if active else "OCR paused"
        self._print(f"[dim]{message}[/dim]")

    def warning(self, message: str) -> None:
        self._print(f"[yellow]{message}[/yellow]")

    def debug(self, message: str) -> None:
        self._print(f'[dim]{message}[/dim]')

    def _print(self, renderable: str | Text) -> None:
        timestamp = time.strftime("%H:%M:%S")
        if isinstance(renderable, Text):
            self.console.print(Text.assemble((f"[{timestamp}] ", "dim"), renderable))
        else:
            self.console.print(f"[dim][{timestamp}][/dim] {renderable}")

    def _score_table(self, comparison: Comparison) -> None:
        equipped, candidate = comparison.equipped_score, comparison.candidate_score
        eq_meta = f" {comparison.equipped.rarity}, Lv{comparison.equipped.level}" if comparison.equipped and comparison.equipped.rarity and comparison.equipped.level is not None else ""
        cand_meta = f" {comparison.candidate.rarity}, Lv{comparison.candidate.level}" if comparison.candidate and comparison.candidate.rarity and comparison.candidate.level is not None else ""
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold", padding=(0, 2))
        table.add_column(f"EQUIPPED{eq_meta} {equipped.total:.1f}  [base {equipped.base_power:+.1f}]", width=48, no_wrap=True)
        table.add_column(f"CANDIDATE{cand_meta} {candidate.total:.1f}  [base {candidate.base_power:+.1f}]", width=48, no_wrap=True)
        rows = max(len(equipped.details), len(candidate.details))
        for index in range(rows):
            left = self._affix(equipped.details[index]) if index < len(equipped.details) else Text("")
            right = self._affix(candidate.details[index]) if index < len(candidate.details) else Text("")
            table.add_row(left, right)
        self.console.print(table)

    @staticmethod
    def _affix(affix) -> Text:
        line = Text()
        line.append(f"{affix.value:+.2f}%  ", style="cyan")
        line.append(f"{affix.name:<24}", style="orange3" if affix.name.lower() in EXCEPTIONAL_SKILLS else "white")
        line.append(f"{round(affix.contribution):+d}", style="dim")
        return line
