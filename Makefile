PYTHON ?= python3

.PHONY: spec-check model-test check clean

spec-check:
	$(PYTHON) scripts/validate_spec.py

model-test:
	$(PYTHON) -m pytest model/tests

check: spec-check model-test

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(pathlib.Path(p), ignore_errors=True) for p in ('.pytest_cache', 'build', 'dist', 'bifrost_model.egg-info', 'model/bifrost_model.egg-info')]"
