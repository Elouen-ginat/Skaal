"""Constraint type primitives used in Skim decorator annotations."""

from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass


class Durability(str, Enum):
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"
    DURABLE = "durable"


class AccessPattern(str, Enum):
    RANDOM_READ = "random-read"
    RANDOM_WRITE = "random-write"
    SEQUENTIAL = "sequential"
    APPEND_ONLY = "append-only"
    WRITE_HEAVY = "write-heavy"
    BULK_READ = "bulk-read"
    TRANSACTIONAL = "transactional"
    PUB_SUB = "pub-sub"


class ComputeType(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    TPU = "tpu"
    ANY = "any"


class ScaleStrategy(str, Enum):
    ROUND_ROBIN = "round-robin"
    PARTITION_BY_KEY = "partition-by-key"
    BROADCAST = "broadcast"
    RACE = "race"
    COMPETING_CONSUMER = "competing-consumer"


class Consistency(str, Enum):
    EVENTUAL = "eventual"
    STRONG = "strong"
    CAUSAL = "causal"


@dataclass
class Latency:
    """Represents a latency constraint, e.g. Latency('< 5ms')."""

    expr: str
    ms: float
    op: str  # '<', '<=', '>', '>='

    def __init__(self, expr: str) -> None:
        self.expr = expr
        match = re.match(r"([<>]=?)\s*([\d.]+)\s*ms", expr.strip())
        if not match:
            raise ValueError(f"Invalid latency expression: {expr!r}. Expected e.g. '< 5ms'")
        self.op = match.group(1)
        self.ms = float(match.group(2))

    def __repr__(self) -> str:
        return f"Latency({self.expr!r})"


@dataclass
class Throughput:
    """Represents a throughput constraint, e.g. Throughput('> 1000 req/s')."""

    expr: str
    value: float
    unit: str  # 'req/s', 'MB/s', 'events/s'
    op: str

    def __init__(self, expr: str) -> None:
        self.expr = expr
        match = re.match(r"([<>]=?)\s*([\d.]+)\s*(.+)", expr.strip())
        if not match:
            raise ValueError(f"Invalid throughput expression: {expr!r}")
        self.op = match.group(1)
        self.value = float(match.group(2))
        self.unit = match.group(3).strip()

    def __repr__(self) -> str:
        return f"Throughput({self.expr!r})"


@dataclass
class Scale:
    """Compute scaling parameters."""

    instances: int | str = "auto"  # int or "auto"
    strategy: ScaleStrategy = ScaleStrategy.ROUND_ROBIN

    def __post_init__(self) -> None:
        if isinstance(self.strategy, str):
            self.strategy = ScaleStrategy(self.strategy)


@dataclass
class Compute:
    """Compute constraint parameters."""

    latency: Latency | str | None = None
    throughput: Throughput | str | None = None
    compute_type: ComputeType = ComputeType.CPU
    memory: str | None = None  # e.g. "~ 2GB"
    schedule: str = "realtime"  # "realtime", "batch", "streaming"

    def __post_init__(self) -> None:
        if isinstance(self.latency, str):
            self.latency = Latency(self.latency)
        if isinstance(self.throughput, str):
            self.throughput = Throughput(self.throughput)
        if isinstance(self.compute_type, str):
            self.compute_type = ComputeType(self.compute_type)


@dataclass
class DecommissionPolicy:
    """Policy for decommissioning old infrastructure after migration."""

    retention_days: int = 30
    archive: bool = True
    archive_target: str = "s3"
