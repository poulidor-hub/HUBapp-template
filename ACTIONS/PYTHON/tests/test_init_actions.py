"""Tests des actions générées par INITIALISE.py.

Les actions START et UPDATE doivent synchroniser le .env (sync-env :
allocation des ports via le Hub + FRONTEND_HTTPS_PORT) AVANT tout
build/up docker compose — sinon une app initialisée avec ports vides
échoue au premier démarrage (APP_SUBNET requis, ports non alloués).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import INITIALISE


class TestGeneratedActionsSyncEnv:
    def test_common_exposes_ensure_env_sync(self):
        assert "def ensure_env_sync" in INITIALISE.COMMON_PY

    def test_common_uses_allocate_ports(self):
        assert "allocate_ports.py" in INITIALISE.COMMON_PY

    def test_start_calls_sync_before_up(self):
        src = INITIALISE._action_template("START")
        assert "ensure_env_sync()" in src

    def test_update_calls_sync_before_up(self):
        src = INITIALISE._action_template("UPDATE")
        assert "ensure_env_sync()" in src


class TestSyncHttpsPort:
    """sync_https_port : FRONTEND_HTTPS_PORT = FRONTEND_PORT + 1 dans le .env."""

    @staticmethod
    def _load_common(tmp_path):
        ns = {"__file__": str(tmp_path / "ACTIONS" / "PYTHON" / "_common.py")}
        exec(compile(INITIALISE.COMMON_PY, "_common.py", "exec"), ns)
        return ns

    def test_recomputes_https_port(self, tmp_path):
        ns = self._load_common(tmp_path)
        env = tmp_path / ".env"
        env.write_text("APP_SLUG=demo\nFRONTEND_PORT=4300\nFRONTEND_HTTPS_PORT=9999\n")
        assert ns["sync_https_port"](env) is True
        content = env.read_text()
        assert "FRONTEND_HTTPS_PORT=4301" in content
        assert "9999" not in content

    def test_noop_when_port_missing(self, tmp_path):
        ns = self._load_common(tmp_path)
        env = tmp_path / ".env"
        env.write_text("APP_SLUG=demo\nFRONTEND_PORT=\n")
        assert ns["sync_https_port"](env) is False
        assert "FRONTEND_HTTPS_PORT" not in env.read_text()

    def test_appends_https_line_when_absent(self, tmp_path):
        ns = self._load_common(tmp_path)
        env = tmp_path / ".env"
        env.write_text("APP_SLUG=demo\nFRONTEND_PORT=4300\n")
        assert ns["sync_https_port"](env) is True
        assert "FRONTEND_HTTPS_PORT=4301" in env.read_text()

    def test_accepts_str_path(self, tmp_path):
        """set_env_var/sync_https_port doivent accepter un chemin str (coercition Path)."""
        ns = self._load_common(tmp_path)
        env = tmp_path / ".env"
        env.write_text("APP_SLUG=demo\nFRONTEND_PORT=4300\n")
        assert ns["sync_https_port"](str(env)) is True
        assert "FRONTEND_HTTPS_PORT=4301" in env.read_text()
