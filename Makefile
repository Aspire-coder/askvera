run:
	uvicorn main:app --host 0.0.0.0 --port 8080

test:
	pytest tests/unit tests/governance tests/conversation tests/conversation_pack --cov=services --cov=utils --cov=api.routes --cov-report=term-missing

lint:
	black --check .
	flake8 .

validate-config:
	python scripts/validate_config.py
