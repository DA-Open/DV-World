import ipaddress
import json
import logging
import os
import time
from pathlib import Path
from http import HTTPStatus
from typing import Tuple, Optional

import openai
from openai import AzureOpenAI
import requests
# import servicediscovery as sd
import ServiceDiscovery as sd


from dvworld_agent_fcmode.agent.config import resolve_model_config

logger = logging.getLogger("api-llms")


def _llm_debug_enabled() -> bool:
    return bool(os.getenv("LLM_DEBUG"))


def _write_llm_debug(payload: dict, api_url: str, response_status: Optional[int] = None, response_text: Optional[str] = None) -> None:
    if not _llm_debug_enabled():
        return
    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = log_dir / "llm_debug.jsonl"
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pid": os.getpid(),
            "api_url": api_url,
            "payload": payload,
        }
        if response_status is not None:
            record["response_status"] = response_status
        if response_text is not None:
            record["response_text"] = response_text[:20000]
        with filename.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
        logger.info("LLM debug appended: %s", filename)
    except Exception as exc:
        logger.warning("Failed to write LLM debug log: %s", exc)


_psm_endpoint_cache: dict[tuple[str, str], str] = {}
_ALLOWED_ADDRESS_FAMILIES = {"dual-stack", "v4", "v6"}
_QWEN_OPENAI_MODELS = {
    "openai_qwen3-235b-a22b",
    "openai_qwen3-30b-a3b",
    "openai_qwen3-8b",
    "openai_qwen3-4b",
}


def _normalize_address_family(value: Optional[str]) -> str:
    if not value:
        return "dual-stack"
    normalized = value.lower()
    mapping = {
        "dual-stack": "dual-stack",
        "dualstack": "dual-stack",
        "v6": "v6",
        "ipv6": "v6",
        "v4": "v4",
        "ipv4": "v4",
    }
    resolved = mapping.get(normalized)
    if not resolved:
        logger.warning(
            "Invalid PSM address_family '%s'. Falling back to dual-stack.", value
        )
        return "dual-stack"
    return resolved


def _format_host(host: str) -> str:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host
    if ip.version == 6 and "[" not in host:
        return f"[{host}]"
    return host


def _resolve_psm_endpoint(psm: str, address_family: str) -> str:
    if not psm:
        raise ValueError("PSM name is required when using provider 'psm'.")
    address_family = _normalize_address_family(address_family)
    cache_key = (psm, address_family)
    cached = _psm_endpoint_cache.get(cache_key)
    if cached:
        return cached
    pod = sd.get_one(psm, address_family=address_family)
    if not pod:
        raise RuntimeError(f"servicediscovery can not find pod for psm: {psm}")
    host = _format_host(pod["Host"])
    endpoint = f"http://{host}:{pod['Port']}"
    _psm_endpoint_cache[cache_key] = endpoint
    return endpoint


def _resolve_psm_base_url(
    psm: str,
    address_family: str,
    host_override: Optional[str],
    port_override: Optional[str],
) -> str:
    host_value = (host_override or "").strip()
    if host_value:
        formatted_host = _format_host(host_value)
        port_value = (port_override or "").strip()
        if not port_value:
            raise ValueError("PSM host override requires a valid port.")
        return f"http://{formatted_host}:{port_value}"
    return _resolve_psm_endpoint(psm, address_family=address_family)


def _build_psm_api_url(
    psm: str,
    path: str,
    address_family: str,
    host_override: Optional[str],
    port_override: Optional[str],
) -> str:
    base = _resolve_psm_base_url(
        psm=psm,
        address_family=address_family,
        host_override=host_override,
        port_override=port_override,
    )
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _normalize_psm_api_path(api_path: Optional[str]) -> str:
    path = (api_path or "/v1").strip()
    if not path:
        path = "/v1"
    if not path.startswith("/"):
        path = f"/{path}"
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    path = path.rstrip("/")
    return path if path else "/v1"


def _build_psm_base_url(
    psm: str,
    address_family: str,
    host_override: Optional[str],
    port_override: Optional[str],
    api_path: Optional[str] = None,
) -> str:
    base = _resolve_psm_base_url(
        psm=psm,
        address_family=address_family,
        host_override=host_override,
        port_override=port_override,
    )
    return f"{base}{_normalize_psm_api_path(api_path)}"


def _prepare_payload_model_tweaks(model: str, payload: dict) -> dict:
    tweaked = payload
    if model in ["gpt-5-2025-08-07", "o3-2025-04-16"] and "temperature" in payload:
        tweaked = payload.copy()
        tweaked.pop("temperature", None)
    # Some endpoints (e.g., gpt-5.1 family) reject the enable_thinking flag; strip it.
    if model.startswith(("gpt-5.1", "gpt-5.2")) and "enable_thinking" in tweaked:
        if tweaked is payload:
            tweaked = payload.copy()
        tweaked.pop("enable_thinking", None)

    qwen_no_thinking = set(_QWEN_OPENAI_MODELS)
    qwen_limit_max_tokens = {"openai_qwen3-30b-a3b", "openai_qwen3-8b", "openai_qwen3-4b"}
    if model in qwen_no_thinking or model in qwen_limit_max_tokens:
        tweaked = tweaked.copy()
        # Qwen OpenAI-compatible endpoints require enable_thinking=false and non-streaming.
        tweaked["enable_thinking"] = False
        tweaked["stream"] = False
        if model in qwen_limit_max_tokens and tweaked.get("max_tokens") is None:
            tweaked["max_tokens"] = 8192
    # Doubao thinking variants require reasoning_effort; set to high by default.
    doubao_reasoning_models = {
        "doubao-seed-1-6-thinking-dataagent-preview",
        "doubao-seed-1-8-251215",
    }
    if model in doubao_reasoning_models:
        if tweaked is payload:
            tweaked = payload.copy()
        tweaked.setdefault("reasoning_effort", "high")
    # Kimi endpoints reject enable_thinking; strip it.
    if model.startswith("kimi-k2") and "enable_thinking" in tweaked:
        if tweaked is payload:
            tweaked = payload.copy()
        tweaked.pop("enable_thinking", None)
    return tweaked


def _append_content_filter_note(payload: dict) -> None:
    try:
        last_msg = payload["messages"][-1]["content"][0]["text"]
        if not last_msg.endswith(
            "They do not represent any real events or entities. ]"
        ):
            payload["messages"][-1]["content"][0]["text"] += (
                "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. "
                "They do not represent any real events or entities. ]"
            )
    except Exception:
        # Best-effort; ignore if payload structure differs.
        pass


def _http_chat_completion(
    api_url: str,
    api_key: Optional[str],
    payload: dict,
    model: str,
    bypass_proxy: bool = False,
) -> Tuple[bool, dict]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or ''}",
    }
    proxies = {"http": None, "https": None} if bypass_proxy else None
    code_value = "unknown_error"
    tweaked_payload = payload
    if model in _QWEN_OPENAI_MODELS and isinstance(tweaked_payload, dict):
        tweaked_payload = tweaked_payload.copy()
        tweaked_payload["enable_thinking"] = False
        tweaked_payload.setdefault("stream", False)
    removed_enable_thinking = False
    removed_tools = False
    removed_top_p = False
    removed_temperature = False
    invalid_param_retries = 0
    rate_limit_retries = 0
    rate_limit_backoff = 0.5
    for _ in range(3000):
        _write_llm_debug(tweaked_payload, api_url)
        try:
            response = requests.post(api_url, headers=headers, json=tweaked_payload, proxies=proxies)
        except requests.RequestException as exc:
            logger.error("Failed to call LLM: %s", exc)
            code_value = "request_exception"
            time.sleep(0.2)
            continue

        try:
            response_json = response.json()
        except ValueError:
            logger.error("LLM response is not valid JSON: %s", response.text[:200])
            _write_llm_debug(tweaked_payload, api_url, response_status=response.status_code, response_text=response.text)
            code_value = "invalid_json_response"
            time.sleep(0.2)
            continue

        choices = response_json.get("choices")
        if response.status_code == HTTPStatus.OK and choices:
            first_choice = choices[0] if choices else {}
            message = first_choice.get("message") or {}
            if message:
                return True, message
            logger.error("Missing message payload in LLM response: %s", response_json)
            code_value = "missing_message_content"
        else:
            _write_llm_debug(tweaked_payload, api_url, response_status=response.status_code, response_text=response.text)
            error_info = response_json.get("error") or {}
            code_value = error_info.get("code", f"status_{response.status_code}")
            error_message = str(error_info.get("message", "")).lower()
            if code_value in {"InvalidParameter", "invalid_parameter", "-4003"} and isinstance(tweaked_payload, dict):
                if error_message:
                    logger.warning("HTTP InvalidParameter: %s", error_info)
                if "enable thinking" in error_message and "stream" in error_message:
                    if tweaked_payload.get("enable_thinking") is not False:
                        tweaked_payload = tweaked_payload.copy()
                        tweaked_payload["enable_thinking"] = False
                        removed_enable_thinking = True
                        time.sleep(0.2)
                        continue
                if not removed_enable_thinking and "enable_thinking" in tweaked_payload:
                    tweaked_payload = tweaked_payload.copy()
                    tweaked_payload["enable_thinking"] = False
                    removed_enable_thinking = True
                    time.sleep(0.2)
                    continue
                if not removed_tools and "tools" in tweaked_payload:
                    tweaked_payload = tweaked_payload.copy()
                    tweaked_payload.pop("tools", None)
                    tweaked_payload.pop("tool_choice", None)
                    removed_tools = True
                    logger.warning("Removed tools/tool_choice and retrying due to InvalidParameter.")
                    time.sleep(0.2)
                    continue
                if not removed_top_p and "top_p" in tweaked_payload:
                    tweaked_payload = tweaked_payload.copy()
                    tweaked_payload.pop("top_p", None)
                    removed_top_p = True
                    logger.warning("Removed top_p and retrying due to InvalidParameter.")
                    time.sleep(0.2)
                    continue
                if not removed_temperature and "temperature" in tweaked_payload:
                    tweaked_payload = tweaked_payload.copy()
                    tweaked_payload.pop("temperature", None)
                    removed_temperature = True
                    logger.warning("Removed temperature and retrying due to InvalidParameter.")
                    time.sleep(0.2)
                    continue
            if code_value == "content_filter":
                _append_content_filter_note(payload)
            elif code_value == "context_length_exceeded":
                return False, {"error": code_value}
            elif code_value == "-1013":
                return False, {"error": code_value}
            elif code_value in {"rate_limit", "rate_limit_exceeded", "-2001"}:
                rate_limit_retries += 1
                if rate_limit_retries > 100:
                    return False, {"error": code_value}
                time.sleep(rate_limit_backoff)
                rate_limit_backoff = min(10.0, rate_limit_backoff * 2)
                continue
            elif code_value == "max_tokens" and "max_tokens" in tweaked_payload:
                tweaked_payload = tweaked_payload.copy()
                tweaked_payload.pop("max_tokens", None)
                logger.warning("Removed max_tokens due to InvalidParameter/max_tokens and retrying.")
                time.sleep(0.2)
                continue
            elif code_value in {"InvalidParameter", "invalid_parameter", "-4003"}:
                invalid_param_retries += 1
                if invalid_param_retries > 50:
                    return False, {"error": code_value}
                time.sleep(0.5)
                continue
            else:
                logger.error(
                    "Unexpected LLM response (status %s): %s",
                    response.status_code,
                    response_json,
                )
        logger.error("Retrying ...")
        time.sleep(0.2)
    return False, {"error": code_value}


def _psm_chat_completion(payload: dict, model_settings: dict) -> Tuple[bool, dict]:
    psm_name = model_settings.get("psm_name")
    address_family = model_settings.get("psm_address_family", "dual-stack")
    host_override = model_settings.get("psm_host")
    port_override = model_settings.get("psm_port")
    api_key = (
        model_settings.get("api_key")
        or os.getenv("OPENAI_PSM_API_KEY")
        or os.getenv("PSM_API_KEY")
        or "mock-key"
    )

    if model_settings.get("bypass_proxy"):
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"

    base_url = _build_psm_base_url(
        psm=psm_name,
        address_family=address_family,
        host_override=host_override,
        port_override=port_override,
        api_path=model_settings.get("api_path"),
    )
    logger.info(
        "PSM base_url=%s psm=%s address_family=%s host_override=%s port_override=%s",
        base_url,
        psm_name,
        address_family,
        host_override,
        port_override,
    )
    client = openai.Client(base_url=base_url, api_key=api_key)
    model_name = model_settings.get("model_name") or payload.get("model")

    max_tokens = model_settings.get("max_tokens")
    if max_tokens is None:
        max_tokens = payload.get("max_tokens")
    if max_tokens is None:
        max_tokens = 8192

    include_tools = bool(payload.get("tools")) and model_settings.get("psm_use_tools", True)
    request = {
        "model": model_name,
        "messages": payload.get("messages", []),
        "max_tokens": max_tokens,
        "stream": False,
    }
    if include_tools:
        request["tools"] = payload.get("tools")
        request["tool_choice"] = payload.get("tool_choice", "auto")
    request = {k: v for k, v in request.items() if v is not None}
    request.pop("enable_thinking", None)
    if include_tools and request.get("max_tokens", 0) < 8192:
        request["max_tokens"] = 8192

    last_error = None
    lowered_max_tokens = False
    for _ in range(100):
        try:
            _write_llm_debug(request, base_url)
            completion = client.chat.completions.create(**request)
            choices = None
            if isinstance(completion, dict):
                choices = completion.get("choices")
            else:
                choices = getattr(completion, "choices", None)
            if not choices:
                last_error = "psm_empty_choices"
                _write_llm_debug(request, base_url, response_text=last_error)
                time.sleep(0.5)
                continue
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
            else:
                message = getattr(first_choice, "message", None)
            if not message:
                last_error = "psm_empty_message"
                _write_llm_debug(request, base_url, response_text=last_error)
                time.sleep(0.5)
                continue
            if isinstance(message, dict):
                return True, message
            if hasattr(message, "model_dump"):
                return True, message.model_dump()
            if hasattr(message, "to_dict"):
                return True, message.to_dict()
            return True, {"content": getattr(message, "content", "")}
        except Exception as exc:
            logger.error("PSM OpenAI call failed: %s", exc)
            error_text = str(exc)
            last_error = error_text
            _write_llm_debug(request, base_url, response_text=error_text)
            if "tool" in error_text.lower() and "tools" in request:
                request = dict(request)
                request.pop("tools", None)
                request.pop("tool_choice", None)
                time.sleep(0.2)
                continue
            if (not lowered_max_tokens) and request.get("max_tokens", 0) > 2048 and (
                "max_tokens" in error_text.lower() or "invalidparameter" in error_text.lower()
            ):
                request = dict(request)
                request["max_tokens"] = 2048
                lowered_max_tokens = True
                time.sleep(0.2)
                continue
            time.sleep(0.5)
            continue
    return False, {"error": last_error or "psm_call_failed"}


def _bytedance_chat_completion(payload: dict, model_settings: dict) -> Tuple[bool, dict]:
    api_url = model_settings.get("base_url")
    api_key = (
        model_settings.get("api_key")
        or os.getenv("AUTH_TOKEN")
        or os.getenv("OPENAI_API_KEY")
        or "mock-key"
    )
    if not api_url:
        return False, {"error": "missing_base_url"}

    if model_settings.get("bypass_proxy"):
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or ''}",
    }
    model_name = model_settings.get("model_name") or payload.get("model")
    generate_kwargs = model_settings.get("generate_kwargs") or {}

    max_tokens = generate_kwargs.get("max_tokens")
    if max_tokens is None:
        max_tokens = model_settings.get("max_tokens")
    if max_tokens is None:
        max_tokens = payload.get("max_tokens") or 8192

    def _normalize_message_content(value: Optional[object]) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in value
            )
        return str(value)

    def _sanitize_messages(messages: list) -> list:
        cleaned = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = _normalize_message_content(msg.get("content"))
            if content.strip():
                cleaned.append(msg)
                continue
            if msg.get("tool_calls"):
                patched = dict(msg)
                patched["content"] = "Tool call."
                cleaned.append(patched)
                continue
            # Drop empty assistant/system/user messages with no content.
        return cleaned

    include_tools = bool(payload.get("tools"))
    messages = _sanitize_messages(payload.get("messages", []))
    request = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if include_tools:
        request["tools"] = payload.get("tools")
        request["tool_choice"] = payload.get("tool_choice", "auto")
    for key, value in generate_kwargs.items():
        if key in {"max_tokens", "model"}:
            continue
        if value is not None:
            request[key] = value
    for key in ("temperature", "top_p"):
        if key in payload and payload[key] is not None:
            request[key] = payload[key]
    request.pop("enable_thinking", None)
    if include_tools and request.get("max_tokens", 0) < 8192:
        request["max_tokens"] = 8192

    last_error = None
    lowered_max_tokens = False
    invalid_param_retries = 0
    removed_stream = False
    rate_limit_retries = 0
    rate_limit_backoff = 0.5
    for _ in range(3000):
        _write_llm_debug(request, api_url)
        try:
            response = requests.post(api_url, headers=headers, json=request)
        except requests.RequestException as exc:
            logger.error("Bytedance HTTP call failed: %s", exc)
            last_error = "request_exception"
            time.sleep(0.2)
            continue

        try:
            response_json = response.json()
        except ValueError:
            logger.error("Bytedance response is not valid JSON: %s", response.text[:200])
            _write_llm_debug(request, api_url, response_status=response.status_code, response_text=response.text)
            last_error = "invalid_json_response"
            time.sleep(0.2)
            continue

        choices = response_json.get("choices")
        if response.status_code == HTTPStatus.OK and choices:
            first_choice = choices[0] if choices else {}
            message = first_choice.get("message") or {}
            if message:
                return True, message
            last_error = "missing_message_content"
        else:
            _write_llm_debug(request, api_url, response_status=response.status_code, response_text=response.text)
            error_info = response_json.get("error") or {}
            code_value = error_info.get("code", f"status_{response.status_code}")
            error_message = str(error_info.get("message", "")).lower()
            last_error = code_value
            if code_value == "content_filter":
                _append_content_filter_note(payload)
            elif code_value == "context_length_exceeded":
                return False, {"error": code_value}
            elif code_value == "-1013":
                return False, {"error": code_value}
            elif code_value in {"rate_limit", "rate_limit_exceeded", "-2001"}:
                rate_limit_retries += 1
                if rate_limit_retries > 100:
                    return False, {"error": code_value}
                time.sleep(rate_limit_backoff)
                rate_limit_backoff = min(10.0, rate_limit_backoff * 2)
                continue
            elif code_value == "max_tokens" and "max_tokens" in request:
                request = dict(request)
                request.pop("max_tokens", None)
                logger.warning("Removed max_tokens due to InvalidParameter/max_tokens and retrying.")
                time.sleep(0.2)
                continue
            elif code_value in {"InvalidParameter", "invalid_parameter", "-4003"}:
                invalid_param_retries += 1
                if error_message:
                    logger.warning("Bytedance InvalidParameter: %s", error_info)
                if "enable thinking" in error_message and "stream" in error_message:
                    if request.get("enable_thinking") is not False:
                        request = dict(request)
                        request["enable_thinking"] = False
                        invalid_param_retries = 0
                        logger.warning("Retrying with enable_thinking disabled due to stream restriction.")
                        time.sleep(0.2)
                        continue
                if "stream" in error_message and not removed_stream and "stream" in request:
                    request = dict(request)
                    request.pop("stream", None)
                    removed_stream = True
                    invalid_param_retries = 0
                    logger.warning("Retrying without stream flag due to stream restriction.")
                    time.sleep(0.2)
                    continue
                if (not lowered_max_tokens) and request.get("max_tokens", 0) > 2048:
                    request = dict(request)
                    request["max_tokens"] = 2048
                    lowered_max_tokens = True
                    time.sleep(0.2)
                    continue
                if invalid_param_retries > 50:
                    return False, {"error": code_value}
                time.sleep(0.5)
                continue

        logger.error("Retrying ...")
        time.sleep(0.2)
    return False, {"error": last_error or "bytedance_call_failed"}


def _azure_chat_completion(
    api_url: str,
    api_key: Optional[str],
    api_version: Optional[str],
    model_name: str,
    payload: dict,
    max_tokens: Optional[int],
) -> Tuple[bool, dict]:
    client = AzureOpenAI(
        azure_endpoint=api_url,
        api_version=api_version or "2024-03-01-preview",
        api_key=api_key,
    )
    code_value = "unknown_error"
    for _ in range(3000):
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=payload["messages"],
                max_tokens=max_tokens or payload.get("max_tokens"),
                extra_headers={"X-TT-LOGID": ""},
            )
            output_message = completion.choices[0].message
            message = output_message.to_dict() if hasattr(output_message, "to_dict") else {"content": output_message}
            return True, message
        except Exception as exc:
            logger.error("Failed to call LLM: %s", exc)
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_info = exc.response.json()
                    code_value = error_info.get("error", {}).get("code", "unknown_error")
                except Exception:
                    code_value = "unknown_error"
                if code_value == "content_filter":
                    _append_content_filter_note(payload)
                if code_value == "context_length_exceeded":
                    return False, {"error": code_value}
            else:
                code_value = "unknown_error"
        logger.error("Retrying ...")
        time.sleep(0.2)
    return False, {"error": code_value}


def call_llm(payload):
    model = payload["model"]

    model_settings = resolve_model_config(model)
    api_url = model_settings.get("base_url")
    api_key = model_settings.get("api_key")
    api_version = model_settings.get("api_version")
    model_name_override = model_settings.get("model_name")
    max_tokens_override = model_settings.get("max_tokens")
    provider = model_settings.get("provider", "http")
    bypass_proxy = model_settings.get("bypass_proxy", False)
    if model_name_override:
        payload = payload.copy()
        payload["model"] = model_name_override

    payload = _prepare_payload_model_tweaks(model, payload)
    if model in _QWEN_OPENAI_MODELS:
        payload = payload.copy()
        payload["enable_thinking"] = False
        payload.setdefault("stream", False)
    if provider == "psm" and "enable_thinking" in payload:
        payload = payload.copy()
        payload.pop("enable_thinking", None)

    logger.info("Generating content with model: %s", model)

    if provider == "psm":
        return _psm_chat_completion(payload=payload, model_settings=model_settings)

    if provider == "bytedance":
        return _bytedance_chat_completion(payload=payload, model_settings=model_settings)

    if provider == "azure":
        model_name = model_name_override or model
        return _azure_chat_completion(
            api_url=api_url,
            api_key=api_key,
            api_version=api_version,
            model_name=model_name,
            payload=payload,
            max_tokens=max_tokens_override,
        )

    # Default: OpenAI-compatible HTTP endpoint
    if model in _QWEN_OPENAI_MODELS and isinstance(payload, dict):
        payload = payload.copy()
        payload["enable_thinking"] = False
        payload.setdefault("stream", False)
    return _http_chat_completion(
        api_url=api_url,
        api_key=api_key,
        payload=payload,
        model=model,
        bypass_proxy=bypass_proxy,
    )
