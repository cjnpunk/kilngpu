import asyncio

from kilngpu.loop import run_loop
from kilngpu.policy import Policy
from kilngpu.sensors import MockSensor, Reading


class _NullLoad:
    def start(self): pass
    def stop(self): pass
    def apply(self, intensity, sensor): sensor.apply_load(intensity)


def _r(temp):
    return Reading(temp=temp, util=0, power=0, fan=0)


def test_reflex_cools_and_resets_integral_at_critical():
    p = Policy(critical=90, integral=50.0, intensity=0.8)
    d = p.react(_r(91), dt=1.0)
    assert d.intensity == 0.0
    assert p.integral == 0.0
    assert any(tag == "reflex" for tag, _ in d.events)


def test_proportional_sign_is_correct():
    below = Policy(setpoint=65).react(_r(50), dt=1.0).intensity
    above = Policy(setpoint=65, intensity=0.5, integral=10).react(_r(80), dt=1.0).intensity
    assert below > 0          # cold -> work
    assert above < 0.5        # hot -> back off


def test_integral_does_not_wind_up_while_saturated():
    # Pinned far below target: output rails high, the integral must not run away.
    p = Policy(setpoint=65, out_max=1.0)
    for _ in range(50):
        p.react(_r(40), dt=1.0)
    # Without anti-windup, integrating error=25 for 50 ticks would reach ~1250.
    # Conditional integration caps it where the output saturates.
    assert p.integral < 80
    assert p.intensity >= 0.9


def test_setpoint_drops_under_sustained_heat():
    p = Policy(critical=90, hot_margin=8, setpoint=65, floor_setpoint=52)
    start = p.setpoint
    for _ in range(25):            # 25s within 8C of critical
        p.react(_r(85), dt=1.0)
    assert p.setpoint < start
    assert p.setpoint >= p.floor_setpoint


def test_loop_holds_temperature_near_target():
    sensor = MockSensor(idle=35, ceiling=95, tau=4.0, seed=1)
    policy = Policy(setpoint=65, critical=90)
    temps = []
    asyncio.run(run_loop(sensor, policy, _NullLoad(),
                         lambda r, p, d: temps.append(r.temp),
                         interval=0, dt=sensor.dt, max_ticks=600))
    settled = temps[-100:]
    avg = sum(settled) / len(settled)
    assert abs(avg - 65) < 4      # converges on the setpoint, no standing offset
