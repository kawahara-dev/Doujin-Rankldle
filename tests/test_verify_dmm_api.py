import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.providers.fanza_api import DOUJIN_FLOOR, DOUJIN_SERVICE, FanzaApiProvider, normalize_items
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
