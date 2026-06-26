"""Live vitals readout."""

import math
from collections import deque

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .policy import Decision, Policy
from .sensors import Reading
from .state import zone_for

_TAG_STYLE = {"sense": "dim", "adapt": "magenta", "reflex": "bold red"}


def _bar(value: float, lo: float, hi: float, width: int = 26) -> Text:
    if math.isnan(value) or hi <= lo:
        return Text("·" * width, style="dim")
    frac = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(frac * width)
    return Text("█" * filled + "░" * (width - filled))


def _watts(power: float) -> str:
    return "  n/a" if math.isnan(power) else f"{power:4.0f}W"


class Dashboard:
    def __init__(self, critical: float, title: str = "kilngpu", log_size: int = 12):
        self.critical = critical
        self.title = title
        self.reading: Reading | None = None
        self.policy: Policy | None = None
        self.log: deque[tuple[str, str]] = deque(maxlen=log_size)

    def update(self, reading: Reading, policy: Policy, decision: Decision) -> None:
        self.reading, self.policy = reading, policy
        zone = zone_for(reading.temp, self.critical)
        self.log.append(("sense", f"{reading.temp:5.1f}C  {reading.util:3.0f}%  "
                                  f"{_watts(reading.power)}  zone {zone}  "
                                  f"load {decision.intensity:4.0%}"))
        self.log.extend(decision.events)

    def render(self):
        if self.reading is None:
            return Panel(Text("starting…", style="dim"), title=self.title, border_style="grey37")

        r, p = self.reading, self.policy
        vitals = Table.grid(padding=(0, 1))
        vitals.add_column(style="dim", justify="right")
        vitals.add_column()
        vitals.add_column(justify="right")
        vitals.add_row("temp", _bar(r.temp, 30, self.critical + 3), f"{r.temp:.1f}C")
        vitals.add_row("util", _bar(r.util, 0, 100), f"{r.util:.0f}%")
        vitals.add_row("power", _bar(r.power, 0, 320), _watts(r.power).strip())
        vitals.add_row("fan", _bar(r.fan, 0, 100), f"{r.fan:.0f}%")

        status = Text()
        status.append(f"zone {zone_for(r.temp, self.critical)}", style="bold")
        status.append(f"   target {p.setpoint:.0f}C   throttle {self.critical:.0f}C\n", style="dim")
        status.append(f"workload {p.intensity:>4.0%}   integral {p.integral:+.1f}", style="dim")

        log = Text()
        for tag, msg in self.log:
            log.append(f"[{tag}] ", style=_TAG_STYLE.get(tag, "white"))
            log.append(f"{msg}\n")

        body = Group(vitals, Text(), status, Text(), log)
        return Panel(body, title=self.title, subtitle="self-regulating on the gpu", border_style="grey37")
