"""Command-line interface for InsightBot."""

import secrets
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from insightbot.config import get_settings
from insightbot.flows.worker import WorkerService
from insightbot.infra.migrations import IndexCollisionError, apply_migrations
from insightbot.infra.mongo import check_mongo_connection, get_mongo_client
from insightbot.models.user import Role, UserStatus
from insightbot.modules.deduplication import DeduplicationEngine, DeduplicationService
from insightbot.modules.ingestion.service import IngestionService
from insightbot.modules.nlp import (
    EventTimeSplitter,
    MultilingualEvaluator,
    NLPService,
    load_gold_corpus,
    load_model_manifest,
)
from insightbot.modules.sources.registry import (
    load_sources_from_yaml,
    sync_sources_to_db,
    validate_sources_config,
)
from insightbot.modules.stories import (
    StoryClusteringEngine,
    StoryService,
)
from insightbot.repositories.source_repository import SourceRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthenticationError, AuthService

app = typer.Typer(
    name="insightbot",
    help="InsightBot - Multilingual news intelligence platform CLI.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="Configuration inspection and initialization.")
db_app = typer.Typer(help="Database migration and validation commands.")
admin_app = typer.Typer(help="Administrator management commands.")
sources_app = typer.Typer(help="Source definition and validation commands.")
models_app = typer.Typer(help="Model manifest and local weight lifecycle management.")
eval_app = typer.Typer(help="Multilingual evaluation, gold corpus, and quality reports.")
dedup_app = typer.Typer(help="Deduplication and syndication analysis commands.")
stories_app = typer.Typer(help="Story clusters, lifecycle, and event timeline commands.")

app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(admin_app, name="admin")
app.add_typer(sources_app, name="sources")
app.add_typer(models_app, name="models")
app.add_typer(eval_app, name="eval")
app.add_typer(dedup_app, name="dedup")
app.add_typer(stories_app, name="stories")


@config_app.command(name="init")
def config_init(
    local: bool = typer.Option(
        False, "--local", help="Initialize local development configuration."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing configuration file if present."
    ),
) -> None:
    """Initialize environment and directories without overwriting existing secrets."""
    env_file = Path(".env")
    if env_file.exists() and not force:
        typer.echo(
            f"[INFO] '{env_file}' already exists. Skipping creation (use --force to overwrite)."
        )
    else:
        generated_secret = secrets.token_hex(32)
        env_content = f"""# InsightBot Environment Configuration
INSIGHTBOT_ENV=development
INSIGHTBOT_HOST=127.0.0.1
INSIGHTBOT_PORT=8000
INSIGHTBOT_MONGO_URI=mongodb://127.0.0.1:27017
INSIGHTBOT_MONGO_DB=insightbot
INSIGHTBOT_SECRET_KEY={generated_secret}
INSIGHTBOT_TIMEZONE=UTC
INSIGHTBOT_SEARCH_BACKEND=basic
INSIGHTBOT_ENABLE_LLM=false
PREFECT_API_URL=http://127.0.0.1:4200/api
HF_HUB_OFFLINE=1
"""
        env_file.write_text(env_content, encoding="utf-8")
        typer.echo(f"[SUCCESS] Created '{env_file}' with fresh generated cryptographic secret key.")

    # Ensure required base directories exist
    settings = get_settings()
    settings.raw_storage_path.mkdir(parents=True, exist_ok=True)
    settings.export_storage_path.mkdir(parents=True, exist_ok=True)
    Path("configs").mkdir(parents=True, exist_ok=True)
    typer.echo("[SUCCESS] Ensured data directories exist (data/raw, data/exports, configs).")


@config_app.command(name="check")
def config_check(
    wait_services: bool = typer.Option(
        False, "--wait-services", help="Wait for dependent services (MongoDB)."
    ),
    timeout: int = typer.Option(
        10, "--timeout", help="Timeout in seconds when waiting for services."
    ),
) -> None:
    """Validate runtime configuration, directory permissions, and service readiness."""
    settings = get_settings()
    typer.echo(f"InsightBot Environment: {settings.env}")
    typer.echo(f"MongoDB URI: {settings.mongo_uri} (Database: {settings.mongo_db})")
    typer.echo(f"Raw Storage: {settings.raw_storage_path}")
    typer.echo(f"Timezone: {settings.timezone}")

    issues = settings.validate_runtime()
    if issues:
        typer.echo("\n[ERROR] Configuration issues detected:")
        for issue in issues:
            typer.echo(f" - {issue}")
        sys.exit(1)

    typer.echo("[OK] Directory access and basic settings validated.")

    if wait_services:
        typer.echo(f"Waiting for services readiness (timeout: {timeout}s)...")
        start_time = time.time()
        connected = False
        last_msg = ""
        while time.time() - start_time < timeout:
            ok, msg = check_mongo_connection(settings)
            last_msg = msg
            if ok:
                connected = True
                break
            time.sleep(1.5)

        if connected:
            typer.echo(f"[OK] {last_msg}")
        else:
            typer.echo(f"[ERROR] Service check failed after {timeout}s: {last_msg}")
            sys.exit(1)
    else:
        ok, msg = check_mongo_connection(settings)
        if ok:
            typer.echo(f"[OK] {msg}")
        else:
            typer.echo(f"[WARN] {msg}")


@db_app.command(name="migrate")
def db_migrate(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report planned index and schema changes without applying."
    ),
    apply: bool = typer.Option(False, "--apply", help="Execute migrations and create indexes."),
    database: str = typer.Option("", "--database", help="Target database name (overrides config)."),
) -> None:
    """Database migration and index creation tool (T02)."""
    if not dry_run and not apply:
        typer.echo("Error: Please specify either --dry-run or --apply.")
        sys.exit(1)

    settings = get_settings()
    target_db_name = database if database else settings.mongo_db
    typer.echo(
        f"[INFO] Connecting to MongoDB: {settings.mongo_uri} (target db: '{target_db_name}')..."
    )

    ok, msg = check_mongo_connection(settings)
    if not ok:
        typer.echo(f"[ERROR] Cannot perform migrations: {msg}")
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[target_db_name]

    try:
        report = apply_migrations(db, dry_run=dry_run)
        if dry_run:
            typer.echo("[SUCCESS] Migration Dry-Run Complete:")
            typer.echo(f" - Planned index creations: {report['planned_creations']}")
            typer.echo(f" - Already present indexes: {report['already_present']}")
            for item in report["details"]:
                typer.echo(f"   * {item['collection']}.{item['index']} (unique={item['unique']})")
        else:
            typer.echo("[SUCCESS] Migration Applied Successfully:")
            typer.echo(f" - Created indexes: {report['created_count']}")
            typer.echo(f" - Already present indexes: {report['already_present_count']}")
            for idx in report["created_indexes"]:
                typer.echo(f"   * Created: {idx}")
    except IndexCollisionError as exc:
        typer.echo("\n[CRITICAL ERROR] Migration stopped to protect data integrity:")
        typer.echo(f" - {exc}")
        sys.exit(1)
    finally:
        client.close()


@admin_app.command(name="create")
def admin_create(
    username: Optional[str] = typer.Option(
        None, "--username", "-u", help="Administrator username."
    ),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Administrator email address."),
) -> None:
    """Interactively provision administrator account without predefined seeds (T03)."""
    settings = get_settings()
    ok, msg = check_mongo_connection(settings)
    if not ok:
        typer.echo(f"[ERROR] Cannot connect to MongoDB: {msg}")
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)

    try:
        active_admins = user_repo.count_active_admins()
        if active_admins > 0:
            typer.echo(f"[INFO] Notice: {active_admins} active administrator(s) already exist.")
            if not typer.confirm("Do you wish to create an additional administrator?"):
                typer.echo("Operation cancelled.")
                return

        if not username:
            username = typer.prompt("Admin username").strip()
        if not email:
            email_input = typer.prompt("Admin email (optional)", default="").strip()
            email = email_input if email_input else None

        password = typer.prompt("Admin password (min 8 chars)", hide_input=True)
        password_confirm = typer.prompt("Confirm admin password", hide_input=True)

        if password != password_confirm:
            typer.echo("[ERROR] Passwords do not match.")
            sys.exit(1)

        user = auth_service.register(
            username=username,
            password=password,
            email=email,
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
        )
        typer.echo(
            f"[SUCCESS] Administrator '{user.username}' created successfully (ID: {user.user_id})."
        )
    except AuthenticationError as exc:
        typer.echo(f"[ERROR] Failed to create administrator: {exc}")
        sys.exit(1)
    finally:
        client.close()


@sources_app.command(name="validate")
def sources_validate(
    config: Path = typer.Option(
        Path("configs/sources.yaml"), "--config", help="Path to sources YAML file."
    ),
    sync: bool = typer.Option(False, "--sync", help="Synchronize validated sources to MongoDB."),
) -> None:
    """Validate source definitions against schema (T04)."""
    typer.echo(f"[INFO] Validating sources configuration: '{config}'...")
    is_valid, issues = validate_sources_config(config)
    if not is_valid:
        typer.echo("[ERROR] Source configuration validation failed:")
        for issue in issues:
            typer.echo(f" - {issue}")
        sys.exit(1)

    sources = load_sources_from_yaml(config)
    typer.echo(f"[SUCCESS] Source configuration is valid. Registered sources: {len(sources)}.")
    for s in sources:
        typer.echo(f"   * [{s.source_id}] {s.name} ({s.language}) - Enabled: {s.enabled}")

    if sync:
        settings = get_settings()
        ok, msg = check_mongo_connection(settings)
        if not ok:
            typer.echo(f"[WARN] Cannot sync to MongoDB: {msg}")
            return
        client = get_mongo_client(settings)
        db = client[settings.mongo_db]
        repo = SourceRepository(db)
        synced = sync_sources_to_db(sources, repo)
        typer.echo(f"[SUCCESS] Synchronized {synced} sources into database.")
        client.close()


@app.command(name="ingest")
def ingest(
    source: str = typer.Option(..., "--source", help="Approved source identifier."),
    limit: int = typer.Option(10, "--limit", help="Maximum URLs to fetch."),
    ignore_disabled: bool = typer.Option(
        False, "--ignore-disabled", help="Override disabled flag for testing."
    ),
) -> None:
    """Fetch new content from an approved publisher source (T04)."""
    settings = get_settings()
    sources_config = settings.sources_config_path
    if not sources_config.exists():
        typer.echo(f"[ERROR] Sources file '{sources_config}' not found.")
        sys.exit(1)

    sources = load_sources_from_yaml(sources_config)
    target_source = next((s for s in sources if s.source_id == source), None)
    if not target_source:
        typer.echo(f"[ERROR] Source '{source}' not found in registry. Approved sources:")
        for s in sources:
            typer.echo(f" - {s.source_id}")
        sys.exit(1)

    if not target_source.enabled and not ignore_disabled:
        typer.echo(
            f"[WARN] Source '{target_source.name}' ({target_source.source_id}) is currently DISABLED by policy."
        )
        typer.echo(
            "       Approval and policy review are required before live collection. Use --ignore-disabled for bounded testing."
        )
        return

    ok, msg = check_mongo_connection(settings)
    if not ok:
        typer.echo(f"[ERROR] Cannot connect to MongoDB: {msg}")
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    service = IngestionService(db=db, settings=settings)

    typer.echo(f"[INFO] Ingesting source '{target_source.name}' (limit: {limit})...")
    report = service.ingest_source(target_source, limit=limit, ignore_disabled=ignore_disabled)

    if report.status == "skipped_disabled":
        typer.echo(f"[WARN] {report.message}")
    else:
        typer.echo(f"[SUCCESS] {report.message}")

    client.close()


@app.command(name="process")
def process(
    pending: bool = typer.Option(True, "--pending", help="Process pending unanalyzed articles."),
    limit: int = typer.Option(20, "--limit", help="Batch size limit."),
) -> None:
    """Run processing flows on ingested articles (T06/T12)."""
    settings = get_settings()
    ok, msg = check_mongo_connection(settings)
    if not ok:
        typer.echo(f"[ERROR] Cannot connect to MongoDB: {msg}")
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    worker = WorkerService(db=db, settings=settings)

    typer.echo(f"[INFO] Worker '{worker.worker_id}' processing pending jobs (limit: {limit})...")
    count = worker.run_bounded(max_jobs=limit)
    typer.echo(f"[SUCCESS] Processed {count} job(s) from pending queue.")
    client.close()


# --- Models Commands ---


@models_app.command(name="list")
def models_list(
    manifest_path: str = typer.Option(
        "configs/models.yaml", "--manifest", help="Path to manifest."
    ),
) -> None:
    """List pinned models from manifest with roles, licenses, and local status."""
    try:
        manifest = load_model_manifest(manifest_path)
    except Exception as exc:
        typer.echo(f"[ERROR] Failed to load manifest: {exc}")
        sys.exit(1)

    nlp = NLPService(manifest_path=manifest_path)
    typer.echo("=" * 80)
    typer.echo(f"  InsightBot Model Manifest v{manifest.version} (Cache: {manifest.cache_dir})")
    typer.echo("=" * 80)
    typer.echo(f"{'MODEL ID':<36} {'ROLE':<16} {'STATUS':<12} {'LICENSE':<10} {'LOCAL'}")
    typer.echo("-" * 80)

    for m in manifest.models:
        is_local = "YES" if nlp.is_model_downloaded(m.model_id) else "NO"
        status_str = m.status.value.upper()
        role_str = m.role.value
        typer.echo(f"{m.model_id:<36} {role_str:<16} {status_str:<12} {m.license:<10} {is_local}")
    typer.echo("-" * 80)


@models_app.command(name="info")
def models_info(
    model_id: str = typer.Argument(
        ..., help="Model identifier (e.g. intfloat/multilingual-e5-small)"
    ),
    manifest_path: str = typer.Option(
        "configs/models.yaml", "--manifest", help="Path to manifest."
    ),
) -> None:
    """Display comprehensive technical specifications and limits for a model."""
    try:
        manifest = load_model_manifest(manifest_path)
    except Exception as exc:
        typer.echo(f"[ERROR] Failed to load manifest: {exc}")
        sys.exit(1)

    model = manifest.get_model(model_id)
    if not model:
        typer.echo(f"[ERROR] Model '{model_id}' not found in manifest.")
        sys.exit(1)

    typer.echo(f"\n--- Model Specification: {model.name} ---")
    typer.echo(f"ID:           {model.model_id}")
    typer.echo(f"Role:         {model.role.value}")
    typer.echo(f"Status:       {model.status.value.upper()}")
    typer.echo(f"License:      {model.license}")
    typer.echo(f"Revision:     {model.revision}")
    typer.echo(f"SHA256:       {model.sha256}")
    typer.echo(f"Dimensions:   {model.dimensions}")
    typer.echo(f"Max Context:  {model.max_tokens} tokens")
    typer.echo(f"Est. Memory:  {model.memory_mb} MB")
    typer.echo(f"Languages:    {', '.join(model.supported_languages)}")
    if model.recommended_prefix:
        typer.echo(f"Prefixes:     {model.recommended_prefix}")
    if model.chunking:
        typer.echo(
            f"Chunking:     {model.chunking.target_tokens_min}-{model.chunking.target_tokens_max} tokens "
            f"(overlap: {model.chunking.overlap_tokens})"
        )
    if model.taxonomy:
        typer.echo(f"Taxonomy:     {', '.join(model.taxonomy)}")
    typer.echo(f"Description:  {model.description}\n")


@models_app.command(name="download")
def models_download(
    model_id: Optional[str] = typer.Option(
        None, "--model", help="Optional specific model ID to download."
    ),
    manifest_path: str = typer.Option(
        "configs/models.yaml", "--manifest", help="Path to manifest."
    ),
) -> None:
    """
    Prepare offline local cache directory for approved models.
    Enforces local safety and prevents dynamic request-time downloads.
    """
    try:
        manifest = load_model_manifest(manifest_path)
    except Exception as exc:
        typer.echo(f"[ERROR] Failed to load manifest: {exc}")
        sys.exit(1)

    cache_dir = Path(manifest.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    targets = [manifest.get_model(model_id)] if model_id else manifest.models
    targets = [m for m in targets if m is not None]

    for m in targets:
        m_dir = cache_dir / m.model_id.replace("/", "--")
        m_dir.mkdir(parents=True, exist_ok=True)
        meta_file = m_dir / "manifest_spec.json"
        meta_file.write_text(m.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"[INFO] Initialized local cache path for '{m.model_id}' at: {m_dir}")

    typer.echo("[SUCCESS] Model cache directories initialized. HF_HUB_OFFLINE=1 ready.")


# --- Evaluation Commands ---


@eval_app.command(name="run")
def eval_run(
    corpus_path: str = typer.Option(
        "data/eval/gold_corpus.json", "--corpus", help="Path to gold dataset."
    ),
    split: str = typer.Option(
        "test", "--split", help="Target split to evaluate: 'test', 'validation', or 'all'."
    ),
) -> None:
    """Run multilingual evaluation on the gold benchmark corpus with event-time splitting."""
    try:
        samples = load_gold_corpus(corpus_path)
    except Exception as exc:
        typer.echo(f"[ERROR] Failed to load evaluation corpus: {exc}")
        sys.exit(1)

    split_result = EventTimeSplitter.split(samples)
    if split == "test":
        target_samples = split_result.test
    elif split == "validation":
        target_samples = split_result.validation
    else:
        target_samples = samples

    typer.echo(
        f"[INFO] Loaded {len(samples)} gold samples across {len(set(s.event_id for s in samples))} events."
    )
    typer.echo(
        f"[INFO] Event-Time Split: {len(split_result.train)} train, "
        f"{len(split_result.validation)} validation, {len(split_result.test)} test."
    )
    typer.echo(f"[INFO] Evaluating {len(target_samples)} samples on split='{split}'...")

    nlp = NLPService()
    evaluator = MultilingualEvaluator(confidence_threshold=0.65)

    def predict_wrapper(text: str, language: str) -> tuple[str, float]:
        res = nlp.classify_article("eval-test", 1, "", text, language=language)
        return res["category"], res["confidence"]

    report = evaluator.evaluate(target_samples, predict_wrapper)

    typer.echo("\n" + "=" * 80)
    typer.echo("               MULTILINGUAL EVALUATION BENCHMARK REPORT")
    typer.echo("=" * 80)
    typer.echo(
        f"{'LANGUAGE':<10} {'SAMPLES':<10} {'COVERAGE':<12} {'MACRO-F1':<12} {'LAT-P95(ms)':<14} {'GATE'}"
    )
    typer.echo("-" * 80)

    for lang, m in report.by_language.items():
        gate_str = "PASS" if m.passed_gate else "FAIL"
        cov_pct = f"{m.coverage_rate * 100:.1f}%"
        f1_str = f"{m.macro_f1:.3f}"
        typer.echo(
            f"{lang:<10} {m.total_samples:<10} {cov_pct:<12} {f1_str:<12} {m.latency_p95_ms:<14} {gate_str}"
        )

    typer.echo("-" * 80)
    ov = report.overall
    ov_gate = "PASS" if ov.passed_gate else "FAIL"
    ov_cov = f"{ov.coverage_rate * 100:.1f}%"
    typer.echo(
        f"{'OVERALL':<10} {ov.total_samples:<10} {ov_cov:<12} {ov.macro_f1:.3f} {ov.latency_p95_ms:<14} {ov_gate}"
    )
    typer.echo("=" * 80)
    typer.echo(f"Acceptance Criteria (Macro-F1 >= 0.80 & Coverage >= 80%): {ov_gate}\n")


# --- Deduplication Commands ---


@dedup_app.command(name="run")
def dedup_run(
    limit: int = typer.Option(50, "--limit", help="Maximum un-deduplicated articles to scan."),
) -> None:
    """Run deduplication on pending ingested articles in database."""
    settings = get_settings()
    ok, msg = check_mongo_connection(settings)
    if not ok:
        typer.echo(f"[ERROR] Cannot connect to MongoDB: {msg}")
        sys.exit(1)

    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    service = DeduplicationService(db)

    typer.echo(f"[INFO] Scanning pending articles for duplicates (limit: {limit})...")
    count = service.run_batch_deduplication(limit=limit)
    typer.echo(f"[SUCCESS] Scanned {count} article(s) and persisted duplicate relationships.")
    client.close()


@dedup_app.command(name="eval")
def dedup_eval() -> None:
    """Evaluate deduplication precision/recall and verify 'similar headlines / different numbers' defense."""
    from datetime import datetime, timezone

    from insightbot.models.article import Article, compute_content_hash

    detector = DeduplicationEngine(near_duplicate_threshold=0.85, temporal_window_hours=72.0)
    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    # Evaluation Pairs: (article_a, article_b, expected_is_duplicate, description)
    test_cases: list[tuple[Article, Article, bool, str]] = []

    # 1. Exact content hash syndication
    wire_body = "أعلنت وزارة الطاقة اليوم الأحد اتفاقاً جديداً لزيادة صادرات الغاز الطبيعي المسال (رويترز)."
    a1 = Article(
        article_id="eval-1a",
        source_id="reuters_ar",
        canonical_url="https://reuters.com/1",
        original_url="https://reuters.com/1",
        resolved_url="https://reuters.com/1",
        title="اتفاق طاقة جديد لزيادة صادرات الغاز المسال",
        body_text=wire_body,
        content_hash=compute_content_hash(wire_body),
        published_at=now,
    )
    a2 = Article(
        article_id="eval-1b",
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/1",
        original_url="https://aljazeera.net/1",
        resolved_url="https://aljazeera.net/1",
        title="رويترز: اتفاق طاقة جديد لزيادة صادرات الغاز",
        body_text=wire_body,
        content_hash=compute_content_hash(wire_body),
        published_at=now,
    )
    test_cases.append((a1, a2, True, "Exact Hash Wire Syndication"))

    # 2. Near-duplicate with high Jaccard similarity (> 0.88)
    near_body_1 = "أغلقت مؤشرات الأسهم الأوروبية على ارتفاع طفيف في ختام تداولات الأسبوع مدعومة بمكاسب قطاع التكنولوجيا وأسهم البنوك."
    near_body_2 = "أغلقت مؤشرات الأسهم الأوروبية على ارتفاع طفيف في ختام تداولات الأسبوع مدعومة بمكاسب قطاع التكنولوجيا وأسهم البنوك والمصارف الكبرى."
    b1 = Article(
        article_id="eval-2a",
        source_id="bbc_ar",
        canonical_url="https://bbc.com/ar/stocks",
        original_url="https://bbc.com/ar/stocks",
        resolved_url="https://bbc.com/ar/stocks",
        title="الأسهم الأوروبية تختتم الأسبوع على ارتفاع طفيف",
        body_text=near_body_1,
        content_hash=compute_content_hash(near_body_1),
        published_at=now,
    )
    b2 = Article(
        article_id="eval-2b",
        source_id="alarabiya_ar",
        canonical_url="https://alarabiya.net/stocks",
        original_url="https://alarabiya.net/stocks",
        resolved_url="https://alarabiya.net/stocks",
        title="الأسهم الأوروبية ترتفع في ختام تعاملات الأسبوع",
        body_text=near_body_2,
        content_hash=compute_content_hash(near_body_2),
        published_at=now,
    )
    test_cases.append((b1, b2, True, "Near-Duplicate High Shingle Overlap"))

    # 3. CRITICAL DEFECT TEST: Similar Arabic headlines with DIFFERENT numbers (Must NOT collapse!)
    c1 = Article(
        article_id="eval-3a",
        source_id="source_a",
        canonical_url="https://news-a.com/crash",
        original_url="https://news-a.com/crash",
        resolved_url="https://news-a.com/crash",
        title="مصرع 12 شخصاً وإصابة آخرين في حادث تصادم حافلة قرب القاهرة",
        body_text="لقي 12 شخصاً مصرعهم اليوم في حادث سير مروع وقع على الطريق الصحراوي.",
        content_hash=compute_content_hash("لقي 12 شخصاً مصرعهم اليوم في حادث سير مروع وقع على الطريق الصحراوي."),
        published_at=now,
    )
    c2 = Article(
        article_id="eval-3b",
        source_id="source_b",
        canonical_url="https://news-b.com/crash",
        original_url="https://news-b.com/crash",
        resolved_url="https://news-b.com/crash",
        title="مصرع 45 شخصاً وإصابة آخرين في حادث تصادم حافلة قرب القاهرة",
        body_text="لقي 45 شخصاً مصرعهم اليوم في حادث سير مروع وقع على الطريق الصحراوي في حصيلة جديدة.",
        content_hash=compute_content_hash("لقي 45 شخصاً مصرعهم اليوم في حادث سير مروع وقع على الطريق الصحراوي في حصيلة جديدة."),
        published_at=now,
    )
    test_cases.append((c1, c2, False, "Similar Arabic Headline With Divergent Numbers (12 vs 45)"))

    # 4. CRITICAL DEFECT TEST: Similar English headlines with DIFFERENT numbers (Must NOT collapse!)
    d1 = Article(
        article_id="eval-4a",
        source_id="reuters_en",
        canonical_url="https://reuters.com/en/flood-10",
        original_url="https://reuters.com/en/flood-10",
        resolved_url="https://reuters.com/en/flood-10",
        title="At least 10 killed in flash floods following heavy rainfall",
        body_text="Authorities reported at least 10 fatalities after severe downpours swept through rural regions.",
        content_hash=compute_content_hash("Authorities reported at least 10 fatalities after severe downpours swept through rural regions."),
        published_at=now,
    )
    d2 = Article(
        article_id="eval-4b",
        source_id="bbc_en",
        canonical_url="https://bbc.com/en/flood-70",
        original_url="https://bbc.com/en/flood-70",
        resolved_url="https://bbc.com/en/flood-70",
        title="At least 70 killed in flash floods following heavy rainfall",
        body_text="Authorities reported at least 70 fatalities after severe downpours swept through rural regions in latest update.",
        content_hash=compute_content_hash("Authorities reported at least 70 fatalities after severe downpours swept through rural regions in latest update."),
        published_at=now,
    )
    test_cases.append((d1, d2, False, "Similar English Headline With Divergent Numbers (10 vs 70)"))

    # 5. Distinct reports in completely different domains
    e1 = Article(
        article_id="eval-5a",
        source_id="bbc_ar",
        canonical_url="https://bbc.com/tech",
        original_url="https://bbc.com/tech",
        resolved_url="https://bbc.com/tech",
        title="إطلاق تحديث برمجي جديد لأنظمة الحوسبة السحابية",
        body_text="أطلقت الشركة المتخصصة نظاماً جديداً لإدارة قواعد البيانات والشبكات الذكية.",
        content_hash=compute_content_hash("أطلقت الشركة المتخصصة نظاماً جديداً لإدارة قواعد البيانات والشبكات الذكية."),
        published_at=now,
    )
    test_cases.append((a1, e1, False, "Completely Distinct Stories"))

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    typer.echo("\n" + "=" * 80)
    typer.echo("               DEDUPLICATION ENGINE EVALUATION REPORT")
    typer.echo("=" * 80)
    typer.echo(f"{'TEST CASE':<52} {'EXPECTED':<10} {'PRED':<10} {'RESULT'}")
    typer.echo("-" * 80)

    for art_a, art_b, expected_dup, desc in test_cases:
        rel = detector.compare(art_a, art_b)
        pred_dup = rel is not None

        if expected_dup and pred_dup:
            tp += 1
            verdict = "PASS (TP)"
        elif not expected_dup and not pred_dup:
            tn += 1
            verdict = "PASS (TN)"
        elif not expected_dup and pred_dup:
            fp += 1
            verdict = "FAIL (FP)"
        else:
            fn += 1
            verdict = "FAIL (FN)"

        exp_str = "DUP" if expected_dup else "DISTINCT"
        pred_str = "DUP" if pred_dup else "DISTINCT"
        typer.echo(f"{desc:<52} {exp_str:<10} {pred_str:<10} {verdict}")

    typer.echo("-" * 80)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    prec_pct = f"{precision * 100:.1f}%"
    rec_pct = f"{recall * 100:.1f}%"

    passed_gate = precision >= 0.98 and recall >= 0.80
    gate_str = "PASS" if passed_gate else "FAIL"

    typer.echo(f"PRECISION: {prec_pct:<10} (Target: >= 98.0%)")
    typer.echo(f"RECALL:    {rec_pct:<10} (Target: >= 80.0%)")
    typer.echo(f"ZERO COLLAPSE OF DISTINCT REPORTS: {'VERIFIED' if fp == 0 else 'VIOLATED'}")
    typer.echo(f"ACCEPTANCE CRITERIA VERDICT:       {gate_str}")
    typer.echo("=" * 80 + "\n")


@stories_app.command(name="list")
def stories_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status (emerging, peak, declining, closed)"),
    limit: int = typer.Option(20, "--limit", help="Maximum stories to return"),
) -> None:
    """List stories with deterministic pagination and short projection (Defect A12)."""
    from insightbot.models.story import StoryStatus

    settings = get_settings()
    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    service = StoryService(db)

    status_enum = StoryStatus(status) if status else None
    items, _, total = service.list_stories(status=status_enum, limit=limit)

    typer.echo(f"\n[STORIES] Total stories: {total} (showing {len(items)})")
    typer.echo("-" * 90)
    typer.echo(f"{'STATUS':<12} {'ARTICLES':<10} {'SOURCES':<10} {'LEAD TITLE'}")
    typer.echo("-" * 90)
    for s in items:
        status_str = s.get("status", "unknown")
        art_count = s.get("article_count", 0)
        src_count = s.get("sources_count", 0)
        title = s.get("title", "")[:55]
        typer.echo(f"{status_str:<12} {art_count:<10} {src_count:<10} {title}")
    typer.echo("-" * 90 + "\n")
    client.close()


@stories_app.command(name="cluster")
def stories_cluster(
    limit: int = typer.Option(50, "--limit", help="Maximum unclustered articles to process"),
) -> None:
    """Batch cluster un-clustered articles into event stories."""
    settings = get_settings()
    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    service = StoryService(db)

    count = service.run_batch_clustering(limit=limit)
    typer.echo(f"[SUCCESS] Processed {count} article(s) into story clusters.")
    client.close()


@stories_app.command(name="eval")
def stories_eval() -> None:
    """
    Evaluate Story Clustering precision, recall, location guards,
    temporal cutoff guards, and chain-merge defenses.
    """
    from datetime import datetime, timedelta, timezone

    from insightbot.models.article import Article, compute_content_hash
    from insightbot.models.story import Story, StoryStatus

    engine = StoryClusteringEngine(
        headline_similarity_threshold=0.55,
        shingle_similarity_threshold=0.45,
        temporal_window_hours=72.0,
    )
    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    # Lead article of base story
    lead_body = "ضرب زلزال بقوة 6.3 درجات قبالة السواحل الشرقية لليابان صباح اليوم مما تسبب في إطلاق تحذيرات من تسونامي في طوكيو والمحافظات المجاورة."
    lead_art = Article(
        article_id="story-lead",
        source_id="nhk_en",
        canonical_url="https://nhk.or.jp/quake",
        original_url="https://nhk.or.jp/quake",
        resolved_url="https://nhk.or.jp/quake",
        title="زلزال بقوة 6.3 درجات يضرب السواحل الشرقية في طوكيو باليابان",
        body_text=lead_body,
        content_hash=compute_content_hash(lead_body),
        published_at=now,
    )

    base_story = Story(
        story_id="story-quake-japan",
        title=lead_art.title,
        status=StoryStatus.EMERGING,
        lead_article_id=lead_art.article_id,
        article_ids=[lead_art.article_id],
        sources=["nhk_en"],
        article_count=1,
        sources_count=1,
        first_article_at=now,
        last_article_at=now,
        primary_location="Japan",
        entities=["Japan", "Tokyo"],
        keywords=["زلزال", "درجات", "طوكيو", "اليابان", "تسونامي"],
        version=1,
    )

    # Test cases: (article, expected_membership, description)
    test_cases: list[tuple[Article, bool, str]] = []

    # 1. Valid event update within 3 hours from different source
    body_corrob = "أعلنت هيئة الأرصاد اليابانية أن زلزالا بقوة 6.3 درجات ضرب منطقة كانتو قرب طوكيو دون تسجيل إصابات بشرية خطيرة حتى اللحظة."
    art_corrob = Article(
        article_id="eval-corrob",
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/japan-quake",
        original_url="https://aljazeera.net/japan-quake",
        resolved_url="https://aljazeera.net/japan-quake",
        title="زلزال بقوة 6.3 درجات يضرب قرب العاصمة طوكيو في اليابان",
        body_text=body_corrob,
        content_hash=compute_content_hash(body_corrob),
        published_at=now + timedelta(hours=3),
    )
    test_cases.append((art_corrob, True, "Same Event Multi-source Corroboration"))

    # 2. Location Conflict Guard: Earthquake in Chile, not Japan!
    body_chile = "ضرب زلزال بقوة 6.3 درجات السواحل الوسطى في تشيلي ما دفع السلطات المحلية لإخلاء الشواطئ تحسبا لأمواج مد بحري."
    art_chile = Article(
        article_id="eval-chile",
        source_id="bbc_ar",
        canonical_url="https://bbc.com/chile-quake",
        original_url="https://bbc.com/chile-quake",
        resolved_url="https://bbc.com/chile-quake",
        title="زلزال بقوة 6.3 درجات يضرب السواحل في تشيلي",
        body_text=body_chile,
        content_hash=compute_content_hash(body_chile),
        published_at=now + timedelta(hours=5),
    )
    test_cases.append((art_chile, False, "Location Conflict Guard (Japan vs Chile)"))

    # 3. Temporal Cutoff Guard: Similar earthquake but 10 days later
    art_late = Article(
        article_id="eval-late",
        source_id="reuters_ar",
        canonical_url="https://reuters.com/japan-late",
        original_url="https://reuters.com/japan-late",
        resolved_url="https://reuters.com/japan-late",
        title="زلزال بقوة 6.3 درجات يضرب السواحل الشرقية في طوكيو باليابان مجددا",
        body_text=lead_body,
        content_hash=compute_content_hash(lead_body),
        published_at=now + timedelta(days=10),
    )
    test_cases.append((art_late, False, "Temporal Cutoff Guard (Delta > 72h)"))

    # 4. Chain-Merge Guard: Unrelated political article sharing only generic words
    body_unrelated = "عقد رئيس الوزراء في طوكيو اجتماعا حكوميا موسعا لمناقشة الميزانية السنوية ومخصصات التعليم والرعاية الصحية."
    art_unrelated = Article(
        article_id="eval-unrelated",
        source_id="asahi_en",
        canonical_url="https://asahi.com/politics",
        original_url="https://asahi.com/politics",
        resolved_url="https://asahi.com/politics",
        title="اجتماع حكومي موسع في طوكيو لمناقشة الميزانية السنوية",
        body_text=body_unrelated,
        content_hash=compute_content_hash(body_unrelated),
        published_at=now + timedelta(hours=2),
    )
    test_cases.append((art_unrelated, False, "Chain-Merge Defense (Unrelated Topic)"))

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    typer.echo("\n" + "=" * 80)
    typer.echo("               STORY CLUSTERING & EVENT LIFECYCLE EVALUATION")
    typer.echo("=" * 80)
    typer.echo(f"{'TEST CASE':<52} {'EXPECTED':<10} {'PRED':<10} {'RESULT'}")
    typer.echo("-" * 80)

    for art, expected, desc in test_cases:
        belongs, score, reason = engine.evaluate_membership(art, base_story, lead_art)
        if expected and belongs:
            tp += 1
            verdict = "PASS (TP)"
        elif not expected and not belongs:
            tn += 1
            verdict = "PASS (TN)"
        elif not expected and belongs:
            fp += 1
            verdict = "FAIL (FP)"
        else:
            fn += 1
            verdict = "FAIL (FN)"

        exp_str = "CLUSTER" if expected else "SEPARATE"
        pred_str = "CLUSTER" if belongs else "SEPARATE"
        typer.echo(f"{desc:<52} {exp_str:<10} {pred_str:<10} {verdict}")

    typer.echo("-" * 80)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    prec_pct = f"{precision * 100:.1f}%"
    rec_pct = f"{recall * 100:.1f}%"

    passed_gate = precision >= 0.90 and recall >= 0.80 and fp == 0
    gate_str = "PASS" if passed_gate else "FAIL"

    typer.echo(f"EVENT PRECISION:        {prec_pct:<10} (Target: >= 90.0%)")
    typer.echo(f"EVENT RECALL:           {rec_pct:<10} (Target: >= 80.0%)")
    typer.echo(f"LOCATION/CHAIN DEFENSE: {'VERIFIED' if fp == 0 else 'VIOLATED'}")
    typer.echo(f"ACCEPTANCE CRITERIA:    {gate_str}")
    typer.echo("=" * 80 + "\n")


if __name__ == "__main__":
    app()
