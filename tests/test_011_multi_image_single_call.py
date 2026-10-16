import json
import unittest
from pathlib import Path
from tests.synthetic_fixtures import SYNTHETIC_IMAGE_PATH
from unittest.mock import patch

from config import ModelConfig, settings
from clients.vision_client import VisionClient


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    SYNTHETIC_IMAGE_PATH,
    SYNTHETIC_IMAGE_PATH,
]


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class MultiImageSingleCallTests(unittest.TestCase):
    def setUp(self):
        self.client = VisionClient()
        self.model = ModelConfig(
            name="unit-test-vision",
            provider="deepseek",
            api_key="test-only-api-key-013",
            base_url="https://api.deepseek.com",
            model_id="deepseek-v4-flash-vision-exp",
            type="vision",
        )
        self.output = {
            "questions": [
                {
                    "image_index": 0,
                    "question_no": "1",
                    "question_text": "3 + 5 = ?",
                    "student_answer": "8",
                    "score": 10,
                    "max_score": 10,
                    "result": "correct",
                },
                {
                    "image_index": 1,
                    "question_no": "A",
                    "question_text": "1/2 + 1/4 = ?",
                    "student_answer": "3/4",
                    "score": 10,
                    "max_score": 10,
                    "result": "correct",
                },
            ]
        }

    def test_multiple_images_share_one_provider_request_and_keep_page_index(self):
        calls = []
        response = _Response({
            "choices": [{"message": {"content": json.dumps(self.output)}}]
        })

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            return response

        with patch("clients.vision_client.urllib.request.urlopen", side_effect=fake_urlopen):
            results = self.client.grade_homework_images_directly(
                [str(path) for path in SAMPLES], self.model
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(calls[0][1], settings.VISION_REQUEST_TIMEOUT_SECONDS)
        body = json.loads(calls[0][0].data.decode("utf-8"))
        content = body["messages"][0]["content"]
        self.assertEqual(sum(item.get("type") == "image_url" for item in content), 2)
        self.assertEqual([result["image_index"] for result in results], [0, 1])

    def test_multi_image_result_without_page_mapping_fails_closed(self):
        payload = {"choices": [{"message": {"content": json.dumps({
            "questions": [{"question_no": "1", "question_text": "unmapped", "result": "wrong"}]
        })}}]}
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)
            return _Response(payload)

        with patch("clients.vision_client.urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(ValueError, "image_index"):
                self.client.grade_homework_images_directly(
                    [str(path) for path in SAMPLES], self.model
                )
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
