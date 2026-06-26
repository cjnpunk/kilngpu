"""`kilngpu run` — start the self-regulating agent on a card (or a simulated one)."""

import argparse
import asyncio
import json
import sys

from rich.console import Console
from rich.live import Live

from .load import LoadGenerator
from .loop import run_loop
from .policy import Policy
from .sensors import MockSensor, NvmlSensor
from .state import zone_for
from .tui import Dashboard

CRITICAL_MARGIN = 3.0  # react this many degrees below the hardware throttle point


def _build(args):
    if args.mock:
        sensor = MockSensor()
        title = "kilngpu (mock)"
        dt = sensor.dt
    else:
        try:
            sensor = NvmlSensor(index=args.gpu)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        title = f"kilngpu · {sensor.gpu_name}"
        dt = args.interval

    slowdown = sensor.slowdown_temp()
    critical = (slowdown - CRITICAL_MARGIN) if slowdown is not None else args.critical
    policy = Policy(critical=critical, setpoint=args.target, nominal_setpoint=args.target)
    load = LoadGenerator(device=f"cuda:{args.gpu}")
    return sensor, policy, load, critical, title, dt


async def _run(args) -> None:
    sensor, policy, load, critical, title, dt = _build(args)
    console = Console()
    log_file = open(args.log, "a") if args.log else None

    if not args.mock and not load.live:
        console.print("[yellow]note:[/] no CUDA backend (torch) — reading the card but "
                      "cannot drive it, so the loop is open. Install the 'load' extra to close it.")

    def record(reading, pol, decision):
        if log_file:
            log_file.write(json.dumps({
                "temp": reading.temp, "util": reading.util, "power": reading.power,
                "fan": reading.fan, "zone": zone_for(reading.temp, critical),
                "setpoint": pol.setpoint, "intensity": decision.intensity,
                "integral": pol.integral,
                "events": decision.events,
            }) + "\n")
            log_file.flush()

    try:
        if args.plain:
            def on_tick(reading, pol, decision):
                record(reading, pol, decision)
                zone = zone_for(reading.temp, critical)
                console.print(f"[dim]sense[/] {reading.temp:5.1f}C {reading.util:3.0f}% "
                              f"zone {zone:6} target {pol.setpoint:.0f}C load {decision.intensity:4.0%}")
                for tag, msg in decision.events:
                    console.print(f"[magenta]{tag}[/] {msg}")
            await run_loop(sensor, policy, load, on_tick, interval=args.interval, dt=dt,
                           max_ticks=args.ticks)
        else:
            dash = Dashboard(critical, title=title)

            def on_tick(reading, pol, decision):
                record(reading, pol, decision)
                dash.update(reading, pol, decision)
                live.update(dash.render())

            with Live(Dashboard(critical, title=title).render(), console=console,
                      refresh_per_second=8, screen=False) as live:
                await run_loop(sensor, policy, load, on_tick, interval=args.interval, dt=dt,
                               max_ticks=args.ticks)
    finally:
        if log_file:
            log_file.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="kilngpu", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the agent")
    run.add_argument("--mock", action="store_true", help="use a simulated GPU (no card needed)")
    run.add_argument("--gpu", type=int, default=0, help="GPU index (default 0)")
    run.add_argument("--target", type=float, default=65.0, help="target temperature (C)")
    run.add_argument("--critical", type=float, default=87.0,
                     help="reflex cooldown temperature if the card won't report one")
    run.add_argument("--interval", type=float, default=1.0, help="seconds per tick")
    run.add_argument("--ticks", type=int, default=None, help="stop after N ticks")
    run.add_argument("--log", metavar="PATH", help="append telemetry as JSON lines")
    run.add_argument("--plain", action="store_true", help="line logging instead of the live readout")

    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
