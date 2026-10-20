"""Affiche la version lue dans apkg2cards/__init__.py (source unique de vérité)."""
import pathlib
import re

text = (pathlib.Path(__file__).parent.parent / "apkg2cards" / "__init__.py").read_text(encoding="utf-8")
print(re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1))
