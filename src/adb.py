from __future__ import annotations

import re
import subprocess
from io import BytesIO

from PIL import Image


class AdbDevice:
    def __init__(self, serial: str, executable: str = "adb", timeout_seconds: float = 15.0) -> None:
        if not serial.strip():
            raise ValueError("ADB serial must not be blank")
        self.serial = serial.strip()
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def screenshot(self) -> Image.Image:
        result = self._run(["exec-out", "screencap", "-p"], binary=True)
        if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("ADB screencap did not return PNG data.")
        image = Image.open(BytesIO(result.stdout)).convert("RGB")
        image.load()
        return image

    def foreground_package(self) -> str | None:
        result = self._run(["shell", "dumpsys", "activity", "activities"], binary=False)
        match = re.search(r"ResumedActivity:.*?\s([A-Za-z0-9._]+)/", result.stdout)
        return match.group(1) if match else self._window_foreground_package()

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int) -> None:
        args = ["shell", "input", "touchscreen", "swipe", str(start[0]), str(start[1]), str(end[0]), str(end[1]), str(duration_ms)]
        self._run(args, binary=False)

    def _window_foreground_package(self) -> str | None:
        result = self._run(["shell", "dumpsys", "window", "windows"], binary=False)
        match = re.search(r"mCurrentFocus=.*?\s([A-Za-z0-9._]+)/", result.stdout)
        return match.group(1) if match else None

    def _run(self, args: list[str], binary: bool):
        command = [self.executable, "-s", self.serial, *args]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=not binary, timeout=self.timeout_seconds, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(f"ADB executable not found: {self.executable!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ADB command timed out for {self.serial!r}") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace") if binary else result.stderr
            raise RuntimeError(f"ADB command failed ({result.returncode}): {stderr.strip()}")
        return result
