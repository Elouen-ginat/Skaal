"""Non-regression deploy suite.

Tests in this package provision real infrastructure on every supported
`Target` (local, AWS, GCP), exercise the deployed app over HTTP, then tear
the infrastructure back down. They are gated behind explicit environment
variables so a default `pytest tests/` collection skips them.

Driven by `.github/workflows/nonregression.yml` on every merge to `main`.
"""
