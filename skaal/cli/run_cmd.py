"""`skaal run` — run the app locally."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer

from skaal.cli._errors import cli_error_boundary
from skaal.cli.config import SkaalSettings
from skaal.types.cli import ReloadMode

app = typer.Typer(
    help="Run a Skaal app locally.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def run(
    target: str | None = typer.Argument(
        None,
        help=(
            "App to run. Either 'module:variable' (e.g. 'examples.counter:app') "
            "or the name of an entry in [tool.skaal.apps]. Falls back to "
            "'app' in [tool.skaal] of pyproject.toml."
        ),
        metavar="[MODULE:APP|APP_NAME]",
    ),
    all_apps: bool = typer.Option(
        False,
        "--all",
        help=(
            "Run every app declared in [tool.skaal.apps] together, each on its "
            "own port. Writes .skaal/local-endpoints.json so cross-app AppRefs "
            "resolve automatically."
        ),
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address."),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on."),
    redis: str = typer.Option(
        "",
        "--redis",
        help="Use Redis backend with this URL, e.g. redis://localhost:6379.",
    ),
    persist: bool = typer.Option(
        False, "--persist", help="Use SQLite for persistent local storage."
    ),
    db: str = typer.Option("skaal_local.db", "--db", help="SQLite database path (with --persist)."),
    distributed: bool = typer.Option(
        False,
        "--distributed",
        help="Use the Rust mesh runtime for distributed execution (requires skaal[mesh]).",
    ),
    node_id: str = typer.Option("node-0", "--node-id", help="Mesh node ID (with --distributed)."),
    reload: bool | None = typer.Option(
        None,
        "--reload/--no-reload",
        help="Hot-reload on source change. Defaults to on for interactive dev.",
    ),
    reload_dir: list[Path] = typer.Option(
        [],
        "--reload-dir",
        help="Directory to watch (repeatable). Defaults to the project root.",
    ),
) -> None:
    """
    Run a Skaal app locally.

    Starts an HTTP server where every @app.function() becomes a
    POST /{name} endpoint.  Storage is backed by in-memory LocalMap.

    Hot-reload is on by default when stdout is a TTY and SKAAL_ENV is unset
    or 'dev' / 'local' / 'development'.  Pass ``--no-reload`` to disable.

    Example:

        skaal run examples.counter:app
        skaal run examples.counter:app --persist
        skaal run examples.counter:app --distributed
        curl -s localhost:8000/increment -d '{"name": "hits"}' | jq
    """
    from skaal import api
    from skaal.cli import _reload

    cfg = SkaalSettings()

    if all_apps:
        _run_all(cfg, host=host, base_port=port)
        return

    if target and ":" not in target and target in cfg.apps:
        from skaal.cli._orchestrator import env_from_local_endpoints

        graph = api.project_graph()
        node = graph.apps[target]
        # Read local endpoint registry so AppRefs to upstreams resolve.
        env_updates = env_from_local_endpoints(graph, target)
        os.environ.update(env_updates)
        resolved_app = node.module
    else:
        resolved_app = target or cfg.app
    if resolved_app is None:
        raise ValueError(
            "missing MODULE:APP.\n"
            "  Pass it as an argument: skaal run mypackage.app:skaal_app\n"
            "  Or set 'app' in [tool.skaal] of pyproject.toml.\n"
            "  Or declare apps under [tool.skaal.apps.<name>] and use "
            "`skaal run --all`."
        )

    mode: ReloadMode = "on" if reload is True else "off" if reload is False else "auto"
    if _reload.resolve_reload(mode):
        argv_tail = _argv_tail(
            target=resolved_app,
            host=host,
            port=port,
            redis=redis,
            persist=persist,
            db=db,
            distributed=distributed,
            node_id=node_id,
        )
        dirs = reload_dir or _reload.default_reload_dirs()
        raise typer.Exit(_reload.supervise(_reload.child_command(argv_tail), dirs))

    if distributed:
        log.info("Using mesh runtime (node: %s)", node_id)
    elif redis:
        log.info("Using Redis backend: %s", redis)
    elif persist:
        log.info("Using SQLite backend: %s", db)

    try:
        api.run(
            resolved_app,
            host=host,
            port=port,
            redis=redis or None,
            persist=persist,
            db=db,
            distributed=distributed,
            node_id=node_id,
        )
    except KeyboardInterrupt:
        log.info("Stopped.")


def _run_all(cfg: SkaalSettings, *, host: str, base_port: int) -> None:
    """Spawn every app in [tool.skaal.apps] on its own port, tail logs.

    Picks consecutive ports starting at *base_port*, writes
    ``.skaal/local-endpoints.json`` so cross-app `AppRef`s resolve, then
    blocks until any child exits or Ctrl-C is pressed.
    """
    import subprocess
    import sys
    import threading

    from skaal import api
    from skaal.cli._orchestrator import write_local_endpoints

    graph = api.project_graph()
    if not graph.apps:
        raise ValueError("`skaal run --all` requires at least one [tool.skaal.apps] entry.")

    ports: dict[str, int] = {}
    used: set[int] = set()
    for name in graph.order:
        port = base_port + len(ports) * 50
        while port in used or _port_in_use(host, port):
            port += 1
        ports[name] = port
        used.add(port)

    endpoints = {name: f"http://{host}:{port}" for name, port in ports.items()}
    write_local_endpoints(endpoints)
    log.info("Local endpoint registry: .skaal/local-endpoints.json")

    procs: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        for name in graph.order:
            node = graph.apps[name]
            cmd = [
                sys.executable,
                "-m",
                "skaal.cli.main",
                "run",
                node.module,
                "--host",
                host,
                "--port",
                str(ports[name]),
                "--no-reload",
            ]
            child_env = os.environ.copy()
            for env_var, upstream_name in graph.expose_env_for(name).items():
                child_env[env_var] = endpoints[upstream_name]
            log.info("[%s] starting on http://%s:%d", name, host, ports[name])
            proc = subprocess.Popen(
                cmd,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            procs.append((name, proc))
            t = threading.Thread(target=_tail_logs, args=(name, proc), daemon=True)
            t.start()

        # Wait for any child to exit.
        while True:
            for name, proc in procs:
                rc = proc.poll()
                if rc is not None:
                    log.info("[%s] exited with code %d", name, rc)
                    return
            try:
                threading_event_wait_short()
            except KeyboardInterrupt:
                return
    except KeyboardInterrupt:
        return
    finally:
        for _name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for _name, proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def threading_event_wait_short() -> None:
    """Sleep briefly without burning CPU; KeyboardInterrupt propagates."""
    import time

    time.sleep(0.5)


def _tail_logs(name: str, proc) -> None:
    """Forward a child process's stdout, prefixed with its app name."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        log.info("[%s] %s", name, line.rstrip())


def _port_in_use(host: str, port: int) -> bool:
    """Return True if *(host, port)* already has a listener."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
        return False


def _argv_tail(
    *,
    target: str,
    host: str,
    port: int,
    redis: str,
    persist: bool,
    db: str,
    distributed: bool,
    node_id: str,
) -> list[str]:
    """Forward flags onto the supervised child process."""
    argv: list[str] = [
        target,
        "--host",
        host,
        "--port",
        str(port),
        "--db",
        db,
        "--node-id",
        node_id,
    ]
    if redis:
        argv += ["--redis", redis]
    if persist:
        argv.append("--persist")
    if distributed:
        argv.append("--distributed")
    return argv
