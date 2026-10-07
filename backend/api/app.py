"""FastAPI application. Read handlers are plain functions so FastAPI runs them in its thread pool."""

from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from api import drafts, live
from api.drafts import Invalid, Unconfigured
from api.interview import Ask, InterviewFailed, InterviewUnavailable, Interviewer, llm_generate
from api.jobs import Busy, Jobs
from api.media import RecordingUnavailable
from api.runs import NotFound, RunInvalid, list_runs
from api.service import Reader

STATUS = {NotFound: 404, RunInvalid: 422, InterviewUnavailable: 503, InterviewFailed: 502, RecordingUnavailable: 503,
          Invalid: 422, Unconfigured: 503, Busy: 409}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ManualText(BaseModel):
    text: str = Field(max_length=drafts.MAX_MANUAL)


class NewDraft(BaseModel):
    manual: str = Field(max_length=drafts.MAX_MANUAL)
    capability_run: str | None = None


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    draft_sha256: str
    accept_overrides: bool = False


class Confirm(BaseModel):
    confirm: Literal[True]


class Size(BaseModel):
    persona_count: int
    duration_days: int


class SamplingEdit(BaseModel):
    temperature: float
    top_p: float
    presence_penalty: float


class DraftEdit(BaseModel):
    draft_sha256: str
    duration_days: int | None = None
    sampling: dict[str, SamplingEdit] | None = None


def create_app(runs_root, interviewer=None, recordings=None, jobs=None):
    app = FastAPI(title="muchhuman", docs_url="/api/docs", openapi_url="/api/openapi.json")
    reader = Reader(runs_root, recordings)
    interviewer = interviewer or Interviewer(llm_generate(None, runs_root))
    jobs = jobs or Jobs(reader.root)

    @app.middleware("http")
    async def same_machine_writes(request: Request, call_next):
        # POSTs start paid model and browser work. A page on another site must not be able to trigger them through
        # the user's browser: only same-machine origins may write, and every POST takes a JSON body (no form posts).
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
                return JSONResponse({"detail": "只接受本机页面发起的写操作"}, 403)
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return JSONResponse({"detail": "请求体必须是 JSON"}, 415)
        return await call_next(request)

    # DNS rebinding: another site can point its own name at 127.0.0.1 and then read run data same-origin.
    # Only local host names reach the API (the Vite proxy keeps the browser's localhost Host).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*LOCAL_HOSTS, "[::1]"])

    for error_type, status in STATUS.items():
        app.add_exception_handler(error_type, lambda request, error, status=status: JSONResponse(
            {"detail": str(error), **({"reason": error.reason} if hasattr(error, "reason") else {})}, status))

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

    # —— New runs: manual → persona draft → human review → simulation and report ——

    @app.post("/api/manuals/check")
    def check_manual(body: ManualText):
        return drafts.check_manual(body.text)

    @app.get("/api/capabilities")
    def capabilities():
        return drafts.capabilities(reader.root)

    @app.get("/api/drafts")
    def list_drafts():
        return drafts.list_drafts(reader.root, jobs.all())

    @app.post("/api/drafts")
    def new_draft(body: NewDraft):
        return drafts.start_prepare(reader.root, jobs, body.manual, body.capability_run)

    @app.get("/api/drafts/{draft_id}")
    def draft_review(draft_id: str):
        return drafts.review(reader.root, draft_id, jobs.all())

    @app.post("/api/drafts/{draft_id}/analysis")
    def resume(draft_id: str, body: Confirm):
        return drafts.start_resume(reader.root, jobs, draft_id)

    @app.post("/api/drafts/{draft_id}/personas")
    def generate(draft_id: str, body: Size):
        return drafts.start_generate(reader.root, jobs, draft_id, body.persona_count, body.duration_days)

    @app.post("/api/drafts/{draft_id}/edits")
    def edit_draft(draft_id: str, body: DraftEdit):
        sampling = {pid: item.model_dump() for pid, item in body.sampling.items()} if body.sampling else None
        return drafts.update_draft(reader.root, draft_id, body.draft_sha256, body.duration_days, sampling)

    @app.post("/api/drafts/{draft_id}/decision")
    def decide(draft_id: str, body: Decision):
        return drafts.decide(reader.root, draft_id, body.decision, body.draft_sha256, body.accept_overrides)

    @app.post("/api/drafts/{draft_id}/simulations")
    def simulate(draft_id: str, body: Confirm):
        return drafts.start_simulation(reader.root, jobs, draft_id)

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.all()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        found = jobs.view(job_id) if drafts.RUN_ID.fullmatch(job_id) else None
        if found is None:
            raise NotFound(f"Unknown job: {job_id}")
        return {**found, "log": jobs.log_tail(job_id)}

    def simulation_job(job_id):
        found = jobs.view(job_id) if drafts.RUN_ID.fullmatch(job_id) else None
        if found is None or found["kind"] != "simulate":
            raise NotFound(f"Unknown simulation job: {job_id}")
        return found

    @app.get("/api/jobs/{job_id}/live")
    def job_live(job_id: str, persona: str | None = None):
        return live.live(reader.root, simulation_job(job_id), persona)

    @app.get("/api/jobs/{job_id}/shots/{persona_id}/{name}")
    def job_shot(job_id: str, persona_id: str, name: str):
        return FileResponse(live.screenshot(reader.root, simulation_job(job_id), persona_id, name), media_type="image/png")

    return app
