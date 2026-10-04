"""FastAPI application. Handlers are plain functions so FastAPI runs them in its thread pool."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from api.runs import NotFound, RunInvalid, list_runs
from api.service import Reader


def create_app(runs_root):
    app = FastAPI(title="muchhuman", docs_url="/api/docs", openapi_url="/api/openapi.json")
    reader = Reader(runs_root)

    def guarded(call, *args):
        try:
            return call(*args)
        except NotFound as error:
            raise HTTPException(404, str(error)) from error
        except RunInvalid as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/runs")
    def runs():
        return list_runs(reader.root)

    @app.get("/api/runs/{run_id}")
    def overview(run_id: str):
        return guarded(reader.overview, run_id)

    @app.get("/api/runs/{run_id}/personas")
    def personas(run_id: str):
        return guarded(reader.personas, run_id)

    @app.get("/api/runs/{run_id}/personas/{persona_id}/experience")
    def experience(run_id: str, persona_id: str):
        return guarded(reader.experience, run_id, persona_id)

    @app.get("/api/runs/{run_id}/community")
    def community(run_id: str):
        return guarded(reader.community, run_id)

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, report_id: str | None = None):
        return guarded(reader.report, run_id, report_id)

    @app.get("/api/runs/{run_id}/evidence/{ref:path}")
    def evidence(run_id: str, ref: str):
        return guarded(reader.evidence, run_id, ref)

    @app.get("/api/runs/{run_id}/files/{path:path}")
    def files(run_id: str, path: str):
        return FileResponse(guarded(reader.file, run_id, path), media_type="image/png")

    return app
