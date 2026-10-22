"""LLM providers behind one interface: client.ask_json(content, schema, effort, system) -> dict.

Anthropic uses its own SDK. Every other provider goes through the OpenAI SDK, since OpenAI,
Gemini, Groq, OpenRouter, DeepSeek, Mistral, xAI and Ollama all expose an OpenAI-compatible API.

`content` is a list of neutral parts built with text() / image(), or a plain string.
"""

import base64
import json
import os
import re
from dataclasses import dataclass


class ScoringError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    env_var: str
    model: str  # default; any model the provider offers can be typed in the app
    base_url: str | None = None  # None: the SDK's default endpoint
    key_prefix: str | None = None  # used to guess the provider from a pasted key


PROVIDERS = {p.name: p for p in [
    Provider("Anthropic", "ANTHROPIC_API_KEY", "claude-opus-5-5", key_prefix="sk-ant-"),
    Provider("OpenAI", "OPENAI_API_KEY", "gpt-5", key_prefix="sk-"),
    Provider("Google Gemini", "GEMINI_API_KEY", "gemini-2.5-flash",
             "https://generativelanguage.googleapis.com/v1beta/openai/", key_prefix="AIza"),
    Provider("Groq", "GROQ_API_KEY", "meta-llama/llama-4-scout-17b-16e-instruct",
             "https://api.groq.com/openai/v1", key_prefix="gsk_"),
    Provider("OpenRouter", "OPENROUTER_API_KEY", "openai/gpt-5",
             "https://openrouter.ai/api/v1", key_prefix="sk-or-"),
    Provider("xAI", "XAI_API_KEY", "grok-4", "https://api.x.ai/v1", key_prefix="xai-"),
    Provider("Mistral", "MISTRAL_API_KEY", "mistral-medium-latest", "https://api.mistral.ai/v1"),
    Provider("DeepSeek", "DEEPSEEK_API_KEY", "deepseek-chat", "https://api.deepseek.com"),
    Provider("Ollama (local)", "OLLAMA_API_KEY", "qwen2.5vl", "http://localhost:11434/v1"),
    Provider("Custom (OpenAI-compatible)", "LLM_API_KEY", ""),
]}

CUSTOM = "Custom (OpenAI-compatible)"


def provider_from_env(names=None):
    """First provider (optionally limited to `names`) whose API-key environment variable is set."""
    return next((p.name for p in PROVIDERS.values()
                 if (names is None or p.name in names) and os.environ.get(p.env_var)), None)


def detect_provider(api_key):
    """Guess the provider from the key's prefix (longest prefix wins); None if unknown."""
    matches = [p for p in PROVIDERS.values() if p.key_prefix and api_key.startswith(p.key_prefix)]
    return max(matches, key=lambda p: len(p.key_prefix)).name if matches else None


def text(s):
    return {"type": "text", "text": s}


def image(data, media_type="image/jpeg"):
    return {"type": "image", "data": data, "media_type": media_type}


def audio(data, fmt="mp3"):
    return {"type": "audio", "data": data, "format": fmt}


def make_client(provider="Anthropic", api_key=None, model=None, base_url=None):
    p = PROVIDERS[provider]
    api_key = api_key or os.environ.get(p.env_var)
    model = model or p.model
    if not model:
        raise ScoringError("Enter a model name")
    if not api_key and provider == "Ollama (local)":
        api_key = "ollama"  # Ollama ignores the key, but the SDK requires one
    if not api_key:
        raise ScoringError(f"Add a {provider} API key in the sidebar, or set {p.env_var}")
    if provider == "Anthropic":
        return AnthropicClient(api_key, model)
    base_url = base_url or p.base_url
    if provider == CUSTOM and not base_url:
        raise ScoringError("Enter the base URL of the OpenAI-compatible API")
    return OpenAICompatibleClient(api_key, model, base_url)


class AnthropicClient:
    def __init__(self, api_key, model):
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def ask_json(self, content, schema, effort, system=None):
        kwargs = {"system": system} if system else {}
        response = self._client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": self._content(content)}],
            **kwargs,
        )
        if response.stop_reason == "refusal":
            raise ScoringError(f"The model declined the request ({response.stop_details})")
        if response.stop_reason == "max_tokens":
            raise ScoringError("The model's answer was cut off (max_tokens); try a shorter recording")
        return json.loads(next(b.text for b in response.content if b.type == "text"))

    @staticmethod
    def _content(content):
        if isinstance(content, str):
            return content
        if any(part["type"] == "audio" for part in content):
            raise ScoringError("Claude can't listen to audio; use another transcription option")
        return [
            {"type": "image", "source": {"type": "base64", "media_type": part["media_type"],
                                         "data": base64.standard_b64encode(part["data"]).decode()}}
            if part["type"] == "image" else part
            for part in content
        ]


class OpenAICompatibleClient:
    # Not every OpenAI-compatible API supports strict JSON schemas, so fall back to JSON mode
    # with the schema in the prompt, then to plain text. The first mode that works is kept.
    MODES = ["json_schema", "json_object", "prompt"]

    def __init__(self, api_key, model, base_url=None):
        import openai

        self.model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._mode = 0

    def ask_json(self, content, schema, effort, system=None):
        import openai

        while True:
            mode = self.MODES[self._mode]
            try:
                response = self._client.chat.completions.create(
                    model=self.model, messages=self._messages(content, schema, system, mode),
                    **self._format(schema, mode),
                )
                break
            except openai.BadRequestError as e:
                if _is_media_error(e, "image"):
                    raise ScoringError(
                        f"{self.model} can't read images, which the frame checks need. "
                        "Pick a vision-capable model."
                    ) from e
                if _is_media_error(e, "audio"):
                    raise ScoringError(f"{self.model} can't listen to audio. Pick an audio-capable model.") from e
                if self._mode == len(self.MODES) - 1:
                    raise
                self._mode += 1

        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise ScoringError(f"The model declined the request ({choice.message.refusal})")
        if choice.finish_reason == "length":
            raise ScoringError("The model's answer was cut off; try a shorter recording or another model")
        answer = extract_json(choice.message.content or "")
        problem = schema_problem(schema, answer)
        if problem:
            raise ScoringError(f"{self.model} returned JSON in the wrong shape ({problem}); try a stronger model")
        return answer

    def _messages(self, content, schema, system, mode):
        if mode != "json_schema":
            # json_object mode also requires the word "JSON" in the messages.
            system = (system + "\n\n" if system else "") + (
                "Reply with a single JSON object, and nothing else, matching this JSON schema:\n"
                + json.dumps(schema)
            )
        messages = [{"role": "system", "content": system}] if system else []
        if isinstance(content, str):
            parts = content
        else:
            parts = [self._part(p) for p in content]
        messages.append({"role": "user", "content": parts})
        return messages

    @staticmethod
    def _part(p):
        if p["type"] == "image":
            return {"type": "image_url", "image_url": {
                "url": f"data:{p['media_type']};base64,{base64.standard_b64encode(p['data']).decode()}"}}
        if p["type"] == "audio":
            return {"type": "input_audio", "input_audio": {
                "data": base64.standard_b64encode(p["data"]).decode(), "format": p["format"]}}
        return p

    @staticmethod
    def _format(schema, mode):
        if mode == "json_schema":
            return {"response_format": {"type": "json_schema",
                                        "json_schema": {"name": "answer", "strict": True, "schema": schema}}}
        if mode == "json_object":
            return {"response_format": {"type": "json_object"}}
        return {}


def _is_media_error(error, kind):
    msg = str(error).lower()
    return kind in msg and any(w in msg for w in ["support", "vision", "multimodal", "modalit", "invalid content type"])


def extract_json(reply):
    """Parse a JSON object from a reply that may wrap it in ``` fences or reasoning text."""
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        pass
    start, end = reply.find("{"), reply.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(reply[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ScoringError("The model didn't return valid JSON; try a stronger model")


def schema_problem(schema, value, path="answer"):
    """Light check that `value` fits `schema` (types, required keys, enums). None if it does."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return f"{path} should be an object"
        for key in schema.get("required", []):
            if key not in value:
                return f"{path}.{key} is missing"
        for key, sub in schema.get("properties", {}).items():
            if key in value and (problem := schema_problem(sub, value[key], f"{path}.{key}")):
                return problem
        return None
    if kind == "array":
        if not isinstance(value, list):
            return f"{path} should be a list"
        for i, item in enumerate(value):
            if problem := schema_problem(schema.get("items", {}), item, f"{path}[{i}]"):
                return problem
        return None
    types = {"string": str, "boolean": bool, "integer": int, "number": (int, float)}
    if kind in types and (not isinstance(value, types[kind]) or (kind in ("integer", "number") and isinstance(value, bool))):
        return f"{path} should be a {kind}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} should be one of {schema['enum']}"
    return None
