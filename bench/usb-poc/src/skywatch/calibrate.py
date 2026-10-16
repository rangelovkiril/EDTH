#!/usr/bin/env python3
"""Calibrate the first camera pair from dashboard captures. Units: metres."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/calibration")
    parser.add_argument("--cols", type=int, default=9, help="INNER corners, not squares")
    parser.add_argument("--rows", type=int, default=6)
    parser.add_argument(
        "--square-m", type=float, required=True, help="Measured printed square side in metres"
    )
    parser.add_argument("--output", default="config/calibration.json")
    args = parser.parse_args()
    if not 0 < args.square_m < 10 or min(args.cols, args.rows) < 3:
        parser.error("Use a positive square size and at least 3x3 inner corners")
    pattern = (args.cols, args.rows)
    board = np.zeros((args.cols * args.rows, 3), np.float32)
    board[:, :2] = np.mgrid[: args.cols, : args.rows].T.reshape(-1, 2) * args.square_m
    objects, left, right, used = [], [], [], []
    size, sources = None, None
    for path in sorted(Path(args.directory).glob("*_0.png")):
        pair = path.name[:-6]
        other = path.with_name(pair + "_1.png")
        metadata_path = path.with_name(pair + ".json")
        if not other.exists() or not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        if sources is not None and sources != metadata["sources"]:
            raise SystemExit(
                "Mixed camera source order in capture directory; use a fresh directory"
            )
        sources = metadata["sources"]
        images = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in (path, other)]
        if any(image is None for image in images):
            continue
        if images[0].shape != images[1].shape:
            raise SystemExit("Both cameras must use the same resolution for this calibration tool")
        current_size = images[0].shape[::-1]
        if size is not None and current_size != size:
            raise SystemExit("Mixed resolutions in calibration captures")
        size = current_size
        detected = [
            cv2.findChessboardCornersSB(
                image, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE
            )
            for image in images
        ]
        if all(ok for ok, _ in detected):
            objects.append(board.copy())
            left.append(detected[0][1])
            right.append(detected[1][1])
            used.append(pair)
    if len(objects) < 12:
        raise SystemExit(
            f"Only {len(objects)} usable pairs. Capture at least 12; aim for 20–30 varied poses."
        )
    rms0, k0, d0, _, _ = cv2.calibrateCamera(objects, left, size, None, None)
    rms1, k1, d1, _, _ = cv2.calibrateCamera(objects, right, size, None, None)
    rms, k0, d0, k1, d1, r, t, _, _ = cv2.stereoCalibrate(
        objects,
        left,
        right,
        k0,
        d0,
        k1,
        d1,
        size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-7),
    )
    baseline = float(np.linalg.norm(t))
    print(
        f"Pairs: {len(objects)} | RMS left/right/stereo: {rms0:.3f}/{rms1:.3f}/{rms:.3f} px"
        f" | baseline: {baseline:.4f} m"
    )
    if (
        not np.isfinite([rms0, rms1, rms, baseline]).all()
        or max(rms0, rms1, rms) > 1.5
        or baseline < 0.01
    ):
        raise SystemExit(
            "Calibration quality rejected. Check board size/orientation, focus and camera rigidity;"
            " recapture."
        )
    cameras = [
        dict(
            K=k0.tolist(),
            dist=d0.ravel().tolist(),
            center=[0, 0, 0],
            rotation=np.eye(3).tolist(),
            size=size,
        ),
        dict(
            K=k1.tolist(),
            dist=d1.ravel().tolist(),
            center=(-r.T @ t).ravel().tolist(),
            rotation=r.T.tolist(),
            size=size,
        ),
    ]
    result = {
        "simulated": False,
        "sources": sources,
        "cameras": cameras,
        "baseline_m": baseline,
        "stereo_rms_px": rms,
        "intrinsic_rms_px": [rms0, rms1],
        "pairs": used,
        "square_m": args.square_m,
        "coordinates": "First camera: x right, y down, z forward; metres",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(
        f"Saved {output}. Check baseline against a ruler,"
        " then set calibration in config/live.json and restart."
    )


if __name__ == "__main__":
    main()
