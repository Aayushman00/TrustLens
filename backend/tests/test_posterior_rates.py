import random

import pytest

from app.posterior.rates import bonferroni_level, jeffreys_interval, newcombe_interval, p_exceeds


def test_jeffreys_edges():
    assert jeffreys_interval(0, 20)[0] == 0.0
    assert jeffreys_interval(20, 20)[1] == 1.0
    assert all(0.0 <= v <= 1.0 for v in jeffreys_interval(0, 20) + jeffreys_interval(20, 20))


def test_jeffreys_matches_s9():
    lvl = bonferroni_level(0.95, 3)
    assert jeffreys_interval(5, 76, lvl) == pytest.approx((0.0196, 0.1575), abs=5e-5)
    assert jeffreys_interval(100, 282, lvl) == pytest.approx((0.2889, 0.4245), abs=5e-5)


def test_jeffreys_coverage_small_n():
    rng, n, p, hit = random.Random(3), 20, 0.05, 0
    for _ in range(2000):
        k = sum(rng.random() < p for _ in range(n))
        lo, hi = jeffreys_interval(k, n)
        hit += lo <= p <= hi
    assert hit / 2000 >= 0.90


def test_newcombe_coverage_null():
    rng, n, p, hit = random.Random(5), 40, 0.1, 0
    for _ in range(2000):
        ka = sum(rng.random() < p for _ in range(n))
        kb = sum(rng.random() < p for _ in range(n))
        lo, hi = newcombe_interval(ka, n, kb, n)
        hit += lo <= 0.0 <= hi
    assert 0.93 <= hit / 2000 <= 0.97


def test_p_exceeds_matches_s9():
    assert p_exceeds(5, 76, 0.05) == pytest.approx(0.751, abs=0.005)
