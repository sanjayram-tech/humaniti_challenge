import json
import unittest
from types import SimpleNamespace
from unittest import mock

import openai

from scoring.llm import (
    OpenAICompatibleClient, ScoringError, detect_provider, extract_json, image, make_client,
    schema_problem, text,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "tags"],
    "additionalProperties": False,
}


def reply(content, finish_reason="stop"):
    message = SimpleNamespace(content=content, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def bad_request(message):
    response = mock.Mock(status_code=400, headers={})
    return openai.BadRequestError(message, response=response, body=None)


class DetectProviderTest(unittest.TestCase):
    def test_prefixes(self):
        self.assertEqual(detect_provider("sk-ant-api03-abc"), "Anthropic")
        self.assertEqual(detect_provider("sk-or-v1-abc"), "OpenRouter")
        self.assertEqual(detect_provider("sk-proj-abc"), "OpenAI")
        self.assertEqual(detect_provider("AIzaSyabc"), "Google Gemini")
        self.assertEqual(detect_provider("gsk_abc"), "Groq")
        self.assertEqual(detect_provider("xai-abc"), "xAI")
        self.assertIsNone(detect_provider("abc123"))


class MakeClientTest(unittest.TestCase):
    def test_missing_key_is_a_clear_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ScoringError, "OPENAI_API_KEY"):
                make_client("OpenAI")

    def test_ollama_needs_no_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            client = make_client("Ollama (local)")
        self.assertEqual(str(client._client.base_url), "http://localhost:11434/v1/")

    def test_custom_needs_base_url(self):
        with self.assertRaisesRegex(ScoringError, "base URL"):
            make_client("Custom (OpenAI-compatible)", "key", "some-model")


class ExtractJsonTest(unittest.TestCase):
    def test_plain_fenced_and_reasoning(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('Here:\n```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('<think>{maybe}</think>{"a": 1}'), {"a": 1})
        with self.assertRaises(ScoringError):
            extract_json("no json here")


class SchemaProblemTest(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(schema_problem(SCHEMA, {"score": 4, "tags": ["x"]}))

    def test_problems(self):
        self.assertIn("score is missing", schema_problem(SCHEMA, {"tags": []}))
        self.assertIn("one of", schema_problem(SCHEMA, {"score": 7, "tags": []}))
        self.assertIn("integer", schema_problem(SCHEMA, {"score": "4", "tags": []}))
        self.assertIn("tags[0]", schema_problem(SCHEMA, {"score": 4, "tags": [1]}))


class OpenAICompatibleClientTest(unittest.TestCase):
    def setUp(self):
        self.client = OpenAICompatibleClient("key", "model", "http://localhost/v1")
        self.create = mock.Mock()
        self.client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))

    def test_sends_images_as_data_urls(self):
        self.create.return_value = reply(json.dumps({"score": 5, "tags": []}))
        answer = self.client.ask_json([text("look"), image(b"\xff\xd8")], SCHEMA, effort="low")
        self.assertEqual(answer["score"], 5)
        parts = self.create.call_args.kwargs["messages"][-1]["content"]
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/jpeg;base64,/9g=")
        self.assertEqual(self.create.call_args.kwargs["response_format"]["type"], "json_schema")

    def test_falls_back_when_json_schema_is_unsupported(self):
        self.create.side_effect = [bad_request("response_format json_schema not supported"),
                                   reply('{"score": 3, "tags": []}')]
        self.assertEqual(self.client.ask_json("hi", SCHEMA, effort="high")["score"], 3)
        second = self.create.call_args.kwargs
        self.assertEqual(second["response_format"], {"type": "json_object"})
        self.assertIn("JSON schema", second["messages"][0]["content"])

    def test_model_without_vision(self):
        self.create.side_effect = bad_request("This model does not support image input")
        with self.assertRaisesRegex(ScoringError, "vision"):
            self.client.ask_json([image(b"x")], SCHEMA, effort="low")

    def test_wrong_shape_and_truncation(self):
        self.create.return_value = reply('{"score": 3}')
        with self.assertRaisesRegex(ScoringError, "wrong shape"):
            self.client.ask_json("hi", SCHEMA, effort="low")
        self.create.return_value = reply('{"sc', finish_reason="length")
        with self.assertRaisesRegex(ScoringError, "cut off"):
            self.client.ask_json("hi", SCHEMA, effort="low")


if __name__ == "__main__":
    unittest.main()
