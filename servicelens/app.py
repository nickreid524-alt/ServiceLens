"""Entry point.

    python -m servicelens

DPI awareness has to be declared to Windows before Tk is created, which is
why it happens here rather than inside the window.
"""

from __future__ import annotations

import argparse


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m servicelens",
        description="ServiceLens - work order intelligence for maintenance "
                    "and service operations.")
    parser.add_argument(
        "workbook", nargs="?", default=None,
        help="an .xlsx work order export to open on launch")
    parser.add_argument(
        "--demo", action="store_true",
        help="open the synthetic demonstration workbook on launch")
    parser.add_argument(
        "--scale", type=float, default=None,
        help="override the display scaling factor, for checking the layout "
             "at 1.0, 1.25 or 1.5 on a display set to something else")
    arguments = parser.parse_args(argv)

    from .ui.theme import enable_dpi_awareness
    enable_dpi_awareness()

    workbook = arguments.workbook
    if arguments.demo and not workbook:
        from .ui.shell import DEMO_WORKBOOK, project_root
        workbook = str(project_root() / "demo" / DEMO_WORKBOOK)

    from .ui.shell import run
    run(scale=arguments.scale, workbook=workbook)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
