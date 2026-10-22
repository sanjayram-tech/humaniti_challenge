import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from scoring import transcribe


class TranscribeApiTest(unittest.TestCase):
    def test_offsets_chunks_and_reads_confidence(self):
        replies = [
            SimpleNamespace(text="hi", segments=[
                SimpleNamespace(start=0.0, end=2.0, text=" Hello class ", avg_logprob=-0.2)]),
            {"text": "bye", "segments": [{"start": 1.0, "end": 3.0, "text": "Bye", "avg_logprob": -0.4}]},
        ]
        with TemporaryDirectory() as tmp:
            chunks = []
            for i, offset in enumerate([0.0, 1200.0]):
                path = Path(tmp) / f"chunk_{i}.mp3"
                path.write_bytes(b"x")
                chunks.append((offset, path))
            with mock.patch("openai.OpenAI") as client_cls:
                client_cls.return_value.audio.transcriptions.create.side_effect = replies
                segments, confidence = transcribe.transcribe_api(chunks, "gsk_x", "whisper-large-v3",
                                                                 "https://api.groq.com/openai/v1")
        self.assertEqual(segments, [
            {"start": 0.0, "end": 2.0, "text": "Hello class"},
            {"start": 1201.0, "end": 1203.0, "text": "Bye"},
        ])
        self.assertAlmostEqual(confidence, 0.7408, places=3)  # exp(mean(-0.2, -0.4))

    def test_text_without_segments(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.mp3"
            path.write_bytes(b"x")
            with mock.patch("openai.OpenAI") as client_cls:
                client_cls.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
                    text="whole class", segments=None)
                segments, confidence = transcribe.transcribe_api([(60.0, path)], "k", "m")
        self.assertEqual(segments, [{"start": 60.0, "end": 60.0, "text": "whole class"}])
        self.assertEqual(confidence, 1.0)


class GeminiTranscriptionTest(unittest.TestCase):
    def test_sends_audio_and_offsets_segments(self):
        answers = [
            '{"segments": [{"start": 1.5, "end": 4, "text": " Good morning "}]}',
            '{"segments": [{"start": 0, "end": 2, "text": "Bye"}, {"start": 3, "end": 3, "text": " "}]}',
        ]
        replies = [SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=a, refusal=None), finish_reason="stop")]) for a in answers]
        with TemporaryDirectory() as tmp:
            chunks = []
            for i, offset in enumerate([0.0, 600.0]):
                path = Path(tmp) / f"chunk_{i}.mp3"
                path.write_bytes(b"")
                chunks.append((offset, path))
            with mock.patch("openai.OpenAI") as client_cls:
                create = client_cls.return_value.chat.completions.create
                create.side_effect = replies
                segments, confidence = transcribe.transcribe_api(
                    chunks, "AIza-x", "gemini-2.5-flash", "https://g/openai/", provider="Google Gemini")
        self.assertEqual(segments, [
            {"start": 1.5, "end": 4, "text": "Good morning"},
            {"start": 600.0, "end": 602.0, "text": "Bye"},
        ])
        self.assertEqual(confidence, 1.0)
        audio_part = create.call_args.kwargs["messages"][-1]["content"][0]
        self.assertEqual(audio_part, {"type": "input_audio", "input_audio": {"data": "AQI=", "format": "mp3"}})

    def test_chunk_length_per_kind(self):
        self.assertEqual(transcribe.CHUNK_SECONDS[transcribe.api_kind("Google Gemini")], 600)
        self.assertEqual(transcribe.CHUNK_SECONDS[transcribe.api_kind(None)], 1200)


if __name__ == "__main__":
    unittest.main()
