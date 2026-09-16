"""Publish one completed user_trait_daily snapshot to MySQL (DW contract §7).

Run after Q4/Q5, never concurrently with an overwrite of the input directory.
This is a bounded Python transfer job, not another Spark calculation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from streaming.jobs.dw_projection_source import (
    DEFAULT_DDL, MART, Contract, ParquetSnapshot, ProjectionError, identifier, load_contract,
)


@dataclass(frozen=True)
class Config:
    host: str
    user: str
    password: str = field(repr=False)
    port: int = 3306
    database: str = "dw"
    batch_size: int = 1000
    allow_empty: bool = False
    tls_ca: str | None = None

    def __post_init__(self):
        identifier(self.database)
        if not self.host.strip() or not self.user.strip() or not self.password:
            raise ProjectionError("DW_MYSQL_HOST, USER and PASSWORD are required")
        if "://" in self.host or not 1 <= self.port <= 65535:
            raise ProjectionError("Invalid MySQL host/port")
        if not 1 <= self.batch_size <= 10000:
            raise ProjectionError("batch_size must be 1..10000")


def connect(config: Config):
    import pymysql

    tls = {} if not config.tls_ca else dict(
        ssl_ca=config.tls_ca, ssl_verify_cert=True, ssl_verify_identity=True,
    )
    return pymysql.connect(
        host=config.host, port=config.port, user=config.user, password=config.password,
        database=config.database, charset="utf8mb4", autocommit=True,
        connect_timeout=10, read_timeout=120, write_timeout=120,
        sql_mode="STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION",
        init_command="SET time_zone = '+00:00'", **tls,
    )


class MysqlStore:
    def __init__(self, connection, database: str, contract: Contract):
        self.connection = connection
        self.database = database
        self.contract = contract

    def table(self, name):
        return f"{identifier(self.database)}.{identifier(name)}"

    def execute(self, sql, params=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)

    def rows(self, sql, params=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def scalar(self, sql, params=()):
        return self.rows(sql, params)[0][0]

    @property
    def lock_name(self):
        return "dw-publish-" + hashlib.sha256(f"{self.database}.{MART}".encode()).hexdigest()[:48]

    def acquire(self):
        return self.scalar("SELECT GET_LOCK(%s, 0)", (self.lock_name,)) == 1

    def release(self):
        self.scalar("SELECT RELEASE_LOCK(%s)", (self.lock_name,))

    def assert_lock(self):
        if self.scalar("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (self.lock_name,)) != 1:
            raise ProjectionError("Publication lock was lost")

    def check_target(self):
        engine = self.rows(
            "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (self.database, MART),
        )
        if engine != (("InnoDB",),):
            raise ProjectionError("Initialize the serving table from contracts/dw/schema.sql (InnoDB)")
        columns = self.rows(
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, EXTRA, COLLATION_NAME "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
            (self.database, MART),
        )
        expected = [("dw_row_id", "bigint", "NO", "auto_increment", None)] + [
            (c.name, c.sql_type.lower(), "YES" if c.nullable else "NO", "",
             "utf8mb4_0900_ai_ci" if c.sql_type.startswith("VARCHAR") else None)
            for c in self.contract.columns
        ]
        if list(columns) != expected:
            raise ProjectionError("Serving schema differs from checked-in DW DDL; apply reviewed DDL first")
        self.execute("SET SESSION lock_wait_timeout = 30")

    def create_staging(self, name):
        # No IF NOT EXISTS: rerunning a run id must never append to an old load.
        self.execute(self.contract.create_staging_sql(self.database, name))

    def insert(self, name, rows):
        columns = ", ".join(identifier(c) for c in self.contract.names)
        placeholders = ", ".join(["%s"] * len(self.contract.columns))
        with self.connection.cursor() as cursor:
            cursor.executemany(f"INSERT INTO {self.table(name)} ({columns}) VALUES ({placeholders})", rows)

    def validate(self, name, expected_count):
        table = self.table(name)
        count = self.scalar(f"SELECT COUNT(*) FROM {table}")
        if count != expected_count:
            raise ProjectionError(f"Staging row count mismatch: expected={expected_count}, actual={count}")
        grain = ", ".join(identifier(c) for c in self.contract.grain)
        # MySQL GROUP BY groups NULL axes together. Surrogate PK/UNIQUE cannot
        # enforce this. DB collation also detects case/accent-equivalent keys.
        duplicate = self.rows(f"SELECT 1 FROM {table} GROUP BY {grain} HAVING COUNT(*) > 1 LIMIT 1")
        if duplicate:
            raise ProjectionError("Staging has duplicate grain (including NULL/collation-equivalent axes)")
        required = " OR ".join(f"{identifier(c.name)} IS NULL" for c in self.contract.columns if not c.nullable)
        if self.scalar(f"SELECT COUNT(*) FROM {table} WHERE {required}") != 0:
            raise ProjectionError("Staging has NULL in a required column")

    def prepare_swap(self):
        # A previous publication can have succeeded even when cleanup failed.
        # Remove that backup only after the NEW staging has passed validation.
        self.execute(f"DROP TABLE IF EXISTS {self.table(MART + '__old')}")

    def swap(self, staging):
        self.assert_lock()
        self.execute(f"RENAME TABLE {self.table(MART)} TO {self.table(MART + '__old')}, "
                     f"{self.table(staging)} TO {self.table(MART)}")

    def cleanup(self):
        # Called only after confirmed publication, while holding the same lock.
        names = self.rows("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
                          (self.database,))
        for (name,) in names:
            if name == MART + "__old" or re.fullmatch(MART + r"__stg_[0-9a-f]{16}", name):
                self.execute(f"DROP TABLE {self.table(name)}")


def publish(source, store, config: Config, report: dict, run_id: str | None = None):
    run_id = run_id or uuid4().hex[:16]
    if not re.fullmatch(r"[0-9a-f]{16}", run_id):
        raise ProjectionError("run_id must be 16 lowercase hexadecimal characters")
    staging = f"{MART}__stg_{run_id}"
    report.update(mart=MART, run_id=run_id, staging=staging, status="validating",
                  source_rows=source.row_count, inserted_rows=0, published=False, warnings=[])
    acquired = False
    try:
        if source.row_count == 0 and not config.allow_empty:
            raise ProjectionError("Empty snapshot blocked; use --allow-empty only for an intentional empty publication")
        if not store.acquire():
            raise ProjectionError("Another publisher holds the Mart lock")
        acquired = True
        store.check_target()
        source.assert_unchanged()
        store.create_staging(staging)
        report["status"] = "loading"
        for rows in source.batches(config.batch_size):
            if rows:
                store.insert(staging, rows)
                report["inserted_rows"] += len(rows)
        store.validate(staging, source.row_count)
        if report["inserted_rows"] != source.row_count:
            raise ProjectionError("Source iterator row count changed")
        source.assert_unchanged()
        store.assert_lock()
        store.prepare_swap()
        report["status"] = "publishing"
        store.swap(staging)
        report.update(status="published", published=True)
        try:
            store.cleanup()
        except Exception:
            # Never say the publication failed after the atomic rename succeeded.
            report["warnings"].append("Published; old/staging cleanup failed and will be retried on next success")
    except Exception as error:
        report["status"] = "publication_unknown" if report["status"] == "publishing" else "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        if acquired:
            try:
                store.release()
            except Exception:
                report["warnings"].append("Lock release failed; closing the DB connection releases the lock")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/marts/user_trait_daily"))
    parser.add_argument("--ddl", type=Path, default=DEFAULT_DDL)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--report-path", type=Path)
    args = parser.parse_args(argv)
    report = {"mart": MART, "status": "failed", "published": False}
    connection = None
    code = 0
    try:
        config = Config(host=os.getenv("DW_MYSQL_HOST", ""), user=os.getenv("DW_MYSQL_USER", ""),
                        password=os.getenv("DW_MYSQL_PASSWORD", ""),
                        port=int(os.getenv("DW_MYSQL_PORT", "3306")),
                        database=os.getenv("DW_MYSQL_DB", "dw"), batch_size=args.batch_size,
                        allow_empty=args.allow_empty, tls_ca=os.getenv("DW_MYSQL_SSL_CA") or None)
        contract = load_contract(args.ddl)
        source = ParquetSnapshot(args.source, contract)
        connection = connect(config)
        publish(source, MysqlStore(connection, config.database, contract), config, report)
    except Exception as error:
        # DB exception messages can contain values or connection details. Emit
        # only safe validation messages and numeric DB error codes.
        report["error_type"] = type(error).__name__
        if isinstance(error, ProjectionError):
            report["error"] = str(error)
        elif error.args and isinstance(error.args[0], int):
            report["db_error_code"] = error.args[0]
        code = 1
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report_path:
        try:
            args.report_path.parent.mkdir(parents=True, exist_ok=True)
            temp = args.report_path.with_name(args.report_path.name + "." + uuid4().hex + ".tmp")
            temp.write_text(rendered + "\n", encoding="utf-8")
            temp.replace(args.report_path)
        except OSError:
            print("Report file write failed; publication status is in stdout", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
