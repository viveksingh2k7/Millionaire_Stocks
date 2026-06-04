# ─────────────────────────────────────────────────────────────────
# Millionaire Stocks — Local Dev Pipeline
# Usage:  make <target>
# ─────────────────────────────────────────────────────────────────

PYTHON      = python
PIP         = $(PYTHON) -m pip
SRC         = src
TESTS       = tests

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  Millionaire Stocks — Dev Pipeline"
	@echo "  ─────────────────────────────────"
	@echo "  make install      Install all dependencies (prod + dev)"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Auto-format code with ruff"
	@echo "  make test         Run all unit tests"
	@echo "  make coverage     Run tests + print coverage report"
	@echo "  make validate     Validate trading_agent.yml YAML"
	@echo "  make security     Scan for committed .env / secrets"
	@echo "  make pipeline     Full pipeline: install → lint → test → validate → security"
	@echo "  make dry-run      Run strategy in dry-run mode (requires .env)"
	@echo "  make clean        Remove cache and coverage artefacts"
	@echo ""

# ── Install ──────────────────────────────────────────────────────
.PHONY: install
install:
	@echo "📦 Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	@echo "✅ Done"

# ── Lint ─────────────────────────────────────────────────────────
.PHONY: lint
lint:
	@echo "🔍 Running ruff linter..."
	ruff check $(SRC)/ $(TESTS)/
	@echo "✅ Lint passed"

# ── Format ───────────────────────────────────────────────────────
.PHONY: format
format:
	@echo "🎨 Formatting with ruff..."
	ruff format $(SRC)/ $(TESTS)/
	@echo "✅ Formatting done"

# ── Tests ────────────────────────────────────────────────────────
.PHONY: test
test:
	@echo "🧪 Running tests..."
	ALPACA_API_KEY=test-key \
	ALPACA_SECRET_KEY=test-secret \
	ALPACA_BASE_URL=https://paper-api.alpaca.markets \
	pytest $(TESTS)/ -v --tb=short
	@echo "✅ Tests passed"

# ── Coverage ─────────────────────────────────────────────────────
.PHONY: coverage
coverage:
	@echo "📊 Running tests with coverage..."
	ALPACA_API_KEY=test-key \
	ALPACA_SECRET_KEY=test-secret \
	ALPACA_BASE_URL=https://paper-api.alpaca.markets \
	pytest $(TESTS)/ --cov=$(SRC) --cov-report=term-missing --cov-report=html
	@echo "✅ Coverage report → htmlcov/index.html"

# ── Validate YAML ────────────────────────────────────────────────
.PHONY: validate
validate:
	@echo "✅ Validating workflows/trading_agent.yml..."
	@$(PYTHON) -c "\
	import yaml, sys; \
	doc = yaml.safe_load(open('workflows/trading_agent.yml')); \
	assert 'jobs' in doc, 'Missing jobs'; \
	print('✅ trading_agent.yml is valid YAML') \
	"

# ── Security scan ────────────────────────────────────────────────
.PHONY: security
security:
	@echo "🔒 Checking for committed .env..."
	@if git ls-files | grep -E '^\.env$$'; then \
		echo "ERROR: .env is tracked — remove with: git rm --cached .env"; exit 1; \
	else echo "✅ .env not committed"; fi
	@echo "🔒 Scanning for hardcoded secrets..."
	@if grep -rn --include="*.py" \
		-E "(APCA-API-[A-Z]+-[A-Z0-9]{20}|sk_[a-z0-9]{40})" $(SRC)/; then \
		echo "ERROR: Possible hardcoded secret in src/"; exit 1; \
	else echo "✅ No hardcoded secrets"; fi

# ── Full pipeline ────────────────────────────────────────────────
.PHONY: pipeline
pipeline: install lint test validate security
	@echo ""
	@echo "🚀 ════════════════════════════════════════"
	@echo "🚀  Pipeline complete — all checks passed!"
	@echo "🚀 ════════════════════════════════════════"

# ── Dry run (local) ──────────────────────────────────────────────
.PHONY: dry-run
dry-run:
	@echo "🧪 Starting dry-run (no real orders)..."
	@if [ -f .env ]; then \
		export $$(grep -v '^#' .env | xargs) && DRY_RUN=true $(PYTHON) $(SRC)/strategy.py; \
	else \
		echo "ERROR: .env file not found. Copy .env.example → .env and fill in your keys."; exit 1; \
	fi

# ── Clean ────────────────────────────────────────────────────────
.PHONY: clean
clean:
	@echo "🧹 Cleaning artefacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ coverage.xml .coverage
	@echo "✅ Clean"
