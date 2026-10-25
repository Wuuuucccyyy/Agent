"""Versioned contracts shared by profiling agents, retrieval and execution."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal["pca", "regression", "clustering", "manova", "discriminant", "unknown"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: str = "0.1.0"


class Evidence(Contract):
    origin: Literal["computed", "official_document", "user", "rule_inference", "llm_inference", "unknown"]
    source: str
    method: str
    status: Literal["verified", "unverified", "unknown"]
    note: str = ""


class TaskProfile(Contract):
    research_goal: str = Field(min_length=1)
    task_type: TaskType = "unknown"
    target_variables: list[str] = Field(default_factory=list)
    predictor_variables: list[str] = Field(default_factory=list)
    group_variables: list[str] = Field(default_factory=list)
    expected_output: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)


class SourceProfile(Contract):
    file_name: str
    sha256: str
    format: Literal["csv", "xlsx"]
    extraction_method: str
    sheet: str | int | None = None
    uncertainties: list[str] = Field(default_factory=list)


class StructureProfile(Contract):
    n: int = Field(ge=1)
    p: int = Field(ge=1)
    p_over_n: float
    duplicate_rows: int
    candidate_keys: list[str]
    layout: str = "unknown"
    time_order: str = "unknown"
    repeated_measures: str = "unknown"


class VariableProfile(Contract):
    name: str
    dtype: str
    kind: Literal["numeric", "categorical", "boolean", "datetime"]
    measurement_scale: str = "unknown"
    n_unique: int
    missing_count: int
    missing_rate: float = Field(ge=0, le=1)
    nonfinite_count: int = 0
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    variance: float | None = None
    skewness: float | None = None
    excess_kurtosis: float | None = None
    quantiles: dict[str, float] = Field(default_factory=dict)
    zero_fraction: float | None = None
    evidence: Evidence


class QualityProfile(Contract):
    schema_version: str = "0.2.0"
    missing_cells: int
    missing_rate: float
    missing_patterns: dict[str, int]
    iqr_outlier_counts: dict[str, int]
    constant_columns: list[str]
    all_missing_columns: list[str]
    warnings: list[str]


class RelationsProfile(Contract):
    schema_version: str = "0.2.0"
    columns: list[str]
    complete_rows: int
    analysis_columns: list[str] = Field(default_factory=list)
    analysis_complete_rows: int | None = None
    analysis_predictor_rank: int | None = None
    correlation: dict[str, dict[str, float | None]]
    covariance: dict[str, dict[str, float | None]]
    centered_rank: int | None
    effective_dimension_95: int | None
    condition_number: float | None
    singular: bool | None
    group_sizes: dict[str, dict[str, int]]
    method: str = "Complete-case numeric subset; sample covariance; centered SVD"


class DesignProfile(Contract):
    independence: str = "unknown"
    pairing: str = "unknown"
    sampling: str = "unknown"
    repeated_measures: str = "unknown"
    goal: str
    response_types: dict[str, str]


class DataProfile(Contract):
    schema_version: str = "0.2.0"
    source: SourceProfile
    structure: StructureProfile
    variables: list[VariableProfile]
    quality: QualityProfile
    relations: RelationsProfile
    design: DesignProfile
    evidence: dict[str, Evidence]
    unknowns: list[str]


class KnowledgeProfile(Contract):
    id: str
    package: str
    function_name: str
    task_types: list[TaskType]
    summary: str
    input_types: list[str]
    input_constraints: list[str]
    output_types: list[str]
    assumptions: list[str]
    missing_data_handling: str
    failure_conditions: list[str]
    alternatives: list[str]
    source_url: str
    package_version: str
    verification_status: Literal["official_docs_reviewed", "unverified"]
    retrieved_on: str
    evidence: dict[str, Evidence]


class Penalty(Contract):
    name: str
    severity: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)
    reason: str


class Candidate(Contract):
    knowledge_id: str
    cosine: float
    hard_failures: list[str]
    penalties: list[Penalty]
    unknowns: list[str]
    penalty_total: float
    score: float
    source_url: str


class RetrievalResult(Contract):
    status: Literal["ranked", "no_compatible_method", "needs_clarification"]
    encoder: str
    mode: Literal["A", "B", "C"]
    alpha: float
    penalty_lambda: float
    ranked: list[Candidate]
    excluded: list[Candidate]


class ExecutionResult(Contract):
    schema_version: str = "0.2.0"
    status: Literal["success", "blocked", "not_implemented", "skipped"]
    method: str | None = None
    backend: str = "python_trusted_templates"
    inputs: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    validation_passed: bool = False
    message: str = ""
