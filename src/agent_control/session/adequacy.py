"""Load and evaluate adequacy profiles (Slice T04)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_shared.models.adequacy import (
    AdequacyCheckResult,
    AdequacyCheckSpec,
    AdequacyEvaluation,
    AdequacyProfile,
    AdequacyStatus,
    VerificationOutcomeLabel,
)

_DEFAULT_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[3] / "config" / "adequacy_profiles.yaml",
    Path("/opt/ai-sdlc-lab/agent-control-plane/config/adequacy_profiles.yaml"),
    Path("/app/config/adequacy_profiles.yaml"),
    Path.cwd() / "config" / "adequacy_profiles.yaml",
)


def _default_config_path() -> Path:
    for candidate in _DEFAULT_CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _DEFAULT_CONFIG_CANDIDATES[0]


_DEFAULT_CONFIG = _default_config_path()


def _parse_check(raw: Any) -> AdequacyCheckSpec:
    if isinstance(raw, str):
        return AdequacyCheckSpec(id=raw, kind="other", description=raw)
    if isinstance(raw, dict):
        return AdequacyCheckSpec.model_validate(raw)
    raise TypeError(f"invalid check spec: {raw!r}")


def load_adequacy_profiles(path: Path | None = None) -> dict[str, AdequacyProfile]:
    cfg_path = path or _default_config_path()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    profiles_raw = data.get("profiles") or {}
    out: dict[str, AdequacyProfile] = {}
    for pid, body in profiles_raw.items():
        body = dict(body or {})
        required = [_parse_check(c) for c in body.pop("required_checks", []) or []]
        optional = [_parse_check(c) for c in body.pop("optional_checks", []) or []]
        out[pid] = AdequacyProfile(
            profile_id=pid,
            required_checks=required,
            optional_checks=optional,
            **{
                k: v
                for k, v in body.items()
                if k
                in (
                    "description",
                    "applies_to_commands",
                    "agent_authored_tests",
                    "fixed_verified_allowed",
                    "default_limitations",
                    "require_agent_test_limitation_when_unknown",
                )
            },
        )
    return out


def default_profile_id_for_command(
    command_kind: str, path: Path | None = None
) -> str:
    cfg_path = path or _default_config_path()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    mapping = data.get("default_by_command") or {}
    return str(mapping.get(command_kind) or "risk1_hypothesis")


@lru_cache(maxsize=4)
def _cached_profiles(path_str: str) -> dict[str, AdequacyProfile]:
    return load_adequacy_profiles(Path(path_str) if path_str else _DEFAULT_CONFIG)


def get_profile(
    profile_id: str, *, config_path: Path | None = None
) -> AdequacyProfile:
    path = config_path or _default_config_path()
    profiles = _cached_profiles(str(path.resolve()))
    if profile_id not in profiles:
        raise KeyError(f"unknown adequacy profile: {profile_id}")
    return profiles[profile_id]


def profile_for_command(
    command_kind: str, *, config_path: Path | None = None
) -> AdequacyProfile:
    path = config_path or _default_config_path()
    pid = default_profile_id_for_command(command_kind, path)
    return get_profile(pid, config_path=path)


def evaluate_adequacy(
    profile: AdequacyProfile,
    *,
    verification_status: str,
    workflows_observed: list[str] | None = None,
    agent_test_paths: list[str] | None = None,
    agent_tests_exercised: bool | None = None,
) -> AdequacyEvaluation:
    """Evaluate profile against machine evidence.

    ``agent_tests_exercised``:
      - True: CI/local evidence shows agent-authored tests ran
      - False: known not run
      - None: unknown (default for CT102 aggregate-only path)
    """
    workflows_observed = workflows_observed or []
    agent_test_paths = agent_test_paths or []
    checks: list[AdequacyCheckResult] = []
    limitations: list[str] = []
    if profile.default_limitations.strip():
        limitations.append(profile.default_limitations.strip())

    if verification_status == "missing":
        outcome: VerificationOutcomeLabel = "verification_missing"
        status: AdequacyStatus = "not_applicable"
        return AdequacyEvaluation(
            profile_id=profile.profile_id,
            status=status,
            outcome_label=outcome,
            checks=checks,
            limitations=limitations
            or ["No CT102/ACI verification claim for this command."],
            fixed_verified=False,
        )

    if verification_status == "failed":
        for spec in profile.required_checks:
            checks.append(
                AdequacyCheckResult(
                    id=spec.id,
                    kind=spec.kind,
                    status="failed",
                    evidence="verification_status=failed",
                )
            )
        return AdequacyEvaluation(
            profile_id=profile.profile_id,
            status="failed",
            outcome_label="verification_failed",
            checks=checks,
            limitations=limitations + ["Required verification failed."],
            fixed_verified=False,
        )

    # passed / requested path
    required_ok = True
    for spec in profile.required_checks:
        if spec.kind == "ci_workflow":
            if verification_status == "passed":
                checks.append(
                    AdequacyCheckResult(
                        id=spec.id,
                        kind=spec.kind,
                        status="passed",
                        evidence=(
                            "ct102_aggregate_verified"
                            if not workflows_observed
                            else ",".join(workflows_observed[:8])
                        ),
                    )
                )
            elif verification_status == "requested":
                checks.append(
                    AdequacyCheckResult(
                        id=spec.id,
                        kind=spec.kind,
                        status="pending",
                        evidence="ci_pending",
                    )
                )
                required_ok = False
            else:
                checks.append(
                    AdequacyCheckResult(
                        id=spec.id,
                        kind=spec.kind,
                        status="incomplete",
                        evidence=f"unexpected_status={verification_status}",
                    )
                )
                required_ok = False
        else:
            checks.append(
                AdequacyCheckResult(
                    id=spec.id,
                    kind=spec.kind,
                    status="incomplete",
                    notes="no evaluator for this check kind yet",
                )
            )
            required_ok = False

    # Agent-authored tests dimension (scoped claims)
    if profile.agent_authored_tests == "not_applicable":
        pass
    elif profile.agent_authored_tests == "scoped_only":
        if agent_tests_exercised is True:
            checks.append(
                AdequacyCheckResult(
                    id="agent_authored_unit_tests",
                    kind="agent_authored_tests",
                    status="passed",
                    evidence=",".join(agent_test_paths[:12]) or "exercised",
                )
            )
        elif agent_tests_exercised is False:
            checks.append(
                AdequacyCheckResult(
                    id="agent_authored_unit_tests",
                    kind="agent_authored_tests",
                    status="incomplete",
                    evidence=",".join(agent_test_paths[:12]) or "not_run",
                    notes="Agent-authored tests present but not shown as exercised by CI.",
                )
            )
            if profile.require_agent_test_limitation_when_unknown or agent_test_paths:
                limitations.append(
                    "Agent-authored tests are scoped claims only; CI aggregate does not "
                    "prove those tests ran unless listed in required workflows."
                )
        else:
            # unknown — CT102 aggregate path
            checks.append(
                AdequacyCheckResult(
                    id="agent_authored_unit_tests",
                    kind="agent_authored_tests",
                    status="incomplete",
                    evidence="unknown",
                    notes="CT102 aggregate does not enumerate agent-authored test execution.",
                )
            )
            if profile.require_agent_test_limitation_when_unknown:
                limitations.append(
                    "Agent-authored tests (if any) are not independently attested; "
                    "verification is scoped to CT102 required workflows on this commit only."
                )

    incomplete = any(c.status == "incomplete" for c in checks)
    pending = any(c.status == "pending" for c in checks)

    if verification_status == "requested" or pending:
        eval_status: AdequacyStatus = "pending"
        outcome = "verification_missing"  # not yet verified
        # keep pending label via outcome for requested CI
        if verification_status == "requested":
            outcome = "verification_missing"
        fixed = False
    elif not required_ok or verification_status != "passed":
        eval_status = "incomplete"
        outcome = "ci_regression_passed" if verification_status == "passed" else "verification_failed"
        fixed = False
    elif incomplete:
        eval_status = "incomplete"
        # CI required checks passed but adequacy incomplete → scoped label
        outcome = "ci_regression_passed"
        fixed = False
    else:
        eval_status = "passed"
        if profile.fixed_verified_allowed:
            outcome = "fixed_verified"
            fixed = True
        else:
            outcome = "ci_regression_passed"
            fixed = False

    # Dedupe limitations
    seen: set[str] = set()
    lims: list[str] = []
    for item in limitations:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            lims.append(key)

    return AdequacyEvaluation(
        profile_id=profile.profile_id,
        status=eval_status,
        outcome_label=outcome,
        checks=checks,
        limitations=lims,
        fixed_verified=fixed,
    )


def clear_profile_cache() -> None:
    _cached_profiles.cache_clear()
