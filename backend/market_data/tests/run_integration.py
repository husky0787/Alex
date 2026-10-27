"""Run integration tests against an ephemeral, loopback-only PostgreSQL cluster.

Set PG_BIN to the PostgreSQL bin directory. This never uses an existing DB.
"""
import os
import argparse
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-smoke", action="store_true", help="Make one real provider request using an isolated DB")
    parser.add_argument("--live-backfill", action="store_true", help="Verify all 20 symbols against the live source, paced over several minutes")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    pg_bin = Path(os.environ.get("PG_BIN", Path(shutil.which("pg_ctl") or "").parent))
    suffix = ".exe" if os.name == "nt" else ""
    initdb = pg_bin / f"initdb{suffix}"
    pg_ctl = pg_bin / f"pg_ctl{suffix}"
    if not initdb.is_file() or not pg_ctl.is_file():
        raise SystemExit("Set PG_BIN to a PostgreSQL bin directory containing initdb and pg_ctl.")
    with tempfile.TemporaryDirectory(prefix="alex-market-test-") as directory:
        root = Path(directory)
        cluster = root / "data"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        # Inherit the tool's hidden console; CREATE_NO_WINDOW breaks initdb's
        # restricted-token re-execution on Windows.
        flags = {}
        print("Initializing isolated PostgreSQL cluster...", flush=True)
        subprocess.run([str(initdb), "-D", str(cluster), "-U", "alex_test", "-A", "trust",
                        "--no-locale", "--encoding=UTF8"], check=True, **flags)
        subprocess.run([str(pg_ctl), "-D", str(cluster), "-l", str(root / "server.log"),
                        "-o", f"-h 127.0.0.1 -p {port}", "-w", "-t", "30", "start"], check=True, **flags)
        try:
            environment = {**os.environ, "MARKET_TEST_DATABASE_URL":
                           f"postgresql://alex_test@127.0.0.1:{port}/postgres"}
            if args.live_backfill:
                environment["MARKET_DATABASE_URL"] = environment["MARKET_TEST_DATABASE_URL"]
                evidence_root = Path(".local/market-data/task-04")
                evidence_root.mkdir(parents=True, exist_ok=True)
                subprocess.run([sys.executable, "-m", "market_data", "migrate"], env=environment, check=True)
                result = subprocess.run([sys.executable, "-m", "market_data", "--env-file",
                                         str(args.env_file.resolve()), "backfill", "--raw-dir", str(evidence_root),
                                         "--evidence", str(evidence_root / "backfill.json")], env=environment)
                if result.returncode == 0:
                    subprocess.run([sys.executable, str(Path(__file__).parent / "verify_live_history.py")],
                                   env=environment, check=True)
                subprocess.run([str(pg_bin / f"pg_dump{suffix}"), "--dbname", environment["MARKET_DATABASE_URL"],
                                "--format=custom", "--file", str(evidence_root / "database.dump")], check=True)
                return result.returncode
            if args.live_smoke:
                environment["MARKET_DATABASE_URL"] = environment["MARKET_TEST_DATABASE_URL"]
                subprocess.run([sys.executable, "-m", "market_data", "migrate"],
                               env=environment, check=True)
                result = subprocess.run([sys.executable, "-m", "market_data", "--env-file",
                                         str(args.env_file.resolve()), "smoke"], env=environment)
                if result.returncode == 0:
                    subprocess.run([sys.executable, str(Path(__file__).parent / "verify_live_api.py")],
                                   env=environment, check=True)
                # Preserve this private test database alongside raw evidence so
                # the run and its immutable observations remain inspectable.
                dump = Path(".local/market-data/smoke-database.dump")
                dump.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([str(pg_bin / f"pg_dump{suffix}"), "--dbname",
                                environment["MARKET_DATABASE_URL"], "--format=custom", "--file", str(dump)],
                               check=True)
                return result.returncode
            return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                                   str(Path(__file__).parent), "-p", "test_*.py", "-v"],
                                  env=environment, **flags).returncode
        finally:
            subprocess.run([str(pg_ctl), "-D", str(cluster), "-m", "immediate", "-w", "stop"],
                           check=True, **flags)


if __name__ == "__main__":
    raise SystemExit(main())
