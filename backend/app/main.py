from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.core.config import Settings
from app.core.service import Service
from app.db.store import DuplicateDocument
from app.ingestion.files import InvalidUpload, MAX_UPLOAD_BYTES
from app.llm.ollama import LocalModelUnavailable


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Decision(BaseModel):
    action: str


def create_app(settings: Settings | None = None, embedder=None, llm=None) -> FastAPI:
    settings = settings or Settings.from_env()
    application = FastAPI(title="NeuroVault + Synapse V0", version="0.1.0",
                          docs_url=None, redoc_url=None)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    application.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                               allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    application.state.service = Service(settings, embedder, llm)

    @application.middleware("http")
    async def local_origin_only(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173"}:
            return JSONResponse({"detail": "Only the local dashboard may call this API from a browser"}, status_code=403)
        length = request.headers.get("content-length", "0")
        if not length.isdecimal():
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if request.method == "POST" and int(length) > MAX_UPLOAD_BYTES + 1024 * 1024:
            return JSONResponse({"detail": "Request exceeds the upload limit"}, status_code=413)
        return await call_next(request)

    @application.get("/api/health")
    def health():
        return {"status": "ok", "embedding_model": settings.embedding_model,
                "ollama": application.state.service.llm.status()}

    @application.get("/api/dashboard")
    def dashboard():
        return application.state.service.store.dashboard()

    @application.get("/api/documents")
    def documents():
        return application.state.service.store.documents()

    @application.get("/api/documents/{document_id}")
    def document(document_id: str):
        result = application.state.service.store.document(document_id)
        if not result:
            raise HTTPException(status_code=404, detail="Document not found")
        return result

    @application.post("/api/documents/upload", status_code=201)
    async def upload(file: UploadFile = File(...)):
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        await file.close()
        try:
            return application.state.service.ingest(file.filename or "", file.content_type, data)
        except InvalidUpload as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except DuplicateDocument as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post("/api/ask")
    def ask(body: Question):
        if len(body.question.strip()) < 3:
            raise HTTPException(status_code=422, detail="Question must contain at least three visible characters")
        try:
            return application.state.service.ask(body.question.strip())
        except LocalModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/api/memories")
    def memories():
        return application.state.service.store.memories()

    @application.get("/api/alerts")
    def alerts():
        return application.state.service.store.alerts()

    @application.post("/api/alerts/{alert_id}/resolve")
    def resolve(alert_id: str, body: Decision):
        try:
            result = application.state.service.store.resolve_alert(alert_id, body.action)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return result

    return application


app = create_app()
