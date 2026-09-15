"""Build an installable QGIS ZIP from a clean allowlist, using Python 3."""

from configparser import ConfigParser
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    plugin = root / "j3m_connect"
    config = json.loads((plugin / "config.json").read_text(encoding="utf-8-sig"))
    if (not isinstance(config, dict) or set(config) != {"api_url"}
            or not isinstance(config["api_url"], str) or not config["api_url"].strip()):
        raise ValueError("Preencha apenas api_url em j3m_connect/config.json antes de empacotar.")
    metadata = ConfigParser()
    metadata.read(plugin / "metadata.txt", encoding="utf-8")
    version = metadata["general"]["version"]
    output = root / "dist" / ("j3m_connect-" + version + ".zip")
    output.parent.mkdir(exist_ok=True)
    files = ["__init__.py", "metadata.txt", "j3m_connect.py", "api.py",
             "adapters.py", "settings.py", "layers.py", "dialog.py", "dialog.ui", "j3m-logo.jpeg",
             "config.json", "map_tips.py"]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(plugin / name, "j3m_connect/" + name)
        for name in ("LICENSE", "README.md", "CHANGELOG.md"):
            archive.write(root / name, "j3m_connect/" + name)
    print(output)


if __name__ == "__main__":
    main()
