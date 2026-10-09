.PHONY: check lint types test migrate run mobile-check mobile-verify auth-release-check

check: lint types test mobile-check

lint:
	.venv/bin/ruff check app tests
	.venv/bin/ruff format --check app tests

types:
	.venv/bin/mypy app

test:
	.venv/bin/pytest

migrate:
	RUN_ENV=local .venv/bin/python -m app.migrate

run:
	RUN_ENV=local .venv/bin/python -m app.run

mobile-check:
	npm --prefix mobile run check

mobile-verify:
	npm --prefix mobile run verify:ios

# Safe post-deploy probe: malformed auth requests verify route contracts without sending email.
auth-release-check:
	.venv/bin/python tools/check_auth_release.py https://api.trove.zyphrlabs.com
