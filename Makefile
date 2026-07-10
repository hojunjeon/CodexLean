.PHONY: test benchmark cross-benchmark build install

test:
	PYTHONPATH=src pytest -q

benchmark:
	PYTHONPATH=src python3 -m codexlean benchmark --output benchmarks/results.md
	PYTHONPATH=src python3 -m codexlean benchmark --output benchmarks/results.json

cross-benchmark:
	PYTHONPATH=src python3 benchmarks/cross_benchmark.py

build:
	python3 -m build --wheel

install:
	python3 -m pip install .
	codexlean install --scope user
