# kilngpu

<img width="1280" height="511" alt="telegram-cloud-photo-size-1-5042290961718906155-y" src="https://github.com/user-attachments/assets/b33f152a-b5c1-4877-80d7-215d46e71281" />

A self-regulating agent that lives on your GPU. It runs a workload on the card,
reads the card's temperature, and modulates how hard it works to hold a target
temperature — its own compute is the heat, so the loop closes on itself. When the
card can't stay cool it gets conservative on its own; when things settle it opens
back up.

This is a control system, not a chatbot. The "thinking" is the workload it runs;
v0 ships a GEMM load to stand in for it (see [Roadmap](#roadmap)).

## Install

```bash
git clone https://github.com/cjnpunk/kilngpu
cd kilngpu
pip install -e .              # rich is the only hard dependency
pip install -e ".[gpu]"       # NVIDIA: read + drive the card (nvidia-ml-py + torch)
```

`[gpu]` pulls in both `nvidia-ml-py` (telemetry) and `torch` (the load). If you
only want one, the `[nvml]` and `[load]` extras install them separately.

## Run

```bash
kilngpu run --mock                  # simulated card, runs anywhere
kilngpu run --target 70             # hold gpu 0 at 70C
kilngpu run --plain --log run.jsonl # line output + telemetry to disk
```

`--mock` runs a first-order thermal model, so the whole feedback loop is visible
and testable on a machine with no GPU.

## How it works

**Sense.** Each tick reads temperature, utilization, power, and fan over NVML.
On a real card it also reads the hardware's slowdown threshold, so the limits
come from the silicon instead of a constant.

**Control.** A PI controller drives the workload toward a target temperature.
Proportional handles the immediate gap; the integral accumulates against
sustained load and ambient drift, which removes steady-state offset — the card
settles *on* the target, not near it. Conditional integration (anti-windup) stops
the integral running away while the output is railed at 0 or 100%.

**Adapt.** A supervisory layer moves the target itself. Sustained running near the
throttle point lowers it (the agent backs off before the driver has to); a long
stable stretch eases it back up. Same temperature, different reaction, depending
on what the hardware has been doing.

**Drive.** A background thread runs GEMMs at a duty cycle equal to the requested
workload — 50% means it computes half of each period and idles the rest. That
sustained, proportional load is the real heat the sensor reads back. With no CUDA
backend the loop is open (it reads but can't drive).

**Reflex.** Above the critical threshold it stops outright and clears the
integral, so recovery is bumpless. This sits *on top of* the driver's own thermal
protection and never replaces it — telemetry is read-only, no overclocking, no
clock or fan control.

## Layout

```
kilngpu/
  sensors.py   NVML + mock thermal model, hardware limits
  state.py     thermal zones, relative to the card's limit
  policy.py    PI controller, anti-windup, adaptive setpoint, reflex
  load.py      duty-cycle CUDA load generator
  loop.py      sense -> decide -> drive
  tui.py       live vitals (rich)
  cli.py       kilngpu run
tests/         control behavior under the mock model
```

## Roadmap

- v1: replace the GEMM load with real model inference, so the "thinking" that
  heats the card is actual work.
- Online identification of the thermal time constant to self-tune the gains.
- AMD (`rocm-smi`) and Apple sensors behind the same `Sensor` interface.

## License

MIT.
