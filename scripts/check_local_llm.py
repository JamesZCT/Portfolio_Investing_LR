from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the configured local LLM endpoint is ready.")
    parser.add_argument("--provider", default=os.getenv("LLM_SENTIMENT_PROVIDER", "ollama"))
    parser.add_argument("--model", default=os.getenv("LLM_SENTIMENT_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=float, default=float(os.getenv("LLM_SENTIMENT_TIMEOUT_SECONDS", "10")))
    parser.add_argument(
        "--soft",
        action="store_true",
        help="Return success even when the LLM is unavailable; useful when workflows should fall back to heuristics.",
    )
    args = parser.parse_args()

    provider = args.provider.lower().strip()
    if provider == "ollama":
        result = _check_ollama(
            args.base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            args.model,
            args.timeout,
        )
    elif provider == "openai_compatible":
        result = _check_openai_compatible(
            args.base_url or os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"),
            args.model,
            args.timeout,
        )
    else:
        result = {
            "available": False,
            "provider": provider,
            "model": args.model,
            "reason": f"Unsupported provider: {provider}",
        }

    _write_github_output(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["available"]:
        return 0
    return 0 if args.soft else 1


def _check_ollama(base_url: str, model: str, timeout: float) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    try:
        data = _read_json(f"{base_url}/api/tags", timeout=timeout)
    except Exception as exc:
        return _unavailable("ollama", model, base_url, f"Ollama endpoint is not reachable: {exc}")

    names = _ollama_model_names(data)
    if model and model not in names:
        return _unavailable(
            "ollama",
            model,
            base_url,
            f"Model is not downloaded. Run: ollama pull {model}",
            available_models=names,
        )
    return {
        "available": True,
        "provider": "ollama",
        "model": model,
        "base_url": base_url,
        "reason": "Ollama is reachable and the requested model is available.",
        "available_models": names,
    }


def _check_openai_compatible(base_url: str, model: str, timeout: float) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _unavailable(
            "openai_compatible",
            model,
            base_url,
            "OPENAI_API_KEY is required by the sentiment adapter for OpenAI-compatible endpoints.",
        )

    try:
        data = _read_json(
            f"{base_url}/models",
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception as exc:
        return _unavailable("openai_compatible", model, base_url, f"Model endpoint is not reachable: {exc}")

    names = _openai_model_names(data)
    if model and names and model not in names:
        return _unavailable(
            "openai_compatible",
            model,
            base_url,
            "Requested model was not listed by the endpoint.",
            available_models=names,
        )
    return {
        "available": True,
        "provider": "openai_compatible",
        "model": model,
        "base_url": base_url,
        "reason": "OpenAI-compatible endpoint is reachable.",
        "available_models": names,
    }


def _read_json(url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    request = Request(url, headers={"User-Agent": "portfolio-investing-lab/1.0", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured local/private endpoint
        return json.loads(response.read(500_000))


def _ollama_model_names(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    models = data.get("models", [])
    names = []
    for item in models if isinstance(models, list) else []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("model")
            if isinstance(name, str):
                names.append(name)
    return sorted(set(names))


def _openai_model_names(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    models = data.get("data", [])
    names = []
    for item in models if isinstance(models, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            names.append(item["id"])
    return sorted(set(names))


def _unavailable(
    provider: str,
    model: str,
    base_url: str,
    reason: str,
    available_models: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "available": False,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "reason": reason,
        "available_models": available_models or [],
    }


def _write_github_output(result: dict[str, Any]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    lines = [
        f"available={str(result['available']).lower()}",
        f"provider={result.get('provider', '')}",
        f"model={result.get('model', '')}",
        f"reason={result.get('reason', '')}",
    ]
    with open(output_path, "a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
