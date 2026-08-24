import time

from offcatalog.ratelimit import TokenBucket


def test_token_bucket_allows_burst_up_to_rate():
    bucket = TokenBucket(rate=5, per_seconds=1.0)
    start = time.monotonic()
    for _ in range(5):
        bucket.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.2  # first `rate` calls should not sleep meaningfully


def test_token_bucket_throttles_beyond_rate():
    bucket = TokenBucket(rate=2, per_seconds=0.4)
    start = time.monotonic()
    for _ in range(3):
        bucket.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.3
