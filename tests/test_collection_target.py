import unittest

from src.collection_target import (
    collection_level_for_target,
    normalize_collection_target,
    parse_target_result_count,
)


class CollectionTargetTests(unittest.TestCase):
    def test_accepts_integer_targets_from_one_to_five_thousand(self):
        self.assertEqual(parse_target_result_count(1), 1)
        self.assertEqual(parse_target_result_count("30"), 30)
        self.assertEqual(parse_target_result_count(5000), 5000)

    def test_rejects_missing_non_integer_and_out_of_range_targets(self):
        for value in (None, "", True, 1.5, "1.5", 0, 5001):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_target_result_count(value)

    def test_target_selects_internal_collection_policy(self):
        self.assertEqual(collection_level_for_target(10), "最小采集")
        self.assertEqual(collection_level_for_target(11), "快速采集")
        self.assertEqual(collection_level_for_target(21), "标准采集")
        self.assertEqual(collection_level_for_target(51), "深度采集")

    def test_normalization_uses_one_target_for_limit_and_shortfall(self):
        normalized = normalize_collection_target({"max_results": "37", "min_real_results": 3})

        self.assertEqual(normalized["max_results"], 37)
        self.assertEqual(normalized["min_real_results"], 37)
        self.assertEqual(normalized["collect_level"], "标准采集")


if __name__ == "__main__":
    unittest.main()
