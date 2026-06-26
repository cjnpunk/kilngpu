"""The control policy.

Core is a PI controller that holds the GPU at a target temperature by steering
its own workload. Proportional gives the immediate response; the integral term
accumulates against sustained load and ambient drift, so it converges with no
standing offset and the same instantaneous temperature can call for a different
workload depending on history. Conditional integration stops the integral from
winding up while the output is saturated.

On top of that sits a supervisory layer: if the card keeps running close to its
throttle point the agent lowers its own target (gets conservative), and restores
it once things settle. That is the part that "changes how it reacts" — not a
mood, a setpoint the agent moves based on what the hardware is doing."""

from dataclasses import dataclass, field

from .sensors import Reading


@dataclass
class Decision:
    intensity: float                 # workload it will run this tick, 0..1
    setpoint: float                  # current target temperature
    integral: float                  # controller integral term (for inspection)
    events: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Policy:
    # target band
    nominal_setpoint: float = 65.0
    floor_setpoint: float = 52.0
    setpoint: float = 65.0
    # reflex / supervisory thresholds
    critical: float = 90.0           # hard cooldown at or above this
    hot_margin: float = 8.0          # within this of critical counts as "hot"
    # PI gains (output is workload fraction per degree of error)
    kp: float = 0.03
    ki: float = 0.004
    out_min: float = 0.0
    out_max: float = 1.0
    # state
    integral: float = 0.0
    intensity: float = 0.2
    _hot_for: float = 0.0
    _stable_for: float = 0.0

    def react(self, reading: Reading, dt: float) -> Decision:
        events: list[tuple[str, str]] = []
        temp = reading.temp

        # Reflex: at the hardware edge, stop and shed the integral so recovery is
        # bumpless rather than fighting a wound-up term.
        if temp >= self.critical:
            self.intensity = 0.0
            self.integral = 0.0
            events.append(("reflex", f"{temp:.0f}C >= critical {self.critical:.0f}C — cooling down"))
            return Decision(0.0, self.setpoint, self.integral, events)

        events += self._adapt_setpoint(temp, dt)

        # PI toward the (possibly adjusted) setpoint. Positive error means the
        # card is below target, so there is room to work harder.
        error = self.setpoint - temp
        integral_next = self.integral + error * dt
        output = self.kp * error + self.ki * integral_next
        # Conditional integration: only commit the integral if we are not pinned
        # against a rail in the same direction.
        if self.out_min < output < self.out_max:
            self.integral = integral_next
        output = self.kp * error + self.ki * self.integral

        self.intensity = min(self.out_max, max(self.out_min, output))
        return Decision(self.intensity, self.setpoint, self.integral, events)

    def _adapt_setpoint(self, temp: float, dt: float) -> list[tuple[str, str]]:
        events = []
        if self.critical - temp < self.hot_margin:
            self._hot_for += dt
            self._stable_for = 0.0
        else:
            self._stable_for += dt
            self._hot_for = 0.0

        if self._hot_for >= 20 and self.setpoint > self.floor_setpoint:
            new = max(self.floor_setpoint, self.setpoint - 3)
            events.append(("adapt", f"sustained heat — lowering target {self.setpoint:.0f} -> {new:.0f}C"))
            self.setpoint = new
            self._hot_for = 0.0
        elif self._stable_for >= 60 and self.setpoint < self.nominal_setpoint:
            new = min(self.nominal_setpoint, self.setpoint + 1)
            events.append(("adapt", f"settled — easing target {self.setpoint:.0f} -> {new:.0f}C"))
            self.setpoint = new
            self._stable_for = 0.0
        return events
