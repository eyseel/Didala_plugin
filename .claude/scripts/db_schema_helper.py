#!/usr/bin/env python3
"""Inspect local datasource config and export DDL without exposing secrets to Claude."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


MAX_CONFIG_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 90
CONNECT_TIMEOUT_SECONDS = 8
TEMP_PREFIX = "didala-db-schema-"
ACTIVE_PROCESSES: List[subprocess.Popen] = []


class HelperError(RuntimeError):
    pass


@dataclass
class Candidate:
    engine: str
    host: str
    port: int
    database: str
    username: str
    password: str
    source: Path
    schema: Optional[str] = None

    def public(self, index: int) -> Dict[str, object]:
        return {
            "index": index,
            "engine": self.engine,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "schema": self.schema,
            "username": redact_username(self.username),
            "password_detected": bool(self.password),
            "source": str(self.source),
        }


def emit(payload: Dict[str, object], exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(exit_code)


def redact_username(username: str) -> str:
    if len(username) <= 2:
        return "**"
    return username[:2] + "***"


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_unresolved(value: str) -> bool:
    return "${" in value or "{{" in value or re.search(r"(^|[^\\])\$[A-Za-z_]", value) is not None


def config_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise HelperError("配置路径不存在或不可读取")

    names = []
    allowed_suffixes = {".xml", ".properties", ".env", ".yml", ".yaml", ".json", ".toml", ".conf"}
    for root, dirs, files in os.walk(target):
        relative_depth = len(Path(root).relative_to(target).parts)
        if relative_depth > 2:
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if name not in {".git", "node_modules", "target", "build", "dist"}]
        for filename in files:
            path = Path(root) / filename
            if path.suffix.lower() in allowed_suffixes or filename.startswith(("application", "bootstrap", "docker-compose")):
                names.append(path)
    return sorted(names, key=lambda path: (path.suffix.lower() != ".xml", str(path)))[:30]


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            raise HelperError("配置文件超过 2 MiB，拒绝读取")
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise HelperError("无法读取配置文件") from error


def xml_values(path: Path) -> Dict[str, str]:
    # ElementTree does not fetch external resources. A document declaring an
    # external entity is rejected instead of being resolved.
    try:
        root = ElementTree.fromstring(read_text(path))
    except ElementTree.ParseError as error:
        raise HelperError("XML 格式无效或包含不允许的外部实体") from error

    values: Dict[str, str] = {}
    for element in root.iter():
        tag = normalize_key(element.tag.rsplit("}", 1)[-1])
        attributes = {normalize_key(key): value.strip() for key, value in element.attrib.items()}
        text = (element.text or "").strip()
        if tag == "property":
            key = attributes.get("name") or attributes.get("key")
            value = attributes.get("value") or text
            if key and value:
                values[normalize_key(key)] = value
        elif tag == "jdbcconnection":
            # MyBatis Generator's standard datasource element uses
            # connectionURL, userId and driverClass attributes rather than
            # Spring-style property elements.
            for key, value in attributes.items():
                values[key] = value
        elif tag in {"url", "jdbcurl", "username", "user", "password", "host", "port", "database", "schema"} and text:
            values[tag] = text
        for key, value in attributes.items():
            if key in {"url", "jdbcurl", "connectionurl", "username", "userid", "user", "password", "host", "port", "database", "schema", "driverclass"}:
                values[key] = value
    return values


def line_values(path: Path) -> Dict[str, str]:
    text = read_text(path)
    values: Dict[str, str] = {}
    if path.suffix.lower() == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as error:
            raise HelperError("JSON 配置格式无效") from error

        def collect(value: object, prefix: str = "") -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    collect(nested, prefix + str(key) + ".")
            elif isinstance(value, (str, int, float, bool)):
                key = normalize_key(prefix.rstrip("."))
                values[key] = str(value)

        collect(raw)
        return values

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        match = re.match(r"([^:=\s]+)\s*[:=]\s*(.*)$", line)
        if match:
            values[normalize_key(match.group(1))] = match.group(2).strip().strip("\"'")
    return values


def value_for(values: Dict[str, str], names: Sequence[str]) -> Optional[str]:
    normalized_names = [normalize_key(name) for name in names]
    for name in normalized_names:
        if name in values:
            return values[name]
    for key, value in values.items():
        if any(key.endswith(name) for name in normalized_names):
            return value
    return None


def parse_url(url: str) -> Dict[str, object]:
    raw = url.strip()
    if raw.startswith("jdbc:"):
        raw = raw[5:]
    match = re.match(r"(mysql|mariadb|postgresql|postgres)://", raw, re.IGNORECASE)
    if not match:
        return {}
    engine = match.group(1).lower()
    if engine == "postgres":
        engine = "postgresql"
    parsed = urllib.parse.urlsplit(raw)
    query = {key.lower(): values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items() if values}
    return {
        "engine": engine,
        "host": parsed.hostname or "",
        "port": parsed.port or (5432 if engine == "postgresql" else 3306),
        "database": urllib.parse.unquote(parsed.path.lstrip("/").split("/", 1)[0]),
        "username": urllib.parse.unquote(parsed.username or query.get("user", "")),
        "password": urllib.parse.unquote(parsed.password or query.get("password", "")),
        "schema": query.get("currentschema") or query.get("schema"),
    }


def candidate_from_values(values: Dict[str, str], source: Path) -> Optional[Candidate]:
    url_values = [value for key, value in values.items() if key.endswith("url") and ("jdbc:" in value.lower() or "://" in value)]
    parsed = parse_url(url_values[0]) if url_values else {}
    driver = (value_for(values, ["driver-class-name", "driverclass", "driver"]) or "").lower()
    engine = str(parsed.get("engine") or "")
    if not engine:
        if "mariadb" in driver:
            engine = "mariadb"
        elif "mysql" in driver:
            engine = "mysql"
        elif "postgres" in driver:
            engine = "postgresql"
    if engine not in {"mysql", "mariadb", "postgresql"}:
        return None

    host = str(parsed.get("host") or value_for(values, ["host", "hostname"]) or "")
    port_text = str(parsed.get("port") or value_for(values, ["port"]) or (5432 if engine == "postgresql" else 3306))
    database = str(parsed.get("database") or value_for(values, ["database", "dbname", "catalog"]) or "")
    username = str(parsed.get("username") or value_for(values, ["username", "user", "user-id", "userid"]) or "")
    password = str(parsed.get("password") or value_for(values, ["password", "pass"]) or "")
    schema = str(parsed.get("schema") or value_for(values, ["schema", "currentschema"]) or "") or None
    try:
        port = int(port_text)
    except ValueError:
        return None
    if not all([host, database, username, password]) or any(is_unresolved(value) for value in [host, database, username, password]):
        return None
    return Candidate(engine, host, port, database, username, password, source, schema)


def unavailable_diagnostic(path: Path, values: Dict[str, str]) -> Dict[str, str]:
    """Return an actionable, secret-free reason why this file is unusable."""
    text = read_text(path).lower()
    is_generator_config = path.suffix.lower() == ".xml" and "<generatorconfiguration" in text
    has_generator_datasource = "<jdbcconnection" in text or "connectionurl" in text
    if is_generator_config and not has_generator_datasource:
        return {
            "source": str(path),
            "code": "MYBATIS_GENERATOR_CONFIG",
            "reason": "MyBatis Generator 配置只描述代码生成表，未包含可连接的数据源。",
        }
    protected_markers = ("kms", "enc(", "jasypt", "vault", "nacos", "${", "{{")
    if any(marker in text for marker in protected_markers) or any(is_unresolved(value) for value in values.values()):
        return {
            "source": str(path),
            "code": "PROTECTED_OR_EXTERNAL_DATASOURCE",
            "reason": "数据源由 KMS、加密值、环境变量或外部配置中心提供，不能从本地文件安全取得连接凭据。",
        }
    if is_generator_config and has_generator_datasource:
        return {
            "source": str(path),
            "code": "INCOMPLETE_GENERATOR_DATASOURCE",
            "reason": "MyBatis Generator 的 jdbcConnection 未提供可用的完整明文连接信息。",
        }
    return {
        "source": str(path),
        "code": "NO_PLAINTEXT_DATASOURCE",
        "reason": "未找到包含完整明文 MySQL、MariaDB 或 PostgreSQL 连接信息的数据源。",
    }


def inspect_target(target: Path) -> Tuple[List[Candidate], List[Dict[str, str]]]:
    candidates: List[Candidate] = []
    diagnostics: List[Dict[str, str]] = []
    for path in config_files(target):
        try:
            values = xml_values(path) if path.suffix.lower() == ".xml" else line_values(path)
            candidate = candidate_from_values(values, path)
            if candidate:
                candidates.append(candidate)
            else:
                diagnostics.append(unavailable_diagnostic(path, values))
        except HelperError as error:
            diagnostics.append({"source": str(path), "code": "UNREADABLE_OR_INVALID_CONFIG", "reason": str(error)})
    seen = set()
    unique: List[Candidate] = []
    for candidate in candidates:
        fingerprint = (candidate.engine, candidate.host, candidate.port, candidate.database, candidate.username, candidate.schema, str(candidate.source))
        if fingerprint not in seen:
            unique.append(candidate)
            seen.add(fingerprint)
    return unique, diagnostics[:5]


def find_candidates(target: Path) -> List[Candidate]:
    candidates, _diagnostics = inspect_target(target)
    return candidates


def client_bin_directories() -> List[Path]:
    """Return safe, conventional locations for clients omitted from PATH."""
    paths: List[Path] = []
    configured = os.environ.get("DIDALA_DB_CLIENT_BIN")
    if configured:
        paths.append(Path(configured).expanduser())
    paths.extend(
        [
            Path("/opt/homebrew/opt/mysql-client/bin"),
            Path("/usr/local/opt/mysql-client/bin"),
            Path("/opt/homebrew/opt/mariadb/bin"),
            Path("/usr/local/opt/mariadb/bin"),
            Path("/opt/homebrew/opt/libpq/bin"),
            Path("/usr/local/opt/libpq/bin"),
        ]
    )
    return paths


def require_client(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    for directory in client_bin_directories():
        for name in names:
            path = directory / name
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    raise HelperError("缺少数据库客户端：" + " 或 ".join(names))


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def stop_active_processes() -> None:
    for process in list(ACTIVE_PROCESSES):
        stop_process(process)


def signal_handler(signum: int, _frame: object) -> None:
    stop_active_processes()
    raise SystemExit(128 + signum)


atexit.register(stop_active_processes)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_client(command: Sequence[str], *, env: Optional[Dict[str, str]] = None, timeout: int, capture_output: bool = True) -> subprocess.CompletedProcess:
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    ACTIVE_PROCESSES.append(process)
    try:
        stdout, _stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stop_process(process)
        raise HelperError("数据库客户端超时，已终止并回收连接") from error
    finally:
        if process in ACTIVE_PROCESSES:
            ACTIVE_PROCESSES.remove(process)
    if process.returncode != 0:
        raise HelperError("数据库客户端执行失败（退出码 %s）" % process.returncode)
    return subprocess.CompletedProcess(command, process.returncode, stdout, "")


def write_secure_file(suffix: str, content: str) -> str:
    descriptor, path = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=suffix)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def mysql_option(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def json_rows(output: str, context: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for line in output.splitlines():
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise HelperError(context + "返回了无法解析的元数据") from error
        if not isinstance(value, dict):
            raise HelperError(context + "返回了非对象元数据")
        rows.append(value)
    return rows


def mysql_column_catalog(client: str, credentials_option: str, database: str) -> List[Dict[str, object]]:
    query = (
        "SELECT JSON_OBJECT("
        "'table', TABLE_NAME, 'column', COLUMN_NAME, 'type', COLUMN_TYPE, "
        "'nullable', IS_NULLABLE, 'default', COLUMN_DEFAULT, 'extra', EXTRA, "
        "'comment', COLUMN_COMMENT, 'position', ORDINAL_POSITION) "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )
    result = run_client(
        [
            client,
            credentials_option,
            "--batch",
            "--raw",
            "--skip-column-names",
            "--connect-timeout=" + str(CONNECT_TIMEOUT_SECONDS),
            "--execute=" + query,
            database,
        ],
        timeout=CONNECT_TIMEOUT_SECONDS + 10,
    )
    return json_rows(result.stdout, "MySQL 列说明查询")


def mysql_export(candidate: Candidate, output_path: str, timeout: int) -> Tuple[int, List[Dict[str, object]]]:
    client = require_client("mysql", "mariadb")
    dump_client = require_client("mysqldump", "mariadb-dump")
    credentials = write_secure_file(
        ".cnf",
        "[client]\n"
        + "host=" + mysql_option(candidate.host) + "\n"
        + "port=" + str(candidate.port) + "\n"
        + "user=" + mysql_option(candidate.username) + "\n"
        + "password=" + mysql_option(candidate.password) + "\n"
        + "protocol=TCP\n",
    )
    try:
        credentials_option = "--defaults-extra-file=" + credentials
        tables = run_client(
            [
                client,
                credentials_option,
                "--batch",
                "--skip-column-names",
                "--connect-timeout=" + str(CONNECT_TIMEOUT_SECONDS),
                "--execute=SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name",
                candidate.database,
            ],
            timeout=CONNECT_TIMEOUT_SECONDS + 5,
        ).stdout.splitlines()
        tables = [table for table in tables if table]
        if not tables:
            raise HelperError("目标库没有可导出的基础表")
        command = [
            dump_client,
            credentials_option,
            "--no-data",
            "--no-tablespaces",
            "--skip-triggers",
            "--single-transaction",
            "--skip-lock-tables",
            "--result-file=" + output_path,
        ]
        if candidate.engine == "mysql":
            command.append("--set-gtid-purged=OFF")
        command.extend([candidate.database] + tables)
        run_client(command, timeout=timeout, capture_output=False)
        return len(tables), mysql_column_catalog(client, credentials_option, candidate.database)
    finally:
        try:
            os.unlink(credentials)
        except FileNotFoundError:
            pass


def pgpass_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("\n", "")


def postgres_column_catalog(psql: str, base: Sequence[str], env: Dict[str, str], schema: Optional[str]) -> List[Dict[str, object]]:
    schema_condition = "AND c.table_schema = " + sql_literal(schema) if schema else "AND c.table_schema NOT IN ('pg_catalog', 'information_schema')"
    query = (
        "SELECT json_build_object("
        "'table', c.table_name, 'column', c.column_name, 'type', c.data_type, "
        "'nullable', c.is_nullable, 'default', c.column_default, 'extra', '', "
        "'comment', COALESCE(col_description((quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass, c.ordinal_position), ''), "
        "'position', c.ordinal_position)::text "
        "FROM information_schema.columns c WHERE true "
        + schema_condition
        + " ORDER BY c.table_schema, c.table_name, c.ordinal_position"
    )
    result = run_client(
        [psql, *base, "--tuples-only", "--no-align", "--command=" + query],
        env=env,
        timeout=CONNECT_TIMEOUT_SECONDS + 10,
    )
    return json_rows(result.stdout, "PostgreSQL 列说明查询")


def postgres_export(candidate: Candidate, output_path: str, timeout: int) -> Tuple[int, List[Dict[str, object]]]:
    psql = require_client("psql")
    pg_dump = require_client("pg_dump")
    pgpass = write_secure_file(
        ".pgpass",
        ":".join([pgpass_value(candidate.host), str(candidate.port), pgpass_value(candidate.database), pgpass_value(candidate.username), pgpass_value(candidate.password)]) + "\n",
    )
    env = os.environ.copy()
    env.update({"PGPASSFILE": pgpass, "PGCONNECT_TIMEOUT": str(CONNECT_TIMEOUT_SECONDS)})
    try:
        base = ["--host=" + candidate.host, "--port=" + str(candidate.port), "--username=" + candidate.username, "--dbname=" + candidate.database]
        schema_condition = "AND schemaname = " + sql_literal(candidate.schema) if candidate.schema else "AND schemaname NOT IN ('pg_catalog', 'information_schema')"
        count = run_client(
            [psql, *base, "--tuples-only", "--no-align", "--command=SELECT count(*) FROM pg_catalog.pg_tables WHERE true " + schema_condition],
            env=env,
            timeout=CONNECT_TIMEOUT_SECONDS + 5,
        ).stdout.strip()
        table_count = int(count)
        if not table_count:
            raise HelperError("目标范围没有可导出的基础表")
        command = [pg_dump, *base, "--schema-only", "--no-owner", "--no-privileges", "--file=" + output_path]
        if candidate.schema:
            command.append("--schema=" + candidate.schema)
        run_client(command, env=env, timeout=timeout, capture_output=False)
        return table_count, postgres_column_catalog(psql, base, env, candidate.schema)
    finally:
        env.pop("PGPASSFILE", None)
        try:
            os.unlink(pgpass)
        except FileNotFoundError:
            pass


def sql_literal(value: Optional[str]) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


def export_schema(target: Path, candidate_index: int, timeout: int) -> Dict[str, object]:
    candidates = find_candidates(target)
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise HelperError("所选数据源不存在，请重新 inspect 后选择")
    candidate = candidates[candidate_index]
    descriptor, output_path = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=".sql")
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    try:
        if candidate.engine in {"mysql", "mariadb"}:
            table_count, columns = mysql_export(candidate, output_path, timeout)
        else:
            table_count, columns = postgres_export(candidate, output_path, timeout)
        if os.path.getsize(output_path) == 0:
            raise HelperError("DDL 导出为空")
        catalog_path = write_secure_file(
            ".columns.json",
            json.dumps(
                {
                    "engine": candidate.engine,
                    "table_count": table_count,
                    "columns": columns,
                    "comment_policy": "comment 为空字符串表示数据库未维护该字段说明；不得由工具猜测或补写。",
                },
                ensure_ascii=False,
            ),
        )
        return {
            "status": "ok",
            "engine": candidate.engine,
            "table_count": table_count,
            "output_path": output_path,
            "column_catalog_path": catalog_path,
            "connections_closed": True,
            "credentials_cleaned": True,
        }
    except Exception:
        try:
            os.unlink(output_path)
        except FileNotFoundError:
            pass
        try:
            os.unlink(catalog_path)
        except (FileNotFoundError, UnboundLocalError):
            pass
        raise


def cleanup(path_texts: Sequence[str]) -> Dict[str, object]:
    temporary_root = Path(tempfile.gettempdir()).resolve()
    deleted = 0
    for path_text in path_texts:
        path = Path(path_text)
        try:
            resolved_parent = path.resolve().parent
            file_stat = path.lstat()
        except FileNotFoundError:
            continue
        if resolved_parent != temporary_root or not path.name.startswith(TEMP_PREFIX) or not stat.S_ISREG(file_stat.st_mode):
            raise HelperError("拒绝删除非本工具创建的临时 schema 文件")
        path.unlink()
        deleted += 1
    return {"status": "ok", "deleted": deleted}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe local database-schema helper")
    subparsers = parser.add_subparsers(dest="action", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--config", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--config", required=True)
    export_parser.add_argument("--candidate", required=True, type=int)
    export_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--path", required=True, action="append")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    try:
        if arguments.action == "inspect":
            candidates, diagnostics = inspect_target(Path(arguments.config))
            if not candidates:
                emit(
                    {
                        "status": "error",
                        "code": "NO_USABLE_LOCAL_DATASOURCE",
                        "message": "未找到可安全使用的本地数据库连接配置；未连接数据库。",
                        "diagnostics": diagnostics,
                    },
                    2,
                )
            emit({"status": "ok", "candidates": [candidate.public(index) for index, candidate in enumerate(candidates)]})
        if arguments.action == "export":
            timeout = min(max(arguments.timeout, 10), 300)
            emit(export_schema(Path(arguments.config), arguments.candidate, timeout))
        emit(cleanup(arguments.path))
    except HelperError as error:
        emit({"status": "error", "message": str(error)}, 2)
    except Exception:
        emit({"status": "error", "message": "辅助程序发生未预期错误；未输出凭据或连接串"}, 2)


if __name__ == "__main__":
    main()
