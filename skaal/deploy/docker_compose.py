"""Local Docker Compose artifact generator — for testing deployments locally."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skaal.deploy._deps import collect_user_packages
from skaal.deploy._render import render, to_pyproject_toml
from skaal.deploy.config import LocalStackDeployConfig
from skaal.deploy.push import write_meta

if TYPE_CHECKING:
    from skaal.plan import PlanFile


# ── Per-backend metadata for local services ───────────────────────────────────

_BACKENDS: dict[str, dict[str, Any]] = {
    "redis": {
        "class": "RedisBackend",
        "import": "from skaal.backends.redis_backend import RedisBackend",
        "service": "redis",
        "env_prefix": "SKAAL_REDIS_URL",
        "compose": {
            "service_name": "redis",
            "image": "redis:7-alpine",
            "ports": ["- '6379:6379'"],
            "environment": [],
            "depends_on": [],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "5s",
                "timeout": "3s",
                "retries": 5,
                "start_period": "10s",
            },
        },
    },
    "postgres": {
        "class": "PostgresBackend",
        "import": "from skaal.backends.postgres_backend import PostgresBackend",
        "service": "postgres",
        "env_prefix": "SKAAL_DB_DSN",
        "compose": {
            "service_name": "postgres",
            "image": "postgres:16-alpine",
            "ports": ["- '5432:5432'"],
            "environment": [
                "- POSTGRES_USER=skaal_user",
                "- POSTGRES_PASSWORD=skaal_pass",
                "- POSTGRES_DB=skaal_db",
            ],
            "depends_on": [],
            "healthcheck": {
                "test": ["CMD-SHELL", "pg_isready -U skaal_user -d skaal_db"],
                "interval": "5s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "10s",
            },
        },
    },
    "sqlite": {
        "class": "SQLiteBackend",
        "import": "from skaal.backends.sqlite_backend import SQLiteBackend",
        "service": None,  # SQLite is file-based, no separate service
        "env_prefix": "SKAAL_SQLITE_PATH",
    },
}


def _backend_info(backend_name: str) -> dict[str, Any]:
    """Get metadata for a backend. Defaults to postgres if unknown."""
    return _BACKENDS.get(backend_name, _BACKENDS["postgres"])


def _env_var(backend_name: str, class_name: str) -> str:
    """Generate environment variable name for a storage class."""
    info = _backend_info(backend_name)
    return f"{info['env_prefix']}_{class_name.upper()}"


def _constructor(backend_name: str, class_name: str, env_var: str) -> str:
    """Generate backend constructor call."""
    info = _backend_info(backend_name)
    cls = info["class"]

    if backend_name == "postgres":
        return f'{cls}(os.environ["{env_var}"], namespace="{class_name}")'
    elif backend_name == "redis":
        return f'{cls}(os.environ["{env_var}"], namespace="{class_name}")'
    elif backend_name == "sqlite":
        return f'{cls}(os.environ["{env_var}"])'
    else:
        return f'{cls}(os.environ["{env_var}"])'


# ── Wiring helpers (backend_imports / backend_overrides) ──────────────────────


def _build_wiring(plan: "PlanFile") -> tuple[str, str]:
    """
    Return ``(backend_imports, backend_overrides)`` template variables.

    backend_imports  — one import line per unique backend class used.
    backend_overrides — ``"ClassName": BackendInstance(...)`` lines.
    """
    seen: set[str] = set()
    import_lines: list[str] = []
    override_lines: list[str] = []

    for qname, spec in plan.storage.items():
        class_name = qname.split(".")[-1]
        info = _backend_info(spec.backend)
        env_var = _env_var(spec.backend, class_name)

        if info["import"] not in seen:
            seen.add(info["import"])
            import_lines.append(info["import"])

        ctor = _constructor(spec.backend, class_name, env_var)
        override_lines.append(f'        "{class_name}": {ctor},')

    return "\n".join(import_lines), "\n".join(override_lines)


# ── Docker Compose YAML builder ───────────────────────────────────────────────


def _build_docker_compose(plan: "PlanFile", port: int, source_pkg: str) -> str:
    """
    Build a docker-compose.yml with app service and storage backend services.

    Returns:
        YAML string ready to write to docker-compose.yml.
    """
    # Collect unique services needed by storage backends
    services_needed: dict[str, dict[str, Any]] = {}
    service_dependencies: list[str] = []
    env_vars: list[str] = []

    for qname, spec in plan.storage.items():
        class_name = qname.split(".")[-1]
        info = _backend_info(spec.backend)
        env_var = _env_var(spec.backend, class_name)

        # Add environment variable for the app
        # Map unknown/remote backends to local alternatives
        local_backend = spec.backend
        if spec.backend not in ("postgres", "redis", "sqlite"):
            # Cloud backends (AWS/GCP) are mapped to postgres for local dev
            local_backend = "postgres"

        if local_backend == "postgres":
            # Format: postgresql://user:pass@host/db
            dsn = "postgresql://skaal_user:skaal_pass@postgres/skaal_db"
            env_vars.append(f"      {env_var}: {dsn}")
        elif local_backend == "redis":
            env_vars.append(f"      {env_var}: redis://redis:6379")
        elif local_backend == "sqlite":
            env_vars.append(f"      {env_var}: /app/data/skaal.db")

        # Register service if it has a compose definition
        # Map unknown/remote backends to local service (postgres for cloud backends)
        service_info = info
        if local_backend != spec.backend and local_backend == "postgres":
            service_info = _backend_info("postgres")

        if service_info.get("service"):
            service_name = service_info["service"]
            if service_name not in services_needed:
                services_needed[service_name] = service_info["compose"]
                if service_name not in service_dependencies:
                    service_dependencies.append(service_name)

    # Build services section
    additional_services = ""
    if services_needed:
        service_lines = []
        for service_name, service_config in services_needed.items():
            service_lines.append(f"  {service_name}:")
            service_lines.append(f"    image: {service_config['image']}")

            if service_config.get("ports"):
                service_lines.append("    ports:")
                for port_mapping in service_config["ports"]:
                    service_lines.append(f"      {port_mapping}")

            if service_config.get("environment"):
                service_lines.append("    environment:")
                for env in service_config["environment"]:
                    service_lines.append(f"      {env}")

            if service_config.get("healthcheck"):
                hc = service_config["healthcheck"]
                service_lines.append("    healthcheck:")
                service_lines.append(f"      test: {hc['test']}")
                service_lines.append(f"      interval: {hc['interval']}")
                service_lines.append(f"      timeout: {hc['timeout']}")
                service_lines.append(f"      retries: {hc['retries']}")
                service_lines.append(f"      start_period: {hc['start_period']}")

            service_lines.append("")

        additional_services = "\n".join(service_lines)

    # Build depends_on section
    depends_on_lines = []
    if service_dependencies:
        for dep in service_dependencies:
            depends_on_lines.append(f"      - {dep}")
    depends_on_str = "\n".join(depends_on_lines) if depends_on_lines else "      []"

    # Render template
    return render(
        "local/docker-compose.yml",
        port=str(port),
        source_pkg=source_pkg,
        service_env_vars="\n".join(env_vars) if env_vars else "      {}",
        service_dependencies=depends_on_str,
        additional_services=additional_services,
    )


# ── Public entry point ─────────────────────────────────────────────────────────


def generate_artifacts(
    app: Any,
    plan: "PlanFile",
    output_dir: Path,
    source_module: str,
    app_var: str = "app",
    dev: bool = False,
) -> list[Path]:
    """
    Generate Docker Compose deployment artifacts.

    Writes into *output_dir*:

    - ``main.py`` or ``main_wsgi.py``  — App entry point
    - ``Dockerfile``  — Container build spec
    - ``docker-compose.yml`` — Service orchestration (app + backends)
    - ``pyproject.toml`` — Python dependencies
    - ``README.md`` — Quick start guide
    - ``skaal-meta.json`` — Metadata

    Args:
        app:           The Skaal App instance.
        plan:          The solved PlanFile (``plan.skaal.lock``).
        output_dir:    Directory to write files into (created if absent).
        source_module: Python module path, e.g. ``"examples.counter"``.
        app_var:       Variable name of the App in the module.

    Returns:
        List of generated :class:`~pathlib.Path` objects.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Top-level source package (e.g. "examples" from "examples.03_dash_app.app")
    top_pkg = source_module.split(".")[0]
    project_root = output_dir.parent

    generated: list[Path] = []
    backend_imports, backend_overrides = _build_wiring(plan)
    deploy_config = LocalStackDeployConfig.model_validate(plan.deploy_config)
    wsgi_attribute: str | None = getattr(app, "_wsgi_attribute", None)

    # ── main.py or main_wsgi.py ───────────────────────────────────────────────
    main_path = output_dir / "main.py"
    if wsgi_attribute:
        main_path.write_text(
            render(
                "local/main_wsgi.py",
                source_module=source_module,
                app_var=app_var,
                wsgi_attribute=wsgi_attribute,
                backend_imports=backend_imports,
                backend_overrides=backend_overrides,
            ),
            encoding="utf-8",
        )
    else:
        main_path.write_text(
            render(
                "local/main.py",
                source_module=source_module,
                app_var=app_var,
                backend_imports=backend_imports,
                backend_overrides=backend_overrides,
            ),
            encoding="utf-8",
        )
    generated.append(main_path)

    # ── skaal source bundle (--dev only) ─────────────────────────────────────
    # In dev mode the local skaal source is bundled into the artifacts dir so
    # the Docker image builds from the working copy instead of PyPI.
    # uv resolves "skaal" via [tool.uv.sources] pointing at this subdirectory.
    skaal_bundle_dir = output_dir / "_skaal"
    skaal_src_dir = project_root / "skaal"
    skaal_root_pyproject = project_root / "pyproject.toml"
    if dev and skaal_src_dir.is_dir() and skaal_root_pyproject.exists():
        skaal_bundle_dir.mkdir(exist_ok=True)
        shutil.copytree(skaal_src_dir, skaal_bundle_dir / "skaal", dirs_exist_ok=True)
        shutil.copy2(skaal_root_pyproject, skaal_bundle_dir / "pyproject.toml")
        # hatchling requires the files referenced in pyproject.toml to exist
        for extra in ("LICENSE", "README.md"):
            src = project_root / extra
            if src.exists():
                shutil.copy2(src, skaal_bundle_dir / extra)
        generated.append(skaal_bundle_dir)

    # ── pyproject.toml ────────────────────────────────────────────────────────
    infra_deps = ["skaal", "gunicorn>=22.0"]

    # Add backend-specific dependencies
    # Map unknown/cloud backends to local equivalents for development
    for spec in plan.storage.values():
        local_backend = spec.backend
        if spec.backend not in ("postgres", "redis", "sqlite"):
            # Cloud backends (AWS/GCP) are mapped to postgres for local dev
            local_backend = "postgres"

        if local_backend == "redis":
            infra_deps.append("redis>=5.0")
        elif local_backend == "postgres":
            infra_deps.append("psycopg[binary]>=3.1")
            infra_deps.append("asyncpg>=0.28")
        elif local_backend == "sqlite":
            pass  # SQLite is built-in to Python

    user_pkgs = collect_user_packages(source_module)
    deps = list(dict.fromkeys(infra_deps + user_pkgs))
    uv_sources = {"skaal": "./_skaal"} if dev and skaal_src_dir.is_dir() else None
    pyproject_path = output_dir / "pyproject.toml"
    pyproject_path.write_text(
        to_pyproject_toml(app.name, deps, uv_sources=uv_sources), encoding="utf-8"
    )
    generated.append(pyproject_path)

    # ── Dockerfile ────────────────────────────────────────────────────────────
    dockerfile_path = output_dir / "Dockerfile"
    dockerfile_path.write_text(render("local/Dockerfile"), encoding="utf-8")
    generated.append(dockerfile_path)

    # ── source package ────────────────────────────────────────────────────────
    # Copy the user's top-level source package into the artifacts dir so the
    # Docker build context is self-contained and uv sync uses the artifact's
    # own pyproject.toml instead of the repo root one.
    src_pkg_dir = project_root / top_pkg
    dst_pkg_dir = output_dir / top_pkg
    if src_pkg_dir.is_dir():
        shutil.copytree(src_pkg_dir, dst_pkg_dir, dirs_exist_ok=True)
        generated.append(dst_pkg_dir)

    # ── docker-compose.yml ─────────────────────────────────────────────────────
    compose_path = output_dir / "docker-compose.yml"
    compose_path.write_text(
        _build_docker_compose(plan, deploy_config.port, source_pkg=top_pkg), encoding="utf-8"
    )
    generated.append(compose_path)

    # ── .gitignore ─────────────────────────────────────────────────────────────
    gitignore_path = output_dir / ".gitignore"
    gitignore_path.write_text(
        "# Local data\n"
        "data/\n"
        "*.db\n"
        "*.sqlite3\n"
        "__pycache__/\n"
        ".pytest_cache/\n"
        ".env\n"
        ".env.local\n",
        encoding="utf-8",
    )
    generated.append(gitignore_path)

    # ── skaal-meta.json ───────────────────────────────────────────────────────
    meta_path = write_meta(
        output_dir, target="local", source_module=source_module, app_name=app.name
    )
    generated.append(meta_path)

    return generated
