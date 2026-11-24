"""Shared constants for BPIC 2017 Process Mining project.

Centralizes standard XES column names, activity names, lifecycles,
and integration contract keys agreed upon by the project team.
"""

from __future__ import annotations

# Standard XES Attribute / Column Names
COL_CASE_ID: str = "case:concept:name"
COL_ACTIVITY: str = "concept:name"
COL_TIMESTAMP: str = "time:timestamp"
COL_LIFECYCLE: str = "lifecycle:transition"
COL_RESOURCE: str = "org:resource"

# Aliases for backward compatibility
CASE_COLUMN: str = COL_CASE_ID
ACTIVITY_COLUMN: str = COL_ACTIVITY
TIMESTAMP_COLUMN: str = COL_TIMESTAMP
LIFECYCLE_COLUMN: str = COL_LIFECYCLE
RESOURCE_COLUMN: str = COL_RESOURCE

# Target Activity Names
ACT_ACCEPTED: str = "O_Accepted"
ACT_REFUSED: str = "O_Refused"
ACT_CANCELLED: str = "O_Cancelled"
ACT_FRAUD: str = "W_Assess potential fraud"

# Aliases for backward compatibility
ACCEPTED: str = ACT_ACCEPTED
REFUSED: str = ACT_REFUSED
CANCELLED: str = ACT_CANCELLED
FRAUD_ACTIVITY: str = ACT_FRAUD

# Target Lifecycle Transitions
LIFECYCLE_COMPLETE: str = "complete"
LIFECYCLE_START: str = "start"
LIFECYCLE_SCHEDULE: str = "schedule"

# Tokens treated as missing or invalid resource identifiers
DEFAULT_MISSING_RESOURCE_TOKENS: frozenset[str] = frozenset(
    {"", "none", "null", "nan", "unknown", "<na>"}
)

# Mandatory keys in standardized return contract
CONTRACT_KEYS: tuple[str, ...] = (
    "metadata",
    "summary",
    "case_ids",
    "evidence",
    "per_case",
)
