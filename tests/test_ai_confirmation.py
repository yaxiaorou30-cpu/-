import threading
import unittest

from src.ai_confirmation import AiConfirmationError, OneShotAiConfirmationStore


class OneShotAiConfirmationStoreTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000.0
        self.store = OneShotAiConfirmationStore(
            ttl_seconds=60,
            max_entries=8,
            clock=lambda: self.now,
        )

    def test_confirmation_can_be_consumed_exactly_once(self):
        confirmation_id = self.store.issue("a" * 64, "session-secret")

        self.assertEqual(
            self.store.consume_once(confirmation_id, "session-secret"),
            "a" * 64,
        )
        with self.assertRaises(AiConfirmationError):
            self.store.consume_once(confirmation_id, "session-secret")

    def test_wrong_session_cannot_consume_valid_confirmation(self):
        confirmation_id = self.store.issue("b" * 64, "session-one")

        with self.assertRaises(AiConfirmationError):
            self.store.consume_once(confirmation_id, "session-two")
        self.assertEqual(
            self.store.consume_once(confirmation_id, "session-one"),
            "b" * 64,
        )

    def test_expired_confirmation_is_rejected(self):
        confirmation_id = self.store.issue("c" * 64, "session-secret")
        self.now += 61

        with self.assertRaises(AiConfirmationError):
            self.store.consume_once(confirmation_id, "session-secret")

    def test_two_concurrent_consumers_allow_only_one_success(self):
        confirmation_id = self.store.issue("d" * 64, "session-secret")
        barrier = threading.Barrier(3)
        outcomes = []

        def consume():
            barrier.wait()
            try:
                self.store.consume_once(confirmation_id, "session-secret")
                outcomes.append("success")
            except AiConfirmationError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(outcomes.count("success"), 1)
        self.assertEqual(outcomes.count("rejected"), 1)

    def test_internal_storage_does_not_keep_raw_confirmation_or_session(self):
        confirmation_id = self.store.issue("e" * 64, "raw-session-secret")
        serialized = repr(self.store._entries)

        self.assertNotIn(confirmation_id, serialized)
        self.assertNotIn("raw-session-secret", serialized)


if __name__ == "__main__":
    unittest.main()
