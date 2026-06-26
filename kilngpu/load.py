"""Turns a workload fraction into real heat.

A background thread runs GEMMs on the GPU at a duty cycle equal to the requested
intensity: at 0.5 it works half of each period and idles the other half. That
sustained, proportional load is what actually warms the card, and the warmth is
what the sensor reads back, closing the loop. With no CUDA backend it degrades to
feeding the mock sensor's thermal model."""

import threading
import time


class LoadGenerator:
    def __init__(self, device: str = "cuda", period: float = 0.25, matrix: int = 4096):
        self.device = device
        self.period = period          # seconds per duty cycle
        self.matrix = matrix
        self._intensity = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.torch = None
        self.live = False
        try:
            import torch
            self.torch = torch
            self.live = torch.cuda.is_available()
        except ImportError:
            pass

    def start(self) -> None:
        if self.live and self._thread is None:
            self._thread = threading.Thread(target=self._burn, daemon=True)
            self._thread.start()

    def apply(self, intensity: float, sensor) -> None:
        intensity = max(0.0, min(1.0, intensity))
        with self._lock:
            self._intensity = intensity
        sensor.apply_load(intensity)  # mock thermal model; no-op on real hardware

    def _burn(self) -> None:
        torch = self.torch
        a = torch.randn(self.matrix, self.matrix, device=self.device)
        b = torch.randn(self.matrix, self.matrix, device=self.device)
        while not self._stop.is_set():
            with self._lock:
                duty = self._intensity
            if duty <= 0.0:
                time.sleep(self.period)
                continue
            deadline = time.perf_counter() + self.period * duty
            while time.perf_counter() < deadline and not self._stop.is_set():
                a = a @ b
            torch.cuda.synchronize()
            if duty < 1.0:
                time.sleep(self.period * (1.0 - duty))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
