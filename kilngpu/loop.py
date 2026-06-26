"""The control loop: sense, decide, drive, repeat."""

import asyncio
from typing import Callable, Optional

from .policy import Decision, Policy
from .sensors import Reading, Sensor

TickFn = Callable[[Reading, Policy, Decision], None]


async def run_loop(
    sensor: Sensor,
    policy: Policy,
    load,
    on_tick: TickFn,
    interval: float = 1.0,
    dt: float = 1.0,
    max_ticks: Optional[int] = None,
    stop: Optional[asyncio.Event] = None,
) -> None:
    load.start()
    ticks = 0
    try:
        while not (stop and stop.is_set()):
            reading = sensor.read()
            decision = policy.react(reading, dt)
            load.apply(decision.intensity, sensor)
            on_tick(reading, policy, decision)
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            if interval > 0:
                await asyncio.sleep(interval)
    finally:
        load.stop()
        sensor.close()
