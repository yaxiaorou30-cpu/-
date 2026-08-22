from src.source_policy import AccessDecision


class AllowAllSourcePolicy:
    """Explicit network-free policy used by parser and adapter unit tests."""

    def check(
        self,
        url: str,
        channel: str = "",
        access_mode: str = "public_crawler",
    ) -> AccessDecision:
        return AccessDecision(
            allowed=True,
            code="test_allowed",
            reason="unit test fixture",
            source_rule_id="SRC-TEST",
            source_name=channel or "test",
            support_level="TEST",
            access_type="TEST",
            platform_rule_status="test fixture",
            external_adapter_allowed=True,
            access_mode=access_mode,
            robots_status="test_fixture",
        )
