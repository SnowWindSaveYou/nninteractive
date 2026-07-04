#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


DEFAULT_PROXY = "http://127.0.0.1:1080"


def configure_proxy(enabled: bool, proxy: str) -> None:
    if not enabled:
        return
    os.environ.setdefault("HTTP_PROXY", proxy)
    os.environ.setdefault("HTTPS_PROXY", proxy)
    os.environ.setdefault("http_proxy", proxy)
    os.environ.setdefault("https_proxy", proxy)


def load_model_management():
    try:
        from nnInteractive.model_management import ensure_model_available, get_default_model_id, list_models
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "nnInteractive is not installed. Install local inference dependencies first, for example:\n"
            "  pip install -e /path/to/nnInteractive\n"
            "or install the package version used by your deployment."
        ) from exc
    return ensure_model_available, get_default_model_id, list_models


def print_available_models(list_models, model_root: Path) -> None:
    models = list_models(model_root)
    print(f"Available models in manifest ({model_root}):")
    for item in models:
        flags = []
        if item.get("default"):
            flags.append("default")
        flags.append("downloaded" if item.get("downloaded") else "not downloaded")
        print(f"  {item['id']:<28} {item.get('display_name', ''):<32} [{', '.join(flags)}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download or locate official nnInteractive model weights.")
    parser.add_argument("model_id", nargs="?", default=None, help="Model id, e.g. nnInteractive_v1.0. Omit to use manifest default.")
    parser.add_argument(
        "--model-root",
        default=os.environ.get("NNINTERACTIVE_MODEL_DIR", str(Path.home() / ".nninteractive")),
        help="Model cache root. Default: $NNINTERACTIVE_MODEL_DIR or ~/.nninteractive",
    )
    parser.add_argument("--list", action="store_true", help="List available models before downloading.")
    parser.add_argument("--no-download", action="store_true", help="Only list/resolve model id; do not download.")
    parser.add_argument(
        "--proxy",
        default=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or DEFAULT_PROXY,
        help="HTTP(S) proxy used for Hugging Face download. Default: existing proxy env or http://127.0.0.1:1080",
    )
    parser.add_argument("--no-proxy", action="store_true", help="Do not set proxy environment variables.")
    args = parser.parse_args(argv)

    configure_proxy(not args.no_proxy, args.proxy)
    model_root = Path(args.model_root).expanduser().resolve()
    os.environ["NNINTERACTIVE_MODEL_DIR"] = str(model_root)

    try:
        ensure_model_available, get_default_model_id, list_models = load_model_management()
        if args.list:
            print_available_models(list_models, model_root)
            print()
        model_id = args.model_id or get_default_model_id(model_root)
        local_dir = model_root / "models" / model_id
        if args.no_download:
            print(f"Selected model: {model_id}")
            print(f"Expected local path: {local_dir}")
            return 0
        print(f"Ensuring model '{model_id}' is available under: {model_root}")
        local_dir = ensure_model_available(model_id, model_root)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"Model ready: {local_dir}")
    print()
    print("Use it with the local backend:")
    print("  export NNINTERACTIVE_BACKEND_ENGINE=local")
    print(f"  export NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR={local_dir}")
    print("  export NNINTERACTIVE_BACKEND_LOCAL_DEVICE=cuda:0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
