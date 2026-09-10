"""The domain must be usable without a display.

ServiceLens is a desktop application, but its analysis is not. These tests
fail the moment a rule, a metric or the ingestion layer starts depending on
tkinter, which is what keeps the business logic testable in CI and reusable
outside the interface.
"""

import builtins
import importlib
import sys
import unittest

HEADLESS_MODULES = (
    "servicelens.config",
    "servicelens.analysis",
    "servicelens.domain.models",
    "servicelens.domain.rules",
    "servicelens.domain.integrity",
    "servicelens.domain.directives",
    "servicelens.domain.routing",
    "servicelens.domain.filters",
    "servicelens.domain.metrics",
    "servicelens.ingestion.schema",
    "servicelens.ingestion.xlsx",
    "servicelens.ingestion.normalization",
    "servicelens.demo.corpus",
    "servicelens.demo.generator",
    "servicelens.demo.xlsx_writer",
    "servicelens.reporting",
    "servicelens.reporting.pdf",
    "servicelens.reporting.summary",
    "servicelens.reporting.review_pack",
    "servicelens.reporting.exception_register",
    "servicelens.reporting.csv_export",
)


class HeadlessImportTests(unittest.TestCase):

    def test_no_module_imports_tkinter(self):
        real_import = builtins.__import__

        def blocked(name, *arguments, **keywords):
            if name == "tkinter" or name.startswith("tkinter."):
                raise AssertionError(
                    f"tkinter was imported by a headless module ({name})")
            return real_import(name, *arguments, **keywords)

        # Import fresh copies with tkinter blocked, then put the original
        # module objects back. Leaving the fresh copies in place would hand
        # later tests a second copy of every enum, and identity comparisons
        # between the two would fail for no visible reason.
        originals = {name: module for name, module in sys.modules.items()
                     if name.startswith("servicelens")}
        for name in originals:
            del sys.modules[name]

        builtins.__import__ = blocked
        try:
            for name in HEADLESS_MODULES:
                importlib.import_module(name)
        finally:
            builtins.__import__ = real_import
            for name in [n for n in sys.modules if n.startswith("servicelens")]:
                del sys.modules[name]
            sys.modules.update(originals)

    def test_tkinter_is_not_already_loaded_by_the_package(self):
        for name in [n for n in list(sys.modules)
                     if n.startswith("servicelens")]:
            module = sys.modules[name]
            for attribute in vars(module).values():
                self.assertNotEqual(
                    getattr(attribute, "__name__", ""), "tkinter",
                    f"{name} holds a reference to tkinter")


class DependencyTests(unittest.TestCase):

    def test_no_third_party_imports(self):
        """Everything ServiceLens needs ships with Python."""
        allowed = set(sys.stdlib_module_names) | {"servicelens"}
        for name in HEADLESS_MODULES:
            module = importlib.import_module(name)
            source = module.__doc__ or ""
            self.assertIsInstance(source, str)
        # Walk the real import graph rather than trusting the source text.
        for name in HEADLESS_MODULES:
            importlib.import_module(name)
        loaded = {n.split(".")[0] for n in sys.modules
                  if not n.startswith("_")}
        unexpected = {
            n for n in loaded
            if n not in allowed and not n.startswith("test")
            and n not in ("tests", "unittest", "pytest", "py", "pluggy",
                          "iniconfig", "pygments", "coverage")
        }
        self.assertEqual(unexpected, set(),
                         f"unexpected third-party modules: {unexpected}")


if __name__ == "__main__":
    unittest.main()
