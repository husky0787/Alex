These five valid empty ZIP archives are **only** inputs for the mocked Terraform
test's file-hash expressions. They contain no executable worker and must never
be deployed. Real plans require a private `worker_directory` built by the
showcase packaging tool and verified on Lambda.
