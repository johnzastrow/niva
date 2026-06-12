PLUGIN_NAME = niva
ZIP_FILE    = $(PLUGIN_NAME).zip

.PHONY: package clean help

help:
	@echo "Targets:"
	@echo "  package  — build $(ZIP_FILE) for QGIS ▸ Install from ZIP"
	@echo "  clean    — remove build artefacts"

package: clean
	mkdir -p $(PLUGIN_NAME)
	# The plugin sources live in this folder; copy them into a folder named
	# after the package so the zip installs as the `$(PLUGIN_NAME)` plugin.
	cp __init__.py plugin.py metadata.txt icon.svg README.md $(PLUGIN_NAME)/
	cp ../LICENSE $(PLUGIN_NAME)/ 2>/dev/null || true
	find $(PLUGIN_NAME) -name '__pycache__' -type d -prune -exec rm -rf {} +
	zip -r $(ZIP_FILE) $(PLUGIN_NAME)/
	rm -rf $(PLUGIN_NAME)
	@echo "Built $(ZIP_FILE) — install via QGIS: Plugins ▸ Install from ZIP"

clean:
	rm -rf $(PLUGIN_NAME) $(ZIP_FILE)
