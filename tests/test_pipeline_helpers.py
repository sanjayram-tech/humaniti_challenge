import unittest

from scoring.claude_scoring import gates_from_frames
from scoring.transcribe import parse_transcript_file


def frame(bg=True, face=True, lighting="good", glitch=False):
    return {"chessboard_background": bg, "face_visible": face, "lighting": lighting, "glitch": glitch}


class GatesTest(unittest.TestCase):
    def test_clean_class_passes_everything(self):
        gates, _ = gates_from_frames([frame()] * 10, transcript_confidence=0.75)
        self.assertEqual(set(gates.values()), {"pass"})

    def test_camera_off_part_of_class_is_partial(self):
        frames = [frame()] * 7 + [frame(face=False, lighting="no_face")] * 3
        gates, metrics = gates_from_frames(frames, 0.75)
        self.assertEqual(gates["camera_face"], "partial")
        self.assertEqual(metrics["face_visible"], 0.7)

    def test_no_background_fails(self):
        gates, _ = gates_from_frames([frame(bg=False)] * 10, 0.75)
        self.assertEqual(gates["background"], "fail")

    def test_poor_audio_fails_clarity(self):
        gates, _ = gates_from_frames([frame()] * 10, transcript_confidence=0.3)
        self.assertEqual(gates["av_clarity"], "fail")


class TranscriptParseTest(unittest.TestCase):
    def test_srt(self):
        srt = "1\n00:00:05,000 --> 00:00:09,500\nHi Arjun,\nhow was school?\n\n2\n00:01:20,000 --> 00:01:24,000\nHomework: puzzles 1-5\n"
        segs = parse_transcript_file(srt)
        self.assertEqual([s["start"] for s in segs], [5.0, 80.0])
        self.assertEqual(segs[0]["text"], "Hi Arjun, how was school?")

    def test_plain_text(self):
        self.assertEqual(len(parse_transcript_file("hello\n\nworld\n")), 2)


if __name__ == "__main__":
    unittest.main()
