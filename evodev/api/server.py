"""FastAPI local daemon for EvoDev REST API and developer dashboard."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig, load_config
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.opencode import OpenCodeConnector
from evodev.evaluation.benchmark import BenchmarkSuiteRunner
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class QueryRequest(BaseModel):
    task_description: str
    project_id: str = "web-client"
    domain: str = "general"
    technologies: List[str] = []


class ProfileCreateRequest(BaseModel):
    name: str
    description: str = ""
    domains: List[str] = ["general"]
    technologies: List[str] = []
    activate: bool = False


class BenchmarkRunRequest(BaseModel):
    suite: str = "standard_dev_challenges"
    mode: str = "evodev_experienced"


class ArchiveInspectFileRequest(BaseModel):
    file_path: Optional[str] = None
    password: Optional[str] = None


class LessonModifyRequest(BaseModel):
    updates: Dict[str, Any]
    confirm: bool = False
    reason: str = "User manual edit"


class DeleteConfirmRequest(BaseModel):
    confirm: bool = False



def create_api_app(config: Optional[EvoDevConfig] = None) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    cfg = config or load_config()
    db = get_db(cfg)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)
    b_repo = BenchmarkRepository(db)

    mgr = ProfileManager(p_repo, l_repo, s_repo, e_repo, b_repo, cfg)
    inspector = ProfileInspector(p_repo, l_repo, s_repo, e_repo, b_repo, ev_repo, cfg)
    collector = CollectorService(ev_repo, e_repo, p_repo)
    engine = RetrievalEngine(l_repo, p_repo)
    assembler = ContextAssembler()


    app = FastAPI(
        title=f"{cfg.product_name} Local Experience API",
        description="Local-first experience and learning layer daemon",
        version="1.0.0",
    )

    # Allow local CORS only for dashboard and local tools
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8765", "http://127.0.0.1:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 1. Status & Telemetry
    @app.get("/api/status")
    def get_status():
        active = p_repo.get_active()
        p_id = active.profile_id if active else "default"
        opencode_conn = OpenCodeConnector()
        gemini_conn = GeminiCLIConnector()

        db_size_kb = 0
        if cfg.db_path.is_file():
            db_size_kb = round(cfg.db_path.stat().st_size / 1024, 1)

        return {
            "product_name": cfg.product_name,
            "database": {
                "path": str(cfg.db_path),
                "size_kb": db_size_kb,
                "total_events": ev_repo.count(),
            },
            "active_profile": active.model_dump() if active else None,
            "counts": {
                "lessons": l_repo.count_by_profile(p_id),
                "strategies": len(s_repo.list_by_profile(p_id)),
                "experiences": e_repo.count_by_profile(p_id),
            },
            "connectors": {
                "opencode": opencode_conn.get_status(),
                "gemini": gemini_conn.get_status(),
            },
        }

    # 2. Profiles Management
    @app.get("/api/profiles")
    def list_profiles():
        return [p.model_dump() for p in p_repo.list_all()]

    @app.post("/api/profiles")
    def create_profile(req: ProfileCreateRequest):
        manifest = mgr.create_profile(
            name=req.name,
            description=req.description,
            domains=req.domains,
            technologies=req.technologies,
            activate=req.activate,
        )
        return manifest.model_dump()

    @app.post("/api/profiles/{identifier}/activate")
    def activate_profile(identifier: str):
        success = mgr.activate_profile(identifier)
        if not success:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"status": "activated", "profile": identifier}

    # 3. Knowledge Inspection
    @app.get("/api/lessons")
    def list_lessons(profile_id: Optional[str] = None):
        if not profile_id:
            active = p_repo.get_active()
            profile_id = active.profile_id if active else "default"
        lessons = l_repo.list_by_profile(profile_id)
        return [l.model_dump() for l in lessons]

    @app.get("/api/strategies")
    def list_strategies(profile_id: Optional[str] = None):
        if not profile_id:
            active = p_repo.get_active()
            profile_id = active.profile_id if active else "default"
        strategies = s_repo.list_by_profile(profile_id)
        return [s.model_dump() for s in strategies]

    @app.get("/api/experiences")
    def list_experiences(profile_id: Optional[str] = None, limit: int = 50):
        if not profile_id:
            active = p_repo.get_active()
            profile_id = active.profile_id if active else "default"
        experiences = e_repo.list_by_profile(profile_id, limit=limit)
        return [e.model_dump() for e in experiences]

    @app.get("/api/benchmarks")
    def list_benchmarks(profile_id: Optional[str] = None):
        if not profile_id:
            active = p_repo.get_active()
            profile_id = active.profile_id if active else "default"
        return b_repo.get_metrics(profile_id)

    # 4. Context Query Endpoint
    @app.post("/api/query")
    def query_context(req: QueryRequest):
        active = p_repo.get_active()
        p_name = active.name if active else "Default"
        p_id = active.profile_id if active else "default"

        scored = engine.retrieve_relevant_lessons(
            task_description=req.task_description,
            project_id=req.project_id,
            domain=req.domain,
            technologies=req.technologies,
            profile_id=p_id,
        )
        advisory_md = assembler.assemble(scored, profile_name=p_name)
        return {
            "advisory_markdown": advisory_md,
            "matched_count": len(scored),
            "lessons": [
                {"lesson": l.model_dump(), "score": round(score, 3)}
                for l, score in scored
            ],
        }

    # 5. Ingestion Endpoint
    @app.post("/api/events")
    def ingest_event(event_dict: Dict[str, Any]):
        normalized = collector.ingest_raw_event(event_dict)
        return {"status": "ingested", "event_id": normalized.id, "type": normalized.event_type.value}

    # 6. Benchmark Trigger
    @app.post("/api/benchmark/run")
    def run_benchmark(req: BenchmarkRunRequest):
        active = p_repo.get_active()
        p_id = active.profile_id if active else "default"
        runner = BenchmarkSuiteRunner(engine, b_repo)
        metrics = runner.run_suite(suite_name=req.suite, profile_id=p_id, agent_mode=req.mode)
        return metrics.model_dump()

    # =========================================================================
    # 7. Experience Inspector & Profile Analytics Endpoints
    # =========================================================================

    @app.get("/api/inspector/profiles")
    def inspector_list_profiles():
        """List high-level summary and health metrics for all stored profiles."""
        summaries = []
        for p in p_repo.list_all():
            summaries.append(inspector.get_profile_summary(p.profile_id).model_dump())
        return summaries

    @app.get("/api/inspector/profile/{identifier}")
    def inspector_get_profile(identifier: str):
        """Get complete summary and inspection metrics for a specific profile."""
        try:
            summary = inspector.get_profile_summary(identifier)
            return summary.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/inspector/archive/{identifier}")
    def inspector_inspect_archive(identifier: str):
        """Inspect the real .vxp archive corresponding to an existing profile."""
        profile = p_repo.get_by_id(identifier) or p_repo.get_by_name(identifier)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{identifier}' not found.")

        # Check exports_dir or profiles_dir
        archive_path = cfg.exports_dir / f"{profile.name}.vxp"
        if not archive_path.is_file():
            archive_path = cfg.profiles_dir / f"{profile.name}.vxp"

        if archive_path.is_file():
            res = inspector.inspect_archive(archive_path)
            return res.model_dump()

        # If archive not yet exported to disk, package in-memory to measure real entries and compression
        lessons = l_repo.list_by_profile(profile.profile_id, active_only=False)
        strategies = s_repo.list_by_profile(profile.profile_id)
        benchmarks = b_repo.get_metrics(profile.profile_id) if b_repo else []

        package = ProfilePackage(
            manifest=profile,
            lessons=lessons,
            strategies=strategies,
            preferences={},
            benchmarks=benchmarks,
        )

        temp_export = cfg.exports_dir / f"{profile.name}.vxp"
        mgr.archive_format.pack_to_vxp(package, temp_export)
        res = inspector.inspect_archive(temp_export)
        return res.model_dump()

    @app.post("/api/inspector/archive/inspect-file")
    def inspector_inspect_file(req: ArchiveInspectFileRequest):
        """Inspect any .vxp archive file on disk with optional password for encrypted profiles."""
        if not req.file_path:
            raise HTTPException(status_code=400, detail="file_path is required")
        target_path = Path(req.file_path)
        if not target_path.is_file():
            raise HTTPException(status_code=404, detail=f"Archive file not found: {req.file_path}")

        res = inspector.inspect_archive(target_path, password=req.password)
        return res.model_dump()

    @app.get("/api/inspector/expertise/{identifier}")
    def inspector_expertise(identifier: str):
        """Calculate multi-dimensional expertise (observed activity vs verified competence)."""
        try:
            analytics = inspector.calculate_expertise(identifier)
            return analytics.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/inspector/views/{identifier}")
    def inspector_views(
        identifier: str,
        query: str = "",
        scope: str = "",
        status: str = "",
        domain: str = "",
        category: str = "",
    ):
        """Searchable and filterable views for lessons, strategies, projects, tech, prefs, and benchmarks."""
        try:
            views_data = inspector.get_searchable_views(
                identifier=identifier,
                query=query,
                scope=scope,
                status=status,
                domain=domain,
                category=category,
            )
            return views_data
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/inspector/record/{record_type}/{record_id}")
    def inspector_record_detail(record_type: str, record_id: str):
        """Get deep provenance, evidence, confidence, outcome history, and contradictions for a record."""
        try:
            detail = inspector.get_record_detail(record_type, record_id)
            return detail.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/inspector/storage")
    def inspector_storage(profile_id: Optional[str] = None):
        """Return system storage analytics across archive, uncompressed, database, cache, and RAM."""
        analytics = inspector.get_storage_analytics(profile_id)
        return analytics.model_dump()

    @app.get("/api/inspector/versions/{identifier}/compare")
    def inspector_compare_versions(identifier: str, version_a: str, version_b: str):
        """Compare two version checkpoints and compute real additions, updates, removals, and rollbacks."""
        try:
            diff = inspector.compare_versions(identifier, version_a, version_b)
            return diff.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/inspector/timeline/{identifier}")
    def inspector_timeline(identifier: str):
        """Return chronological timeline of version checkpoints and expertise growth."""
        try:
            timeline = inspector.get_expertise_timeline(identifier)
            return [t.model_dump() for t in timeline]
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/inspector/lessons/{lesson_id}/modify")
    def inspector_modify_lesson(lesson_id: str, req: LessonModifyRequest):
        """Safely modify a lesson with explicit user confirmation, recording a version checkpoint."""
        try:
            updated = inspector.modify_lesson_safely(
                lesson_id=lesson_id,
                updates=req.updates,
                confirm=req.confirm,
                reason=req.reason,
            )
            return updated.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/inspector/lessons/{lesson_id}")
    def inspector_delete_lesson(lesson_id: str, req: DeleteConfirmRequest):
        """Safely delete a lesson with explicit user confirmation, recording a version checkpoint."""
        try:
            success = inspector.delete_lesson_safely(lesson_id=lesson_id, confirm=req.confirm)
            if not success:
                raise HTTPException(status_code=404, detail="Lesson not found")
            return {"status": "deleted", "lesson_id": lesson_id}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/inspector/profiles/{identifier}")
    def inspector_delete_profile(identifier: str, req: DeleteConfirmRequest):
        """Safely delete a profile with explicit user confirmation."""
        try:
            success = inspector.delete_profile_safely(identifier=identifier, confirm=req.confirm)
            if not success:
                raise HTTPException(status_code=404, detail="Profile not found")
            return {"status": "deleted", "profile": identifier}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # 8. Dashboard Static Files

    static_dir = Path(__file__).parent.parent / "dashboard" / "static"
    if static_dir.is_dir():
        @app.get("/")
        def serve_index():
            return FileResponse(static_dir / "index.html")

        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app
