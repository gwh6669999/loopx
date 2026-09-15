"""The managed executor readback names the executor and whether it can launch."""

from __future__ import annotations

import pytest

from loopx.control_plane.turn_driver.host_binding import (
    DSH_RUNTIME_UNAVAILABLE,
    EXECUTOR_KIND_GENERIC,
    EXECUTOR_KIND_INDIVIDUAL,
    EXECUTOR_KIND_MANAGED,
    INDIVIDUAL_DEFAULT_TURN_HOST,
    MANAGED_EXECUTOR_BINDING_SCHEMA_VERSION,
    MANAGED_TURN_HOST,
    OPERATOR_CREDENTIAL_UNCONFIGURED,
    managed_executor_binding,
    resolve_default_turn_host,
)

_NO_RUNTIME = lambda _module: False  # noqa: E731 - tiny probe fixture
_RUNTIME = lambda _module: True  # noqa: E731 - tiny probe fixture


def test_managed_executor_reports_the_operator_credential_and_endpoint():
    binding = managed_executor_binding(
        "dsh",
        environ={
            "DEEPSEEK_API_KEY": "sk-operator",
            "DEEPSEEK_BASE_URL": "https://example.invalid",
        },
        module_probe=_RUNTIME,
    )

    assert binding == {
        "schema_version": MANAGED_EXECUTOR_BINDING_SCHEMA_VERSION,
        "executor": "dsh",
        "executor_kind": EXECUTOR_KIND_MANAGED,
        "credential_env": "DEEPSEEK_API_KEY",
        "endpoint_env": "DEEPSEEK_BASE_URL",
        "operator_credential_bound": True,
        "available": True,
        "unavailable_reason": None,
    }


def test_managed_executor_fails_closed_when_the_runtime_is_missing():
    binding = managed_executor_binding(
        "dsh",
        environ={"DEEPSEEK_API_KEY": "sk-operator"},
        module_probe=_NO_RUNTIME,
    )

    assert binding["available"] is False
    assert binding["unavailable_reason"] == DSH_RUNTIME_UNAVAILABLE


def test_configured_runner_hook_makes_the_managed_host_launchable():
    binding = managed_executor_binding(
        "dsh",
        environ={"DEEPSEEK_API_KEY": "sk-operator"},
        dsh_runner_configured=True,
        module_probe=_NO_RUNTIME,
    )

    assert binding["available"] is True
    assert binding["unavailable_reason"] is None


def test_managed_executor_reports_an_unconfigured_credential_without_inventing_one():
    binding = managed_executor_binding(
        "dsh",
        environ={},
        dsh_runner_configured=True,
        module_probe=_RUNTIME,
    )

    assert binding["credential_env"] is None
    assert binding["endpoint_env"] is None


def test_managed_selection_without_the_operator_credential_fails_closed():
    """The managed host authenticates with the operator credential or not at all."""

    binding = managed_executor_binding("dsh", environ={}, module_probe=_RUNTIME)

    assert binding["executor_kind"] == EXECUTOR_KIND_MANAGED
    assert binding["operator_credential_bound"] is False
    assert binding["available"] is False
    assert binding["unavailable_reason"] == OPERATOR_CREDENTIAL_UNCONFIGURED


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_credential_counts_as_unconfigured(blank):
    binding = managed_executor_binding(
        "dsh", environ={"DEEPSEEK_API_KEY": blank}, module_probe=_RUNTIME
    )

    assert binding["credential_env"] is None
    assert binding["available"] is False
    assert binding["unavailable_reason"] == OPERATOR_CREDENTIAL_UNCONFIGURED


def test_configured_runner_hook_counts_as_an_operator_credential_boundary():
    binding = managed_executor_binding(
        "dsh",
        environ={},
        dsh_runner_configured=True,
        module_probe=_NO_RUNTIME,
    )

    assert binding["operator_credential_bound"] is True
    assert binding["available"] is True


def test_individual_and_generic_executors_are_not_operator_credential_bound():
    for host in ("codex-cli", "generic-cli"):
        binding = managed_executor_binding(host, environ={"DEEPSEEK_API_KEY": "sk-x"})

        assert binding["operator_credential_bound"] is False, binding


@pytest.mark.parametrize(
    ("host", "expected_kind"),
    [
        ("codex-cli", EXECUTOR_KIND_INDIVIDUAL),
        ("claude-code", EXECUTOR_KIND_INDIVIDUAL),
        ("generic-cli", EXECUTOR_KIND_GENERIC),
    ],
)
def test_other_hosts_make_no_launch_claim_and_carry_no_operator_env(
    host, expected_kind
):
    binding = managed_executor_binding(
        host,
        environ={"DEEPSEEK_API_KEY": "sk-operator"},
        module_probe=_RUNTIME,
    )

    assert binding["executor_kind"] == expected_kind
    assert binding["available"] is None
    assert binding["unavailable_reason"] is None
    assert binding["credential_env"] is None
    assert binding["endpoint_env"] is None
    assert binding["operator_credential_bound"] is False


@pytest.mark.parametrize(
    "environ, expected_host, expected_kind",
    [
        ({}, INDIVIDUAL_DEFAULT_TURN_HOST, EXECUTOR_KIND_INDIVIDUAL),
        (
            {"DEEPSEEK_API_KEY": "sk-operator"},
            MANAGED_TURN_HOST,
            EXECUTOR_KIND_MANAGED,
        ),
        ({"DEEPSEEK_API_KEY": "   "}, INDIVIDUAL_DEFAULT_TURN_HOST, EXECUTOR_KIND_INDIVIDUAL),
    ],
)
def test_default_resolution_reads_back_the_executor_it_selected(
    environ, expected_host, expected_kind
):
    default_host = resolve_default_turn_host(environ)
    binding = managed_executor_binding(
        default_host,
        environ=environ,
        module_probe=_RUNTIME,
    )

    # The default follows the operator credential, and the readback names the
    # executor that default resolved to. Whether a managed executor may run here
    # stays a separate, explicitly projected fact.
    assert default_host == expected_host
    assert binding["executor_kind"] == expected_kind
    if expected_kind == EXECUTOR_KIND_MANAGED:
        assert binding["available"] is True
        assert binding["unavailable_reason"] is None


def test_endpoint_without_credential_does_not_select_the_managed_default():
    environ = {"DEEPSEEK_BASE_URL": "https://example.invalid"}
    binding = managed_executor_binding("codex-cli", environ=environ)

    assert resolve_default_turn_host(environ) == INDIVIDUAL_DEFAULT_TURN_HOST
    assert binding["endpoint_env"] is None
