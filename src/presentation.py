from __future__ import annotations

import time

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import EXCEPTIONAL_SKILLS
from .domain import Action, BuildScore, Comparison, ComparisonStatus, ParsedStat
from .equipment import beneficial_value
from .events import score_delta_payload
from .text import canonical_name


class ComparisonFormatter:
    @staticmethod
    def summary(comparison: Comparison, verbose: bool) -> str | Text:
        title = ComparisonFormatter.title(comparison)
        style = ComparisonFormatter.style(comparison)
        summary = Text(title, style=f"bold {style}")
        if verbose:
            return Text.assemble(summary, Text(f" · {comparison.message}", style="yellow"))
        return summary

    @staticmethod
    def title(comparison: Comparison) -> str:
        if comparison.status is not ComparisonStatus.OK:
            return "🟡 CHECK OCR"
        if comparison.rejection_reason == "fast_exceptional":
            return "🔴 SELL · FAST EXCEPTIONAL (<90%)"
        if comparison.rejected:
            return "🔴 SELL · REJECTED"
        if comparison.equipped_score is None or comparison.candidate_score is None:
            return "🔴 SELL?" if comparison.action is Action.SELL else "🟢 EQUIP?"

        equipped = round(comparison.equipped_score.total)
        candidate = round(comparison.candidate_score.total)
        if comparison.action is Action.EQUIP:
            if candidate < equipped:
                return f"🟢 EQUIP · OPPORTUNITY ({equipped} > {candidate} now)"
            return f"🟢 EQUIP ({equipped} < {candidate})"
        return f"🔴 SELL ({equipped} > {candidate})" if equipped != candidate else f"🔴 SELL ({equipped} ≥ {candidate})"

    @staticmethod
    def style(comparison: Comparison) -> str:
        if comparison.status is not ComparisonStatus.OK:
            return "yellow"
        if comparison.action is Action.EQUIP:
            return "bright_green"
        return "bright_red"


class ConsolePresenter:
    def __init__(self, verbose: bool = False, console: Console | None = None) -> None:
        self.verbose = verbose
        self.console = console or Console()

    def result(self, comparison: Comparison) -> None:
        summary = ComparisonFormatter.summary(
            comparison,
            self.verbose or comparison.status is not ComparisonStatus.OK,
        )
        self.new_line()
        self._print(summary)
        if comparison.equipped_score and comparison.candidate_score:
            self._score_table(comparison)
        self.new_line()

    def new_line(self) -> None:
        self.console.print()

    def foreground(self, active: bool) -> None:
        self._print(f"[dim]{'OCR resumed' if active else 'OCR paused'}[/dim]")

    def warning(self, message: str) -> None:
        self._print(f"[yellow]{message}[/yellow]")

    def debug(self, message: str) -> None:
        self._print(f"[dim]{message}[/dim]")

    def _print(self, renderable: str | Text) -> None:
        timestamp = time.strftime("%H:%M:%S")
        if isinstance(renderable, Text):
            self.console.print(Text.assemble((f"[{timestamp}] ", "dim"), renderable))
        else:
            self.console.print(f"[dim][{timestamp}][/dim] {renderable}")

    def _score_table(self, comparison: Comparison) -> None:
        equipped_score = comparison.equipped_score
        candidate_score = comparison.candidate_score
        equipped_item = comparison.equipped
        candidate_item = comparison.candidate
        if equipped_score is None or candidate_score is None or equipped_item is None or candidate_item is None:
            return

        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            header_style="bold",
            padding=(0, 2),
        )
        table.add_column(self._header("EQUIPPED", equipped_item, equipped_score), width=54, no_wrap=True)
        table.add_column(self._header("CANDIDATE", candidate_item, candidate_score), width=54, no_wrap=True)
        rows = max(len(equipped_item.stats), len(candidate_item.stats))
        for index in range(rows):
            left = self._affix(equipped_item.stats[index], equipped_score) if index < len(equipped_item.stats) else Text("")
            right = self._affix(candidate_item.stats[index], candidate_score) if index < len(candidate_item.stats) else Text("")
            table.add_row(left, right)
        self.console.print(table)
        self._score_breakdown(comparison)

    def _score_breakdown(self, comparison: Comparison) -> None:
        delta = score_delta_payload(comparison)
        if delta is None:
            return
        labels = {
            "pve": "PvE",
            "target_defense": "Defense",
            "target_triple": "Triple",
            "target_mega": "Mega",
            "normal_priorities": "Normals",
            "flexibility": "Flex",
            "offense": "Offense",
            "defense": "Defense",
            "sustain": "Sustain",
            "utility": "Utility",
            "balance": "Balance",
        }
        parts = delta["components"]
        summary = " · ".join(
            f"{labels.get(name, name)} {change:+.1f}"
            for name, change in parts.items()
        )
        self.console.print(
            f"[dim]Δ points (candidate − equipped): {summary}"
            f" = {delta['total']:+.1f}[/dim]"
        )
        self.console.print("[dim]Σ means total build stat %, NOT score points.[/dim]")

    @staticmethod
    def _header(label, item, score: BuildScore) -> str:
        rarity = f" {item.rarity}" if item.rarity else ""
        level = f", Lv{item.level}" if item.level is not None else ""
        return (
            f"{label}{rarity}{level} {score.total:.1f} "
            f"[combat {score.combat:.1f} · atk {ConsolePresenter._compact(score.base_attack)} "
            f"· hp {ConsolePresenter._compact(score.base_health)} · flex {score.flexibility:+.1f}]"
        )

    @staticmethod
    def _compact(value: float) -> str:
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        return f"{value:.0f}"

    @staticmethod
    def _affix(affix: ParsedStat, score: BuildScore) -> Text:
        name = canonical_name(affix.name)
        value = beneficial_value(name, affix.value)
        build_stat = score.stat(name)
        aggregate = ""
        if build_stat is not None:
            aggregate = f" Σ{build_stat.raw:.1f}"
            if build_stat.capped:
                aggregate += f"→{build_stat.effective:.0f}"

        line = Text()
        line.append(f"{value:+.2f}%  ", style="cyan")
        line.append(f"{name:<23}", style="orange3" if name in EXCEPTIONAL_SKILLS else "white")
        line.append(aggregate, style="dim")
        return line
