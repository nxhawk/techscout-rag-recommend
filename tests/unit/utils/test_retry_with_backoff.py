"""Unit tests for the shared dependency-retry helper."""

import pytest

from src.utils.helpers import retry_with_backoff


class _Flaky:
    """Callable that raises ``exc`` for the first ``fail_times`` calls."""

    def __init__(self, fail_times: int, exc: Exception, result: str = "ok"):
        self.fail_times = fail_times
        self.exc = exc
        self.result = result
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.result


class TestRetryWithBackoff:
    def test_returns_immediately_on_success(self):
        func = _Flaky(fail_times=0, exc=ConnectionError())
        slept: list[float] = []
        out = retry_with_backoff(func, retry_on=(ConnectionError,), sleep=slept.append)
        assert out == "ok"
        assert func.calls == 1
        assert slept == []  # never waited

    def test_retries_then_succeeds(self):
        func = _Flaky(fail_times=3, exc=ConnectionError("nope"))
        slept: list[float] = []
        out = retry_with_backoff(
            func,
            retry_on=(ConnectionError,),
            base_delay=1.0,
            max_delay=5.0,
            sleep=slept.append,
        )
        assert out == "ok"
        assert func.calls == 4
        # Exponential backoff, capped at max_delay: 1, 2, 4.
        assert slept == [1.0, 2.0, 4.0]

    def test_raises_after_max_attempts(self):
        func = _Flaky(fail_times=99, exc=ConnectionError("down"))
        with pytest.raises(ConnectionError, match="down"):
            retry_with_backoff(
                func,
                retry_on=(ConnectionError,),
                max_attempts=3,
                sleep=lambda _d: None,
            )
        assert func.calls == 3  # exactly max_attempts, no extra

    def test_does_not_catch_other_exceptions(self):
        def boom() -> str:
            raise ValueError("unexpected")

        with pytest.raises(ValueError, match="unexpected"):
            retry_with_backoff(boom, retry_on=(ConnectionError,), sleep=lambda _d: None)
