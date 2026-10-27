"""Build a Linux Lambda zip with locked wheels, without copying a Windows venv."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def create_deployment_package():
    project = Path(__file__).resolve().parent
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv must be available on PATH")
    destination = project / "lambda_function.zip"
    with tempfile.TemporaryDirectory(prefix="alex-ingest-") as directory:
        build = Path(directory)
        requirements = subprocess.run([uv, "export", "--locked", "--no-hashes", "--no-emit-project",
                                       "--no-emit-package", "alex-research"], cwd=project,
                                      check=True, capture_output=True, text=True).stdout
        (build / "requirements.txt").write_text(requirements, encoding="utf-8")
        package = build / "package"
        subprocess.run([uv, "pip", "install", "--python-platform", "x86_64-manylinux2014",
                        "--python-version", "3.12", "--only-binary", ":all:", "--no-deps",
                        "--target", str(package), "-r", str(build / "requirements.txt")], check=True)
        for name in ("ingest_s3vectors.py", "search_s3vectors.py"):
            shutil.copy2(project / name, package / name)
        shutil.copytree(project.parent / "research" / "research_chain", package / "research_chain",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.write(path, path.relative_to(package))
    print(f"Created {destination.name}: {destination.stat().st_size} bytes")
    return str(destination)


if __name__ == "__main__":
    create_deployment_package()
