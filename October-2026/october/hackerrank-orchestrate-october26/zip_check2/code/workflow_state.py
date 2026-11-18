"""
workflow_state.py -- State Schema and Data Contracts for LangGraph Workflow
Milestone 6: Shared state schema, audit challenges, manager decisions,
and state transformation utilities.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from policy_engine import AuditStep, ResourceEvaluation


@dataclass
class AuditChallenge:
    """Represents a specific deficiency or concern flagged by the Audit Agent."""
    target_agent: str       # 'evidence' | 'policy' | 'identity'
    resource_id: str
    system_id: str
    issue: str
    required_action: str
    severity: str = "CRITICAL"  # 'CRITICAL' | 'WARNING'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuditChallenge:
        return cls(**data)


@dataclass
class ManagerDecision:
    """Reasoned judgment emitted by the Manager Agent."""
    action: str             # 'ROUTE_TO_EVIDENCE' | 'ROUTE_TO_POLICY' | 'EXPAND_IDENTITY' | 'FINALIZE' | 'SHORT_CIRCUIT_NOT_APPLICABLE'
    target_agent: str       # 'evidence' | 'policy' | 'identity' | 'output'
    reasoning: str
    targeted_directive: Dict[str, Any] = field(default_factory=dict)
    is_llm_judgment: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ManagerDecision:
        return cls(**data)


class AuditWorkflowState(TypedDict, total=False):
    """
    Shared LangGraph state schema for auditing a deletion request.
    Preserves evidence provenance, uncertainty, audit challenges, and decision logs.
    """
    # Request metadata
    case_id: str
    request_email: str
    request_text: str
    requested_at: str       # ISO string
    reported_status: str
    reported_at: str        # ISO string
    audit_at: str           # ISO string

    # Intent
    intent_is_deletion: Optional[bool]
    intent_confidence: float
    intent_method: str

    # Identity
    user_id: Optional[str]
    identifiers: List[str]  # Normalized lowercase identifiers

    # Evidence and Resource State
    evidence_hits: List[Dict[str, Any]]
    evaluations: List[Dict[str, Any]]  # Serialized ResourceEvaluation dicts
    evidence_gaps: List[str]
    unresolved_conflicts: List[str]

    # Audit and Control Loop
    audit_challenges: List[Dict[str, Any]]
    audit_passed: bool
    iteration_count: int
    max_iterations: int
    manager_decision: Optional[Dict[str, Any]]
    next_node: str

    # Final Output
    deletion_status: str   # 'COMPLETE' | 'INCOMPLETE' | 'NOT_APPLICABLE'
    steps: List[Dict[str, Any]]  # Serialized AuditStep dicts
    steps_json: str

    # Observability and Token Metrics
    gemini_prompt_tokens: int
    gemini_completion_tokens: int
    gemini_call_count: int
    error_trace: List[str]


def eval_to_dict(ev: ResourceEvaluation) -> Dict[str, Any]:
    """Serializes a ResourceEvaluation object to a dictionary."""
    return {
        "resource_id": ev.resource_id,
        "system_id": ev.system_id,
        "data_category": ev.data_category,
        "applicable_rule_id": ev.applicable_rule_id,
        "required_action": ev.required_action,
        "observed_state": ev.observed_state,
        "evidence_id": ev.evidence_id,
        "is_compliant": ev.is_compliant,
        "uncertainty_note": ev.uncertainty_note,
        "conflict_details": list(ev.conflict_details),
    }


def eval_from_dict(d: Dict[str, Any]) -> ResourceEvaluation:
    """Deserializes a dictionary into a ResourceEvaluation object."""
    return ResourceEvaluation(
        resource_id=d.get("resource_id", ""),
        system_id=d.get("system_id", ""),
        data_category=d.get("data_category", ""),
        applicable_rule_id=d.get("applicable_rule_id", ""),
        required_action=d.get("required_action", "DELETE"),
        observed_state=d.get("observed_state", "UNKNOWN"),
        evidence_id=d.get("evidence_id", ""),
        is_compliant=d.get("is_compliant"),
        uncertainty_note=d.get("uncertainty_note", ""),
        conflict_details=list(d.get("conflict_details", [])),
    )


def step_to_dict(step: AuditStep) -> Dict[str, Any]:
    """Serializes an AuditStep object to a dictionary."""
    return {
        "step_no": step.step_no,
        "phase": step.phase,
        "system_id": step.system_id,
        "resource_id": step.resource_id,
        "operation": step.operation,
        "state": step.state,
        "evidence_id": step.evidence_id,
    }


def step_from_dict(d: Dict[str, Any]) -> AuditStep:
    """Deserializes a dictionary into an AuditStep object."""
    return AuditStep(
        step_no=int(d.get("step_no", 0)),
        phase=d.get("phase", ""),
        system_id=d.get("system_id", ""),
        resource_id=d.get("resource_id", ""),
        operation=d.get("operation", ""),
        state=d.get("state", ""),
        evidence_id=d.get("evidence_id", ""),
    )


def create_initial_state(
    case_id: str,
    request_email: str,
    request_text: str,
    requested_at: datetime,
    reported_status: str,
    reported_at: datetime,
    audit_at: datetime,
    max_iterations: int = 2,
) -> AuditWorkflowState:
    """Initializes a blank, well-formed AuditWorkflowState for a given case."""
    return {
        "case_id": case_id,
        "request_email": request_email.strip(),
        "request_text": request_text.strip(),
        "requested_at": requested_at.isoformat(),
        "reported_status": reported_status.strip().upper(),
        "reported_at": reported_at.isoformat(),
        "audit_at": audit_at.isoformat(),

        "intent_is_deletion": None,
        "intent_confidence": 0.0,
        "intent_method": "",

        "user_id": None,
        "identifiers": [request_email.strip().lower()],

        "evidence_hits": [],
        "evaluations": [],
        "evidence_gaps": [],
        "unresolved_conflicts": [],

        "audit_challenges": [],
        "audit_passed": False,
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "manager_decision": None,
        "next_node": "manager_node",

        "deletion_status": "INCOMPLETE",
        "steps": [],
        "steps_json": "[]",

        "gemini_prompt_tokens": 0,
        "gemini_completion_tokens": 0,
        "gemini_call_count": 0,
        "error_trace": [],
    }
