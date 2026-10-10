from __future__ import annotations

import math
import shlex
import subprocess
from pathlib import Path

from .domain import Comparison
from .presentation import ComparisonFormatter


class PhoneNotifier:
    EQUIP_COLOR = "#167D32"
    SELL_COLOR = "#B00020"
    CHECK_COLOR = "#B26A00"

    def __init__(
        self,
        ssh_target: str,
        *,
        ssh_port: int | None = None,
        identity_file: Path | None = None,
        trust_transport: bool = False,
        toast: bool = True,
        push: bool = True,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.ssh_target = ssh_target
        self.ssh_port = ssh_port
        self.identity_file = identity_file
        self.trust_transport = trust_transport
        self.toast = toast
        self.push = push
        self.timeout_seconds = timeout_seconds

    def send(self, comparison: Comparison) -> None:
        summary = str(ComparisonFormatter.summary(comparison, verbose=False))
        commands = self._commands(comparison, summary)
        if commands:
            self._ssh(" && ".join(commands))

    def _commands(self, comparison: Comparison, summary: str) -> list[str]:
        color, icon = self._style(comparison)
        commands: list[str] = []
        if self.toast:
            commands.append(
                f"termux-toast -s -g top -b {shlex.quote(color)} -c white {shlex.quote(summary)}"
            )
        if self.push:
            commands.append(
                " ".join(
                    [
                        "termux-notification",
                        "--id dungeon-rush-compare",
                        "--title 'Dungeon Rush'",
                        f"--content {shlex.quote(summary)}",
                        "--priority high",
                        f"--icon {shlex.quote(icon)}",
                    ]
                )
            )
        return commands

    @staticmethod
    def _style(comparison: Comparison) -> tuple[str, str]:
        if comparison.action.value == "check":
            return PhoneNotifier.CHECK_COLOR, "warning"
        if comparison.action.value == "equip":
            return PhoneNotifier.EQUIP_COLOR, "check_circle"
        return PhoneNotifier.SELL_COLOR, "delete"

    def _ssh(self, remote_command: str) -> None:
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            f"ConnectTimeout={max(1, math.ceil(self.timeout_seconds))}",
        ]
        if self.trust_transport:
            command += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        if self.ssh_port is not None:
            command += ["-p", str(self.ssh_port)]
        if self.identity_file is not None:
            command += ["-i", str(self.identity_file)]
        command += [self.ssh_target, remote_command]
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout_seconds + 1,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return
