.ONESHELL:
SHELL := /bin/bash
PACKAGE=remote_kernel
VERSION_FILE=$(PACKAGE)/__init__.py
PYPROJECT=pyproject.toml

.SILENT:

local: clean
	python3 -m pip install --upgrade build twine
	python3 -m build
	pip install dist/*.whl --force-reinstall

save:
	git add .
	git commit -m "Auto-save on $$(date +'%Y-%m-%d %H:%M:%S')"
	git push

release:
	read -p "Enter release version (e.g., 1.1.0): " VERSION
	if [[ -z "$$VERSION" ]]; then
		echo "Error: Version cannot be empty!"
		exit 1
	fi
	echo "Bumping version to $$VERSION..."

	# Update __version__ in __init__.py
	if ! grep -q '__version__' $(VERSION_FILE); then
		echo "__version__ = '$$VERSION'" >> $(VERSION_FILE)
	else
		sed -i "s/^__version__ = .*/__version__ = '$$VERSION'/" $(VERSION_FILE)
	fi

	# Update version in pyproject.toml
	if grep -q '^version = ' $(PYPROJECT); then
		sed -i "s/^version = \".*\"/version = \"$$VERSION\"/" $(PYPROJECT)
	else
		echo "version = \"$$VERSION\"" >> $(PYPROJECT)
	fi

	git add $(VERSION_FILE) $(PYPROJECT)
	git commit -m "Release $$VERSION" || true

	# Recreate tag
	git tag -d "v$$VERSION" 2>/dev/null || true
	git tag -a "v$$VERSION" -m "Release $$VERSION"
	git push origin main --tags --force
	echo "New version set: $$VERSION"

publish: clean
	python3 -m build
	twine upload dist/*

clean:
	rm -rf dist build *.egg-info
