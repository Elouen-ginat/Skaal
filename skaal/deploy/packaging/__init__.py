from __future__ import annotations


def build_and_push_image(*args, **kwargs):
    from skaal.deploy.packaging.gcp_push import build_and_push_image as impl

    return impl(*args, **kwargs)


def package_lambda(*args, **kwargs):
    from skaal.deploy.packaging.lambda_pkg import package_lambda as impl

    return impl(*args, **kwargs)


def build_local_image(*args, **kwargs):
    from skaal.deploy.packaging.local import build_local_image as impl

    return impl(*args, **kwargs)


__all__ = ["build_and_push_image", "build_local_image", "package_lambda"]
