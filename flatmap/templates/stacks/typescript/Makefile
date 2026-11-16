.PHONY: install lint fmt typecheck test build check

install:
	if [ -f package-lock.json ]; then npm ci; else npm install; fi

lint:
	npm run lint

fmt:
	npm run fmt

typecheck:
	npm run typecheck

test:
	npm test

build:
	npm run build

check: lint typecheck test build
