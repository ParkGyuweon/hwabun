"""Optional compaction of one finished ``raw_events`` date partition.

Q1 appends one small Parquet file per Kafka partition per micro-batch, so a
day of Raw becomes thousands of small files.  This job rewrites a single
*finished* ``raw_ingest_date`` partition into files of roughly
``target_file_bytes`` each.

Safety rules (every one of them makes the job a no-op rather than a risk):

* Only a past date is touched.  Q1 stamps ``raw_ingest_date`` from the
  micro-batch clock (UTC), so once the UTC day is over no new file lands in
  that partition.  Today's partition is refused.
* **A Structured Streaming sink log (``_spark_metadata``) under the Raw root
  makes the job skip.**  When that log exists, Spark batch reads of the Raw
  root (Q2 ``clean_events_job`` and Q5) list files *from the log*, not from
  the directory.  Rewritten files would then be invisible and the removed
  originals would fail the read.  Q1's Parquet file sink always writes that
  log, so on EC2-2 this job skips until Q2 stops depending on it.
* The rewrite goes to ``<raw root>/_compaction_tmp`` first (a ``_``-prefixed
  directory is ignored by Spark partition discovery).  Row count and the
  distinct Kafka coordinate count must match the original exactly before the
  swap.  The swap is rename(original -> backup), rename(tmp -> original),
  then delete(backup); a failed second rename puts the backup back.

Row content is unchanged: the same rows are rewritten, only the file layout
changes.  Q2 picks canonical rows by ``received_at`` and Kafka coordinates,
not by file order, so Processed and Mart numbers do not move.
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


DEFAULT_RAW_PATH = "data/raw_events"
DEFAULT_PARTITION_COLUMN = "raw_ingest_date"
DEFAULT_TARGET_FILE_BYTES = 128 * 1024 * 1024
SINK_LOG_DIR = "_spark_metadata"
TMP_DIR = "_compaction_tmp"
BACKUP_DIR = "_compaction_backup"
COORDINATE_COLUMNS = (
    "kafka_cluster_id",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
)


@dataclass(frozen=True)
class CompactConfig:
    raw_path: str = DEFAULT_RAW_PATH
    partition_date: str = ""
    target_file_bytes: int = DEFAULT_TARGET_FILE_BYTES
    partition_column: str = DEFAULT_PARTITION_COLUMN

    def __post_init__(self) -> None:
        if not self.raw_path.strip():
            raise ValueError("raw_path must be a non-empty string")
        date.fromisoformat(self.partition_date)  # raises on a bad date
        if self.target_file_bytes <= 0:
            raise ValueError("target_file_bytes must be greater than zero")


def _yesterday_utc() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def parse_args(argv: list[str] | None = None) -> CompactConfig:
    parser = argparse.ArgumentParser(
        description="Rewrite one finished raw_events date partition into ~128MB files."
    )
    parser.add_argument(
        "--raw-path", default=os.getenv("RAW_EVENTS_PATH") or DEFAULT_RAW_PATH
    )
    parser.add_argument(
        "--date",
        default=os.getenv("RAW_COMPACTION_DATE") or _yesterday_utc(),
        help="raw_ingest_date to compact (UTC, YYYY-MM-DD). Default: yesterday UTC",
    )
    parser.add_argument(
        "--target-file-bytes",
        type=int,
        default=int(os.getenv("RAW_COMPACTION_TARGET_BYTES") or DEFAULT_TARGET_FILE_BYTES),
    )
    args = parser.parse_args(argv)
    return CompactConfig(
        raw_path=args.raw_path,
        partition_date=args.date,
        target_file_bytes=args.target_file_bytes,
    )


def target_file_count(total_bytes: int, target_file_bytes: int) -> int:
    """Number of output files for ``total_bytes`` of Parquet. Never below 1."""

    if total_bytes <= 0:
        return 1
    return max(1, math.ceil(total_bytes / target_file_bytes))


def skip_reason(
    *,
    partition_date: str,
    today_utc: str,
    partition_exists: bool,
    sink_log_present: bool,
    current_file_count: int,
    wanted_file_count: int,
) -> str | None:
    """Return why compaction must not run, or ``None`` when it may run."""

    if partition_date >= today_utc:
        return "partition_not_finished"
    if not partition_exists:
        return "partition_missing"
    if sink_log_present:
        return "sink_log_present"
    if current_file_count <= wanted_file_count:
        return "already_compact"
    return None


class _Fs:
    """Thin wrapper over the Hadoop FileSystem the Spark session already uses."""

    def __init__(self, spark: Any, root: str) -> None:
        jvm = spark.sparkContext._jvm
        self._Path = jvm.org.apache.hadoop.fs.Path
        conf = spark.sparkContext._jsc.hadoopConfiguration()
        self.fs = self._Path(root).getFileSystem(conf)

    def path(self, *parts: str) -> Any:
        return self._Path("/".join(p.rstrip("/") for p in parts))

    def exists(self, p: Any) -> bool:
        return bool(self.fs.exists(p))

    def parquet_stats(self, p: Any) -> tuple[int, int]:
        files = [
            s
            for s in self.fs.listStatus(p)
            if s.isFile() and s.getPath().getName().endswith(".parquet")
        ]
        return len(files), sum(int(s.getLen()) for s in files)

    def mkdirs(self, p: Any) -> None:
        self.fs.mkdirs(p)

    def rename(self, src: Any, dst: Any) -> bool:
        return bool(self.fs.rename(src, dst))

    def delete(self, p: Any) -> None:
        self.fs.delete(p, True)


def _coordinate_summary(frame: Any) -> tuple[int, int]:
    from pyspark.sql import functions as F

    row = frame.agg(
        F.count(F.lit(1)).alias("rows"),
        F.countDistinct(*COORDINATE_COLUMNS).alias("coordinates"),
    ).first()
    return int(row["rows"]), int(row["coordinates"])


def run(spark: Any, config: CompactConfig, today_utc: str | None = None) -> dict[str, Any]:
    today_utc = today_utc or datetime.now(timezone.utc).date().isoformat()
    fs = _Fs(spark, config.raw_path)
    part_name = f"{config.partition_column}={config.partition_date}"
    source = fs.path(config.raw_path, part_name)
    partition_exists = fs.exists(source)
    file_count, total_bytes = fs.parquet_stats(source) if partition_exists else (0, 0)
    wanted = target_file_count(total_bytes, config.target_file_bytes)
    report: dict[str, Any] = {
        "partition": part_name,
        "files_before": file_count,
        "bytes": total_bytes,
        "files_target": wanted,
    }

    reason = skip_reason(
        partition_date=config.partition_date,
        today_utc=today_utc,
        partition_exists=partition_exists,
        sink_log_present=fs.exists(fs.path(config.raw_path, SINK_LOG_DIR)),
        current_file_count=file_count,
        wanted_file_count=wanted,
    )
    if reason is not None:
        report["status"] = "skipped"
        report["reason"] = reason
        return report

    tmp = fs.path(config.raw_path, TMP_DIR, part_name)
    backup_root = fs.path(config.raw_path, BACKUP_DIR)
    backup = fs.path(config.raw_path, BACKUP_DIR, part_name)
    for leftover in (tmp, backup):
        if fs.exists(leftover):
            fs.delete(leftover)

    original = spark.read.option("mergeSchema", "true").parquet(source.toString())
    expected = _coordinate_summary(original)
    original.repartition(wanted).write.mode("overwrite").parquet(tmp.toString())
    written = _coordinate_summary(spark.read.parquet(tmp.toString()))
    if written != expected:
        fs.delete(tmp)
        raise RuntimeError(
            f"compaction verification failed for {part_name}: "
            f"rows/coordinates before={expected} after={written}; original kept"
        )

    fs.mkdirs(backup_root)
    if not fs.rename(source, backup):
        fs.delete(tmp)
        raise RuntimeError(f"could not move {part_name} aside; original kept")
    if not fs.rename(tmp, source):
        fs.rename(backup, source)
        raise RuntimeError(f"could not swap in compacted {part_name}; original restored")
    fs.delete(backup)

    report["status"] = "compacted"
    report["files_after"] = fs.parquet_stats(source)[0]
    report["rows"] = expected[0]
    return report


def main(argv: list[str] | None = None) -> None:
    import json

    config = parse_args(argv)

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("compact-raw-partition")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        print(json.dumps(run(spark, config), ensure_ascii=False))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
