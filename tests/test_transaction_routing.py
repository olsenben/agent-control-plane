"""Deterministic REQUIRED vs OPTIONAL routing."""

from __future__ import annotations

from agent_control.transaction.evidence.route import (
    CHANGE_DEPENDENCY,
    CHANGE_PRODUCTION,
    CHANGE_PUBLIC_API,
    CHANGE_SECURITY_FINDING,
    OPTIONAL,
    REQUIRED,
    build_route,
    classify_change_classes,
    routed_providers,
)


def test_production_source_routes_p1_required() -> None:
    classes = classify_change_classes(changed_files=["src/pkg/core.py"])
    assert CHANGE_PRODUCTION in classes
    route = build_route(classes, route_id="t")
    providers = {item.provider_id: item.requirement_class for item in routed_providers(route)}
    assert providers["P1"] == REQUIRED


def test_security_finding_routes_p2_p3_required() -> None:
    classes = classify_change_classes(
        changed_files=["src/pkg/core.py"],
        task_type="SECURITY_REMEDIATION",
        security_finding_ids=["f1"],
    )
    assert CHANGE_SECURITY_FINDING in classes
    route = build_route(classes)
    providers = {item.provider_id: item.requirement_class for item in routed_providers(route)}
    assert providers["P2"] == REQUIRED
    assert providers["P3"] == REQUIRED


def test_dependency_optional() -> None:
    classes = classify_change_classes(changed_files=["requirements.txt"])
    assert CHANGE_DEPENDENCY in classes
    route = build_route(classes)
    providers = {item.provider_id: item.requirement_class for item in routed_providers(route)}
    assert providers["dependency_if_configured"] == OPTIONAL


def test_public_api_routes_p4_required() -> None:
    classes = classify_change_classes(
        changed_files=["src/pkg/api.py"],
        task_type="PUBLIC_API",
        units=[{"receipts": ["PUBLIC_API_CHANGE"]}],
    )
    assert CHANGE_PUBLIC_API in classes
    route = build_route(classes)
    providers = {item.provider_id: item.requirement_class for item in routed_providers(route)}
    assert providers["P4"] == REQUIRED


def test_route_is_deterministic_and_not_llm() -> None:
    a = build_route(["PRODUCTION_SOURCE_CHANGE"], route_id="default_deterministic_v1")
    b = build_route(["PRODUCTION_SOURCE_CHANGE"], route_id="default_deterministic_v1")
    assert a.model_dump() == b.model_dump()
    assert a.llm_router is False
    assert a.fail_closed is True
