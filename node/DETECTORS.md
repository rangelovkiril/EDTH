# Writing a detector

The node reads frames from a camera, asks a **detector** where the airborne objects are in the
image, converts each pixel to a bearing and publishes it. Passive sensing only. How to run it
without hardware is in [`AGENTS.md`](AGENTS.md); the settings are in [`CONFIG.md`](CONFIG.md).

A detector is any class with a no-argument constructor and a `detect` method. It gets one BGR
frame (`numpy` array, `uint8`, shape `H×W×3`) and returns the **pixel** centres of what it found.
You never deal with angles, MQTT or time.

```python
# src/yolo.py
import numpy as np

from .detector import Detection


class YoloDetector:
    def __init__(self): ...  # load the model once

    def detect(self, frame: np.ndarray) -> list[Detection]:
        # u = x pixel (right), v = y pixel (down), conf in [0, 1]
        return [Detection(u=412.0, v=88.5, conf=0.9)]
```

Run it by name, without touching `__main__.py`:

```sh
DETECTOR=yolo:YoloDetector NODE_ID=rpi-1 DRY_RUN=1 CAMERA_DEVICE=clip.mp4 uv run python -m src
```

`DETECTOR` is `module:Class`; a module name without a dot is looked up inside `src`.

Things to know:

- **Return only what you believe.** Several detections per frame are fine. Return `[]` when
  there is nothing. The broker later drops anything with `conf < 0.5`, so calibrate `conf` honestly.
- **Keep up with the camera.** The Pi has to stay near the camera frame rate. `status.fps` shows
  the real rate; if it drops, shrink the input or skip work. Detectors are called once per frame,
  on the main thread.
- **State is fine.** Trackers and background models can live on the instance (see `motion.py`).
- **No network, no files at import time**, and no printing to stdout: stdout is the payload
  stream in `DRY_RUN`. Use `logging`.
- **Add dependencies** with `uv add <pkg>`; the lockfile is committed. The Pi image is arm64, so
  prefer packages with arm64 wheels, and keep the image small (`opencv-python-headless`, no GUI).
- **Test it** with a synthetic frame, like `tests/test_motion.py`.
