#!/usr/bin/env python3
"""
Package the Reporter Lambda function using Docker for AWS compatibility.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import zipfile
import argparse
from pathlib import Path


def run_command(cmd, cwd=None):
    """Run a command and capture output."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout


def package_lambda(network=None, uv_binary=None):
    """Package the Lambda function with all dependencies."""

    # Get the directory containing this script
    reporter_dir = Path(__file__).parent.absolute()
    backend_dir = reporter_dir.parent

    # Create a temporary directory for packaging
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        package_dir = temp_path / "package"
        package_dir.mkdir()

        print("Creating Lambda package using Docker...")

        # Export exact requirements from uv.lock (excluding the editable database package)
        print("Exporting requirements from uv.lock...")
        requirements_result = run_command(
            ["uv", "export", "--locked", "--no-emit-project",
             "--no-emit-package", "alex-database", "--no-emit-package", "alex-research"], cwd=str(reporter_dir)
        )

        req_file = temp_path / "requirements.txt"
        req_file.write_text(requirements_result)

        docker_user_args = (
            ["--user", f"{os.getuid()}:{os.getgid()}"] if os.name == "posix" else []
        )
        network_args = ["--network", network] if network else []
        installer = "pip install"
        installer_args = []
        if uv_binary is not None:
            installer_args = [
                "-v", f"{uv_binary.resolve(strict=True)}:/usr/local/bin/uv:ro",
                "--env", "UV_CACHE_DIR=/build/.uv-cache",
            ]
            installer = "uv pip install --python /var/lang/bin/python3.12"
            if "PIP_INDEX_URL" in os.environ:
                installer += ' --default-index "$PIP_INDEX_URL"'
        environment_args = []
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                     "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                     "PIP_INDEX_URL"):
            if name in os.environ:
                environment_args.extend(["--env", name])

        # Use Docker to install dependencies for Lambda's architecture
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            *docker_user_args,
            *network_args,
            *installer_args,
            *environment_args,
            "--platform",
            "linux/amd64",
            "-v",
            f"{temp_path}:/build",
            "-v",
            f"{backend_dir}/database:/database",
            "-v",
            f"{backend_dir}/research:/research",
            "--entrypoint",
            "/bin/bash",
            "public.ecr.aws/lambda/python:3.12",
            "-c",
            f"cd /build && {installer} --no-deps --require-hashes --target ./package -r requirements.txt"
            f" && {installer} --target ./package --no-deps /database /research",
        ]

        run_command(docker_cmd)

        # Copy Lambda handler, agent, templates, and observability
        shutil.copy(reporter_dir / "lambda_handler.py", package_dir)
        shutil.copy(reporter_dir / "agent.py", package_dir)
        shutil.copy(reporter_dir / "templates.py", package_dir)
        shutil.copy(reporter_dir / "observability.py", package_dir)
        shutil.copy(reporter_dir / "judge.py", package_dir)

        # Create the zip file
        zip_path = reporter_dir / "reporter_lambda.zip"

        # Remove old zip if it exists
        if zip_path.exists():
            zip_path.unlink()

        # Create new zip using Python's zipfile (cross-platform, no zip CLI needed)
        print(f"Creating zip file: {zip_path}")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in package_dir.rglob('*'):
                if file.is_file():
                    zf.write(file, file.relative_to(package_dir))

        # Get file size
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"Package created: {zip_path} ({size_mb:.1f} MB)")

        return zip_path


def deploy_lambda(zip_path):
    """Deploy the Lambda function to AWS."""
    import boto3

    lambda_client = boto3.client("lambda")
    function_name = "alex-reporter"

    print(f"Deploying to Lambda function: {function_name}")

    try:
        # Try to update existing function
        with open(zip_path, "rb") as f:
            response = lambda_client.update_function_code(
                FunctionName=function_name, ZipFile=f.read()
            )
        print(f"Successfully updated Lambda function: {function_name}")
        print(f"Function ARN: {response['FunctionArn']}")
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Lambda function {function_name} not found. Please deploy via Terraform first.")
        sys.exit(1)
    except Exception as e:
        print(f"Error deploying Lambda: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Package Reporter Lambda for deployment")
    parser.add_argument("--deploy", action="store_true", help="Deploy to AWS after packaging")
    parser.add_argument("--network", help="Docker network; use host for a localhost proxy on Linux")
    parser.add_argument("--uv-binary", type=Path, help="Optional Linux amd64 uv executable to mount for parallel installation")
    args = parser.parse_args()

    # Check if Docker is available
    try:
        run_command(["docker", "--version"])
    except FileNotFoundError:
        print("Error: Docker is not installed or not in PATH")
        sys.exit(1)

    # Package the Lambda
    zip_path = package_lambda(network=args.network, uv_binary=args.uv_binary)

    # Deploy if requested
    if args.deploy:
        deploy_lambda(zip_path)


if __name__ == "__main__":
    main()
