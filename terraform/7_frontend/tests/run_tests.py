"""Run mocked Terraform tests in isolation from deployment artifacts and state."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def main():
    module = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="alex-routing-") as temporary:
        root = Path(temporary)
        test_module = root / "terraform" / "7_frontend"
        shutil.copytree(
            module,
            test_module,
            ignore=shutil.ignore_patterns(
                ".terraform", "*.tfstate*", "*.tfvars", "__pycache__"
            ),
        )
        # Terraform evaluates file hashes even for overridden resources. Keep the
        # dummy package in the temporary tree, never at the deployment zip path.
        package = root / "backend" / "api" / "api_lambda.zip"
        package.parent.mkdir(parents=True)
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("test-only.txt", "Not a deployable Lambda package")
        environment = {**os.environ, "TF_DATA_DIR": str(module / ".terraform")}
        for command in ["validate", "test"]:
            result = subprocess.run(
                ["terraform", command, "-no-color"],
                cwd=test_module,
                env=environment,
                check=False,
            )
            if result.returncode:
                return result.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
