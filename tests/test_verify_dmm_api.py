import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from src.inspect_dmm_floors import normalize_floors
from src.providers.fanza_api import (
    DOUJIN_FLOOR,
    DOUJIN_SERVICE,
    DmmApiRequestError,
    FanzaApiProvider,
    normalize_items,
    request_json,
)
from src.verify_dmm_api import classify, compare, item_key, load_manual, run


def items(keys):
    return [{"rank": rank, "id": key, "key": key, "title": key, "price": 1, "url": "", "affiliate_url": "", "image_url": "", "service": DOUJIN_SERVICE, "floor": DOUJIN_FLOOR} for rank, key in enumerate(keys, 1)]


class StubProvider:
    def __init__(self, result): self.result = result
    def fetch(self): return self.result


class VerifyDmmApiTests(unittest.TestCase):
    def test_normalization_and_content_id_key(self):
        result = normalize_items([{"content_id": "d_1", "title": "作品", "prices": {"price": "1,200"}, "URL": "normal", "affiliateURL": "affiliate", "imageURL": {"large": "image"}}], service=DOUJIN_SERVICE, floor=DOUJIN_FLOOR)
        self.assertEqual(result[0], {"rank": 1, "id": "d_1", "key": "d_1", "title": "作品", "price": 1200, "url": "normal", "affiliate_url": "affiliate", "image_url": "image", "service": "doujin", "floor": "digital_doujin"})
        self.assertEqual(item_key({"content_id": "d_2"}), "d_2")

    def test_overlap_exact_and_average(self):
        result = compare(items(["a", "b", "c", "d"]), items(["a", "c", "b", "x"]))
        self.assertEqual(result, {"matched_products": 3, "overlap_rate": 75.0, "exact_rank_matches": 1, "exact_rank_rate": 25.0, "average_rank_difference": 0.67})

    def test_classifications(self):
        high = {"overlap_rate": 85, "average_rank_difference": 1}
        medium = {"overlap_rate": 65, "average_rank_difference": 4}
        low = {"overlap_rate": 40, "average_rank_difference": 8}
        self.assertEqual(classify(high, medium)["likely_match"], "1h")
        self.assertEqual(classify(medium, high)["likely_match"], "24h")
        self.assertEqual(classify(low, low)["likely_match"], "neither")
        self.assertEqual(classify(high, {"overlap_rate": 80, "average_rank_difference": 1.5})["likely_match"], "uncertain")

    def test_empty_api_response(self):
        with self.assertRaisesRegex(RuntimeError, "no items"):
            normalize_items([], service=DOUJIN_SERVICE, floor=DOUJIN_FLOOR)

    def test_missing_manual_current(self):
        with self.assertRaises(FileNotFoundError): load_manual(Path("does-not-exist"))

    def test_missing_secrets(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "required"):
            FanzaApiProvider().fetch()

    def test_http_400_includes_body_but_redacts_credentials(self):
        api_id = "secret-api-id"
        affiliate_id = "secret-affiliate-id"
        body = json.dumps(
            {
                "request": {"api_id": api_id, "affiliate_id": affiliate_id},
                "result": {"message": "floor parameter is invalid", "errors": [{"code": "BAD_FLOOR"}]},
                "message": f"rejected {api_id}",
            }
        ).encode()
        error = HTTPError("https://example.invalid/?api_id=secret-api-id", 400, "Bad Request", {}, BytesIO(body))
        with patch("src.providers.fanza_api.urlopen", side_effect=error):
            with self.assertRaises(DmmApiRequestError) as raised:
                request_json("https://example.invalid", {"api_id": api_id, "affiliate_id": affiliate_id})
        message = str(raised.exception)
        self.assertIn("status: 400", message)
        self.assertIn("floor parameter is invalid", message)
        self.assertIn("BAD_FLOOR", message)
        self.assertNotIn(api_id, message)
        self.assertNotIn(affiliate_id, message)
        self.assertNotIn("https://", message)

    def test_floor_api_normalization_preserves_all_returned_floors(self):
        payload = {
            "result": {
                "site": [
                    {"code": "DMM.com", "name": "一般"},
                    {
                        "code": "FANZA",
                        "name": "FANZA",
                        "service": [
                            {
                                "code": "service-a",
                                "name": "サービスA",
                                "floor": [
                                    {"code": "floor-1", "name": "フロア1"},
                                    {"code": "floor-2", "name": "フロア2"},
                                ],
                            }
                        ],
                    },
                ]
            }
        }
        self.assertEqual(
            normalize_floors(payload),
            {
                "site": "FANZA",
                "services": [
                    {
                        "service_code": "service-a",
                        "service_name": "サービスA",
                        "floors": [
                            {"floor_code": "floor-1", "floor_name": "フロア1"},
                            {"floor_code": "floor-2", "floor_name": "フロア2"},
                        ],
                    }
                ],
            },
        )

    def test_run_only_writes_verify_output(self):
        api = items([f"p{i}" for i in range(20)])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data/verify/result.json"
            with patch("src.verify_dmm_api.load_manual", return_value=api):
                result = run(provider=StubProvider(api), output=output)
            self.assertTrue(output.is_file())
            self.assertEqual(json.loads(output.read_text())["mode"], "verify_dry_run")
            self.assertEqual(result["summary"]["likely_match"], "uncertain")
            self.assertEqual([p for p in Path(directory).rglob("*") if p.is_file()], [output])

    def test_run_rejects_fewer_than_twenty(self):
        with self.assertRaisesRegex(RuntimeError, "at least 20"):
            run(provider=StubProvider(items(["one"])))


if __name__ == "__main__":
    unittest.main()
