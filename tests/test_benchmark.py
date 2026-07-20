from codexlean import __version__
from codexlean.benchmark import run_benchmark


def test_benchmark_quality_gates_and_safe_savings():
    report = run_benchmark(["strict", "safe", "max"])
    assert report["version"] == __version__
    assert report["quality_failures"] == 0
    safe = report["profiles"]["safe"]["summary"]
    assert safe["byte_savings_ratio"] > 0.45
    assert safe["transformed"] >= 7
