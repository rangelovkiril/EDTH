import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Engine


class Settings(BaseModel):
    threshold: float = Field(ge=5, le=100)
    min_area: int = Field(ge=2, le=500)


def create_app(config, root=None):
    root = Path(root or Path.cwd())
    assets = Path(__file__).resolve().parent / "static"
    engine = Engine(config, root)

    @asynccontextmanager
    async def lifespan(app):
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title="Triangulum USB camera bench", lifespan=lifespan)
    app.state.engine = engine

    @app.middleware("http")
    async def local_writes(request: Request, call_next):
        # Same-origin writes only. No permissive CORS or cross-site form mutations.
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return Response("Cross-origin write rejected", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return FileResponse(assets / "index.html")

    @app.get("/api/state")
    def state():
        return engine.snapshot()

    @app.get("/api/cameras/{camera_id}/frame.jpg")
    def frame(camera_id: int, mask: bool = False):
        if not 0 <= camera_id < len(engine.camera_configs):
            raise HTTPException(404, "Unknown camera")
        with engine.lock:
            image = (engine.masks if mask else engine.jpegs)[camera_id]
            current = engine.latest_frames[camera_id]
        import time

        if image is None or current is None or time.monotonic() - current.timestamp > 1:
            raise HTTPException(503, "Camera unavailable")
        return Response(image, media_type="image/jpeg")

    @app.post("/api/settings")
    def settings(value: Settings):
        return engine.update_settings(value.model_dump())

    @app.post("/api/reset")
    def reset():
        with engine.lock:
            engine.reset_requested = True
        return {"status": "Background reset scheduled"}

    @app.post("/api/calibration/capture")
    def capture():
        try:
            return engine.save_pair()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/events.csv")
    def events():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["time", "camera", "track", "event", "mode"])
        writer.writeheader()
        with engine.lock:
            writer.writerows(list(engine.events))
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="skywatch-events.csv"'},
        )

    @app.get("/metrics")
    def metrics():
        state = engine.snapshot()
        values = {
            "frames_total": state.get("frames_total", 0),
            "events_total": state.get("events_total", 0),
            "processing_ms": state.get("processing_ms", 0),
            "voxel_candidates": len(state.get("voxels", [])),
            "simulation": int(engine.mode == "demo"),
        }
        lines = []
        for name, value in values.items():
            metric_type = "counter" if name.endswith("_total") else "gauge"
            lines.extend([f"# TYPE skywatch_{name} {metric_type}", f"skywatch_{name} {value}"])
        for camera in state["cameras"]:
            lines.append(
                f'skywatch_camera_up{{camera="{camera["id"]}"}} {int(camera["connected"])}'
            )
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    app.mount("/static", StaticFiles(directory=assets), name="static")
    return app
