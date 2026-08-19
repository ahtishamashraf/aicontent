#!/usr/bin/env python3
"""Pre-download the configured detector model into the local cache.

Run this once per machine (or bake it into an image) so the first inference
does not pay the download cost, and so an air-gapped deployment can be prepared
in advance.

Supply-chain notes
------------------
* Weights are fetched only in safetensors form. A pickle checkpoint executes
  code at load time, so ``use_safetensors=True`` is not negotiable.
* Pin ``ORIGINLENS_MODEL_REVISION`` to a commit SHA in production. A bare tag or
  branch can be moved by the publisher after you have reviewed it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()

    if settings.detector_backend == "fake":
        print(
            "ORIGINLENS_DETECTOR_BACKEND is 'fake'; there is no model to download.\n"
            "Set it to 'modernbert' first.",
            file=sys.stderr,
        )
        return 2

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError:
        print(
            "PyTorch and Transformers are not installed.\n"
            "Install them with:  pip install -e 'backend[ml]'",
            file=sys.stderr,
        )
        return 3

    model_id = settings.model_id
    revision = settings.model_revision or None
    print(f"Downloading {model_id} (revision: {revision or 'default branch'})")

    if revision is None:
        print(
            "  WARNING: no revision pinned. Set ORIGINLENS_MODEL_REVISION to a "
            "commit SHA for reproducible, tamper-evident deployments.",
            file=sys.stderr,
        )

    try:
        AutoTokenizer.from_pretrained(model_id, revision=revision)
        AutoModelForSequenceClassification.from_pretrained(
            model_id, revision=revision, use_safetensors=True
        )
    except Exception as exc:
        print(f"Download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("Download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
