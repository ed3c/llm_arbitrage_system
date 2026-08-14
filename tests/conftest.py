from __future__ import annotations

import asyncio
import inspect
from typing import Any


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "asyncio: run an offline coroutine test")


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    arguments = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(pyfuncitem.obj(**arguments))
    return True
