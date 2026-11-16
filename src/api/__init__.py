"""
Headless experiment API for the confocal control software.

The modules in this package let an agent (or a script, or the Qt GUI)
run experiments through one control surface:

    plan.py     parameter validation and dry-run planning (no hardware)
    jobs.py     background job runner shared by the CLI and the server
    render.py   matplotlib (Agg) figures -> PNG, no Qt window needed
    server.py   localhost HTTP control service, also embeddable in the GUI
    client.py   thin HTTP client used by the CLI
    cli.py      command line entry point

Design rule: exactly one process owns the hardware.  When the Qt GUI is
open it hosts the service (and mirrors the parameters into its widgets);
when it is closed the CLI starts the same runner in-process.
"""

__all__ = ["models", "plan", "jobs", "render", "server", "client"]
