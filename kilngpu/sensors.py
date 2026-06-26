"""GPU telemetry sources.

`NvmlSensor` reads a real NVIDIA card through NVML, including the hardware's own
slowdown threshold so limits come from the silicon, not a guess. `MockSensor`
integrates a first-order thermal model so the control loop runs and can be tested
on a machine with no GPU."""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Reading:
    temp: float    # degrees C
    util: float    # 0..100
    power: float   # watts (nan if the card won't report it)
    fan: float     # 0..100


class Sensor:
    name = "sensor"

    def read(self) -> Reading:
        raise NotImplementedError

    def slowdown_temp(self) -> Optional[float]:
        """Temperature at which the hardware starts throttling, if known."""
        return None

    def apply_load(self, intensity: float) -> None:
        """Only the mock models its own heat from intensity. Real cards heat up
        because the load generator runs actual work, so this is a no-op there."""

    def close(self) -> None:
        pass


class NvmlSensor(Sensor):
    name = "nvml"

    def __init__(self, index: int = 0):
        try:
            import pynvml
        except ImportError as e:
            raise RuntimeError(
                "the NVML reader needs nvidia-ml-py (`pip install nvidia-ml-py`), "
                "or run with --mock to use the simulated card."
            ) from e
        self._nvml = pynvml
        pynvml.nvmlInit()
        self._h = pynvml.nvmlDeviceGetHandleByIndex(index)
        name = pynvml.nvmlDeviceGetName(self._h)
        self.gpu_name = name.decode() if isinstance(name, bytes) else name

    def read(self) -> Reading:
        n, h = self._nvml, self._h
        temp = n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU)
        util = n.nvmlDeviceGetUtilizationRates(h).gpu
        try:
            power = n.nvmlDeviceGetPowerUsage(h) / 1000.0
        except n.NVMLError:
            power = float("nan")
        try:
            fan = float(n.nvmlDeviceGetFanSpeed(h))
        except n.NVMLError:
            fan = 0.0
        return Reading(float(temp), float(util), power, fan)

    def slowdown_temp(self) -> Optional[float]:
        try:
            return float(self._nvml.nvmlDeviceGetTemperatureThreshold(
                self._h, self._nvml.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN))
        except self._nvml.NVMLError:
            return None

    def close(self) -> None:
        try:
            self._nvml.nvmlShutdown()
        except self._nvml.NVMLError:
            pass


class MockSensor(Sensor):
    name = "mock"

    def __init__(self, idle: float = 38.0, ceiling: float = 92.0, tau: float = 7.0,
                 dt: float = 1.0, seed: int = 0):
        self.idle = idle
        self.ceiling = ceiling      # temperature at sustained full load
        self.tau = tau              # thermal time constant (s)
        self.dt = dt                # simulated seconds per read
        self.temp = idle
        self.intensity = 0.0
        self._rng = random.Random(seed)

    def apply_load(self, intensity: float) -> None:
        self.intensity = max(0.0, min(1.0, intensity))

    def read(self) -> Reading:
        equilibrium = self.idle + self.intensity * (self.ceiling - self.idle)
        self.temp += (equilibrium - self.temp) * (self.dt / self.tau)
        self.temp += self._rng.uniform(-0.2, 0.2)
        util = self.intensity * 100.0
        power = 30.0 + self.intensity * 270.0
        span = self.ceiling - self.idle
        fan = max(0.0, min(100.0, (self.temp - self.idle) / span * 100.0))
        return Reading(round(self.temp, 2), round(util, 1), round(power, 1), round(fan, 1))

    def slowdown_temp(self) -> Optional[float]:
        return self.ceiling - 5.0
