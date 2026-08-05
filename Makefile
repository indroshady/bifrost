PYTHON ?= python3
VERILATOR ?= verilator
VERILATOR_FLAGS ?= --binary --timing --assert -Wall -Wno-fatal
RTL_SOURCES := rtl/bifrost_pkg.sv \
	rtl/bifrost_route_decode.sv \
	rtl/bifrost_input_vc.sv \
	rtl/bifrost_credit_counter.sv \
	rtl/bifrost_crossbar.sv \
	rtl/bifrost_router.sv
SIM_BUILD := sim_build

.PHONY: spec-check model-test rtl-lint rtl-test check clean

spec-check:
	$(PYTHON) scripts/validate_spec.py

model-test:
	$(PYTHON) -m pytest model/tests

$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)

rtl-lint: | $(SIM_BUILD)
	$(VERILATOR) --lint-only --timing --assert -Wall -Wno-fatal --top-module bifrost_router $(RTL_SOURCES)

rtl-test: rtl-lint
	$(VERILATOR) $(VERILATOR_FLAGS) --top-module tb_bifrost_router --Mdir $(SIM_BUILD)/directed $(RTL_SOURCES) verification/rtl/tb_bifrost_router.sv
	$(SIM_BUILD)/directed/Vtb_bifrost_router
	$(VERILATOR) $(VERILATOR_FLAGS) --top-module tb_bifrost_routes --Mdir $(SIM_BUILD)/routes $(RTL_SOURCES) verification/rtl/tb_bifrost_routes.sv
	$(SIM_BUILD)/routes/Vtb_bifrost_routes
	$(VERILATOR) $(VERILATOR_FLAGS) --top-module tb_bifrost_random --Mdir $(SIM_BUILD)/random $(RTL_SOURCES) verification/rtl/tb_bifrost_random.sv
	$(SIM_BUILD)/random/Vtb_bifrost_random
	$(VERILATOR) $(VERILATOR_FLAGS) --top-module tb_bifrost_protocol_error --Mdir $(SIM_BUILD)/protocol $(RTL_SOURCES) verification/rtl/tb_bifrost_protocol_error.sv
	@if $(SIM_BUILD)/protocol/Vtb_bifrost_protocol_error >$(SIM_BUILD)/protocol.log 2>&1; then \
		cat $(SIM_BUILD)/protocol.log; \
		echo "protocol violation simulation unexpectedly passed"; \
		exit 1; \
	else \
		grep -q "illegal packet marker sequence" $(SIM_BUILD)/protocol.log && \
		echo "PASS: invalid packet protocol assertion fired"; \
	fi

check: spec-check model-test rtl-test

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(pathlib.Path(p), ignore_errors=True) for p in ('.pytest_cache', 'build', 'dist', 'bifrost_model.egg-info', 'model/bifrost_model.egg-info')]"
	rm -rf $(SIM_BUILD)
