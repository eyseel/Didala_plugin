import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".claude" / "scripts" / "db_schema_helper.py"


class DbSchemaHelperTest(unittest.TestCase):
    def run_helper(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(HELPER), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_xml_inspection_returns_only_redacted_connection_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "application.xml"
            config.write_text(
                """<beans>
  <bean id=\"dataSource\">
    <property name=\"url\" value=\"jdbc:mysql://db.internal:3307/orders?useSSL=true\" />
    <property name=\"username\" value=\"orders_reader\" />
    <property name=\"password\" value=\"not-a-real-password\" />
  </bean>
</beans>""",
                encoding="utf-8",
            )
            result = self.run_helper("inspect", "--config", str(config))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("not-a-real-password", result.stdout)
        self.assertNotIn("jdbc:mysql://", result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["candidates"],
            [
                {
                    "index": 0,
                    "engine": "mysql",
                    "host": "db.internal",
                    "port": 3307,
                    "database": "orders",
                    "schema": None,
                    "username": "or***",
                    "password_detected": True,
                    "source": str(config),
                }
            ],
        )

    def test_cleanup_refuses_non_helper_path_and_deletes_owned_temp_file(self):
        unrelated = self.run_helper("cleanup", "--path", str(ROOT / "README.md"))
        self.assertEqual(unrelated.returncode, 2)

        descriptor, ddl_path = tempfile.mkstemp(prefix="didala-db-schema-", suffix=".sql")
        os.close(descriptor)
        descriptor, catalog_path = tempfile.mkstemp(prefix="didala-db-schema-", suffix=".columns.json")
        os.close(descriptor)
        Path(ddl_path).write_text("CREATE TABLE t_example (id bigint);", encoding="utf-8")
        Path(catalog_path).write_text('{"columns": []}', encoding="utf-8")
        try:
            result = self.run_helper("cleanup", "--path", ddl_path, "--path", catalog_path)
        finally:
            for path in [ddl_path, catalog_path]:
                try:
                    Path(path).unlink()
                except FileNotFoundError:
                    pass
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "ok", "deleted": 2})

    def test_generator_config_returns_diagnostic_without_attempting_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "generatorConfig.xml"
            config.write_text(
                """<generatorConfiguration>
  <context id=\"MySql\"><table tableName=\"t_order\" /></context>
</generatorConfiguration>""",
                encoding="utf-8",
            )
            result = self.run_helper("inspect", "--config", str(config))

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "NO_USABLE_LOCAL_DATASOURCE")
        self.assertEqual(payload["diagnostics"][0]["code"], "MYBATIS_GENERATOR_CONFIG")
        self.assertNotIn("password", result.stdout.lower())

    def test_mybatis_generator_jdbc_connection_is_parsed_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "generatorConfig.xml"
            config.write_text(
                """<generatorConfiguration>
  <context id=\"MySql\">
    <jdbcConnection driverClass=\"com.mysql.cj.jdbc.Driver\"
      connectionURL=\"jdbc:mysql://db.internal:3308/catalog\"
      userId=\"catalog_reader\" password=\"not-a-real-password\" />
    <table tableName=\"t_product\" />
  </context>
</generatorConfiguration>""",
                encoding="utf-8",
            )
            result = self.run_helper("inspect", "--config", str(config))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("not-a-real-password", result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["candidates"][0]["engine"], "mysql")
        self.assertEqual(payload["candidates"][0]["host"], "db.internal")
        self.assertEqual(payload["candidates"][0]["database"], "catalog")
        self.assertEqual(payload["candidates"][0]["username"], "ca***")

    def test_kms_config_returns_protected_datasource_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "application-dev.yaml"
            config.write_text(
                """spring:
  datasource:
    driver-class-name: com.example.kms.jdbc.mysql.Driver
    url: ENC(not-a-real-encrypted-url)
""",
                encoding="utf-8",
            )
            result = self.run_helper("inspect", "--config", str(config))

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnostics"][0]["code"], "PROTECTED_OR_EXTERNAL_DATASOURCE")
        self.assertNotIn("not-a-real-encrypted-url", result.stdout)

    def test_client_lookup_uses_configured_bin_directory_when_path_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "mysql"
            client.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            client.chmod(0o700)
            previous = os.environ.get("DIDALA_DB_CLIENT_BIN")
            os.environ["DIDALA_DB_CLIENT_BIN"] = directory
            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location("db_schema_helper", HELPER)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                previous_module = sys.modules.get(spec.name)
                sys.modules[spec.name] = module
                try:
                    spec.loader.exec_module(module)
                    with mock.patch.object(module.shutil, "which", return_value=None):
                        self.assertEqual(module.require_client("mysql"), str(client))
                finally:
                    if previous_module is None:
                        sys.modules.pop(spec.name, None)
                    else:
                        sys.modules[spec.name] = previous_module
            finally:
                if previous is None:
                    os.environ.pop("DIDALA_DB_CLIENT_BIN", None)
                else:
                    os.environ["DIDALA_DB_CLIENT_BIN"] = previous


if __name__ == "__main__":
    unittest.main()
