"""Fail-closed contracts for the default validator container entrypoint."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable

import pytest

from scripts import validator_entrypoint

FAILURE_MESSAGE = "[entrypoint] validator bootstrap failed\n"


def _clear_entrypoint_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ROLE",
        "KUBETEE_SUBNET_NETUID",
        "KUBETEE_OWNER_WALLET",
        "BT_WALLET",
        "BT_NETWORK",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_validator_setup_is_checked_and_success_execs_exact_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_entrypoint_environment(monkeypatch)
    monkeypatch.setenv("KUBETEE_ENTRYPOINT_TEST_MARKER", "environment-copy")
    expected_setup = [
        sys.executable,
        "-u",
        "scripts/setup_single_node.py",
        "--netuid",
        "1",
        "--owner-wallet",
        "owner",
        "--chain-endpoint",
        "ws://chain:9944",
    ]
    setup_observations: dict[str, bool] = {}
    exec_observations: dict[str, bool] = {}

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        environment = kwargs.get("env")
        setup_observations.update(
            {
                "command": command == expected_setup,
                "check": kwargs.get("check") is True,
                "capture_output": kwargs.get("capture_output") is True,
                "text": kwargs.get("text") is True,
                "environment": (
                    isinstance(environment, dict)
                    and environment is not os.environ
                    and environment.get("KUBETEE_ENTRYPOINT_TEST_MARKER")
                    == "environment-copy"
                ),
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fake_execv(path: str, argv: list[str]) -> None:
        exec_observations.update(
            {
                "path": path == sys.executable,
                "argv": argv == [sys.executable, "scripts/validator.py"],
            }
        )

    monkeypatch.setattr(validator_entrypoint.subprocess, "run", fake_run)
    monkeypatch.setattr(validator_entrypoint.os, "execv", fake_execv)

    validator_entrypoint.main()

    assert setup_observations == {
        "command": True,
        "check": True,
        "capture_output": True,
        "text": True,
        "environment": True,
    }
    assert exec_observations == {"path": True, "argv": True}


def _assert_setup_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_factory: Callable[[], Exception],
) -> None:
    hostile_values = {
        "KUBETEE_SUBNET_NETUID": "netuid-hostile-marker",
        "KUBETEE_OWNER_WALLET": "owner-hostile-marker",
        "BT_WALLET": "validator-hostile-marker",
        "BT_NETWORK": "endpoint-hostile-marker",
    }
    for name, value in hostile_values.items():
        monkeypatch.setenv(name, value)
    setup_observations: dict[str, bool] = {}
    exec_called = False

    def fake_run(command: list[str], **kwargs: object) -> None:
        setup_observations.update(
            {
                "called": bool(command),
                "check": kwargs.get("check") is True,
                "capture_output": kwargs.get("capture_output") is True,
                "text": kwargs.get("text") is True,
            }
        )
        raise failure_factory()

    def fake_execv(_path: str, _argv: list[str]) -> None:
        nonlocal exec_called
        exec_called = True

    monkeypatch.setattr(validator_entrypoint.subprocess, "run", fake_run)
    monkeypatch.setattr(validator_entrypoint.os, "execv", fake_execv)

    with pytest.raises(SystemExit) as raised:
        validator_entrypoint.main()

    captured = capsys.readouterr()
    assert raised.value.code == 1
    assert captured.out == ""
    assert captured.err == FAILURE_MESSAGE
    assert setup_observations == {
        "called": True,
        "check": True,
        "capture_output": True,
        "text": True,
    }
    assert exec_called is False


def test_nonzero_setup_is_redacted_and_never_execs_validator(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failure() -> subprocess.CalledProcessError:
        return subprocess.CalledProcessError(
            17,
            ["command-hostile-marker"],
            output="stdout-hostile-marker",
            stderr="stderr-hostile-marker",
        )

    _assert_setup_failure_is_redacted(monkeypatch, capsys, failure)


def test_setup_launch_error_is_redacted_and_never_execs_validator(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _assert_setup_failure_is_redacted(
        monkeypatch,
        capsys,
        lambda: OSError("launch-exception-hostile-marker"),
    )


def test_setup_keyboard_interrupt_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exec_called = False

    def interrupt(_command: list[str], **_kwargs: object) -> None:
        raise KeyboardInterrupt

    def fake_execv(_path: str, _argv: list[str]) -> None:
        nonlocal exec_called
        exec_called = True

    monkeypatch.setattr(validator_entrypoint.subprocess, "run", interrupt)
    monkeypatch.setattr(validator_entrypoint.os, "execv", fake_execv)

    with pytest.raises(KeyboardInterrupt):
        validator_entrypoint.main()

    assert exec_called is False


def test_setup_system_exit_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exec_called = False

    def exit_setup(_command: list[str], **_kwargs: object) -> None:
        raise SystemExit(23)

    def fake_execv(_path: str, _argv: list[str]) -> None:
        nonlocal exec_called
        exec_called = True

    monkeypatch.setattr(validator_entrypoint.subprocess, "run", exit_setup)
    monkeypatch.setattr(validator_entrypoint.os, "execv", fake_execv)

    with pytest.raises(SystemExit) as raised:
        validator_entrypoint.main()

    assert raised.value.code == 23
    assert exec_called is False
