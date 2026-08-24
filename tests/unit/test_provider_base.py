from offcatalog.providers.base import (
    PROVIDER_REGISTRY,
    ProviderError,
    register_provider,
)


def test_register_provider_adds_to_registry():
    PROVIDER_REGISTRY.clear()

    @register_provider
    class FakeProvider:
        name = "fake"

        def search_by_isrc(self, isrc):
            return None

        def search_track(self, track):
            return []

    assert PROVIDER_REGISTRY["fake"] is FakeProvider


def test_provider_error_is_exception():
    assert issubclass(ProviderError, Exception)
