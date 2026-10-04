"""FastAPI application. Read handlers are plain functions so FastAPI runs them in its thread pool."""

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from api.interview import Ask, InterviewFailed, InterviewUnavailable, Interviewer, llm_generate
from api.media import RecordingUnavailable
from api.runs import NotFound, RunInvalid, list_runs
from api.service import Reader

STATUS = {NotFound: 404, RunInvalid: 422, InterviewUnavailable: 503, InterviewFailed: 502, RecordingUnavailable: 503}


def create_app(runs_root, interviewer=None, recordings=None):
    app = FastAPI(title="muchhuman", docs_url="/api/docs", openapi_url="/api/openapi.json")
    reader = Reader(runs_root, recordings)
    interviewer = interviewer or Interviewer(llm_generate(None))

    for error_type, status in STATUS.items():
        app.add_exception_handler(error_type, lambda request, error, status=status: JSONResponse({"detail": str(error)}, status))

    @app.get("/api/runs")
    def runs():
        return list_runs(reader.root)

    @app.get("/api/runs/{run_id}")
    def overview(run_id: str):
        return reader.overview(run_id)

    @app.get("/api/runs/{run_id}/personas")
    def personas(run_id: str):
        return reader.personas(run_id)

    @app.get("/api/runs/{run_id}/personas/{persona_id}/experience")
    def experience(run_id: str, persona_id: str):
        return reader.experience(run_id, persona_id)

    @app.get("/api/runs/{run_id}/personas/{persona_id}/recording")
    def recording(run_id: str, persona_id: str):
        return reader.recording(run_id, persona_id)[1]

    @app.get("/api/runs/{run_id}/personas/{persona_id}/recording.m3u8")
    def playlist(run_id: str, persona_id: str):
        return Response(reader.recording(run_id, persona_id)[0], media_type="application/vnd.apple.mpegurl")

    @app.post("/api/runs/{run_id}/personas/{persona_id}/interview")
    async def interview(run_id: str, persona_id: str, ask: Ask):
        store = await run_in_threadpool(reader.store, run_id)
        return await interviewer.ask(store, persona_id, ask)

    @app.get("/api/runs/{run_id}/community")
    def community(run_id: str):
        return reader.community(run_id)

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, report_id: str | None = None):
        return reader.report(run_id, report_id)

    @app.get("/api/runs/{run_id}/evidence/{ref:path}")
    def evidence(run_id: str, ref: str):
        return reader.evidence(run_id, ref)

    @app.get("/api/runs/{run_id}/files/{path:path}")
    def files(run_id: str, path: str):
        return FileResponse(reader.file(run_id, path), media_type="image/png")

    return app
