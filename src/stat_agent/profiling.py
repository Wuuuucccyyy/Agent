"""Deterministic numeric facts; no hypothesis assumptions are inferred from marginals."""
import json
import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from .schemas import (
    DataProfile, DesignProfile, Evidence, QualityProfile, RelationsProfile,
    SourceProfile, StructureProfile, TaskProfile, VariableProfile,
)


def finite(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def computed(source: SourceProfile, method: str) -> Evidence:
    return Evidence(origin="computed", source=f"sha256:{source.sha256}", method=method, status="verified")


def describe_variables(frame: pd.DataFrame, source: SourceProfile) -> list[VariableProfile]:
    result = []
    for name in frame:
        col = frame[name]
        kind = ("boolean" if is_bool_dtype(col) else "datetime" if is_datetime64_any_dtype(col)
                else "numeric" if is_numeric_dtype(col) else "categorical")
        fields = {}
        if kind == "numeric":
            valid = col.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
            fields = dict(
                nonfinite_count=int((col.notna() & ~np.isfinite(col)).sum()),
                minimum=finite(valid.min()), maximum=finite(valid.max()), mean=finite(valid.mean()),
                variance=finite(valid.var(ddof=1)), skewness=finite(valid.skew()),
                excess_kurtosis=finite(valid.kurt()),
                quantiles={str(q): float(valid.quantile(q)) for q in [0.25, 0.5, 0.75]} if len(valid) else {},
                zero_fraction=float((valid == 0).mean()) if len(valid) else None,
            )
        result.append(VariableProfile(
            name=name, dtype=str(col.dtype), kind=kind, n_unique=int(col.nunique()),
            missing_count=int(col.isna().sum()), missing_rate=float(col.isna().mean()),
            evidence=computed(source, "pandas; finite observations; sample variance ddof=1; adjusted skew/kurtosis"),
            **fields,
        ))
    return result


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [name for name in frame if is_numeric_dtype(frame[name]) and not is_bool_dtype(frame[name])]


def selected_features(frame: pd.DataFrame, task: TaskProfile) -> list[str]:
    excluded = set(task.target_variables + task.group_variables)
    return task.predictor_variables or [c for c in numeric_columns(frame) if c not in excluded]


def describe_relations(frame: pd.DataFrame, task: TaskProfile) -> RelationsProfile:
    numeric = set(numeric_columns(frame))
    features = selected_features(frame, task)
    cols = [c for c in features if c in numeric]
    clean = frame[cols].replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    analysis_columns = list(dict.fromkeys(features + task.target_variables + task.group_variables))
    analysis_mask = frame[analysis_columns].notna().all(axis=1)
    for c in analysis_columns:
        if c in numeric:
            analysis_mask &= np.isfinite(frame[c])
    n, p = clean.shape
    rank = dimension = condition = singular = None
    corr, cov = {}, {}
    if n >= 2 and p:
        def matrix_dict(matrix):
            return {str(c): {str(r): finite(v) for r, v in values.items()} for c, values in matrix.to_dict().items()}
        corr = matrix_dict(clean.corr())
        cov = matrix_dict(clean.cov(ddof=1))
        centered = clean.to_numpy() - clean.to_numpy().mean(axis=0)
        sv = np.linalg.svd(centered, compute_uv=False)
        rank = rank_from_singular_values(sv, centered.shape)
        singular = rank < p
        condition = None if singular else finite(sv[0] / sv[-1])
        energy = (sv / sv[0]) ** 2 if sv[0] else sv ** 2
        dimension = int(np.searchsorted(np.cumsum(energy) / energy.sum(), 0.95) + 1) if energy.sum() else 0
    analysis_n = int(analysis_mask.sum())
    analysis_rank = None
    if analysis_n >= 2 and p:
        if analysis_n == n:
            analysis_rank = rank
        else:
            analysis_x = frame.loc[analysis_mask, cols].to_numpy(dtype=float)
            centered = analysis_x - analysis_x.mean(axis=0)
            analysis_rank = rank_from_singular_values(np.linalg.svd(centered, compute_uv=False), centered.shape)
    group_sizes = {c: {str(k): int(v) for k, v in frame[c].value_counts(dropna=False).items()}
                   for c in task.group_variables}
    return RelationsProfile(columns=cols, complete_rows=n, correlation=corr, covariance=cov,
                            analysis_columns=analysis_columns, analysis_complete_rows=analysis_n,
                            analysis_predictor_rank=analysis_rank,
                            centered_rank=rank, effective_dimension_95=dimension,
                            condition_number=condition, singular=singular, group_sizes=group_sizes)


def rank_from_singular_values(values: np.ndarray, shape: tuple[int, int]) -> int:
    """Same default relative tolerance as matrix_rank, reusing the existing SVD."""
    tolerance = values[0] * max(shape) * np.finfo(values.dtype).eps
    return int(np.count_nonzero(values > tolerance))


def missing_pattern_counts(missing: pd.DataFrame) -> dict[str, int]:
    """Count packed masks once per distinct pattern; JSON keys cannot alias column names."""
    packed = np.packbits(missing.to_numpy(dtype=bool), axis=1)
    patterns, counts = np.unique(packed, axis=0, return_counts=True)
    masks = np.unpackbits(patterns, axis=1, count=len(missing.columns)).astype(bool)
    return {json.dumps(missing.columns[mask].tolist(), ensure_ascii=False): int(count)
            for mask, count in zip(masks, counts)}


def build_profile(frame: pd.DataFrame, source: SourceProfile, task: TaskProfile,
                  variables: list[VariableProfile], relations: RelationsProfile) -> DataProfile:
    from .applicability_facts import describe_applicability
    missing = frame.isna()
    patterns = missing_pattern_counts(missing)
    outliers = {}
    for c in numeric_columns(frame):
        col = frame[c].replace([np.inf, -np.inf], np.nan)
        q1, q3 = col.quantile([0.25, 0.75])
        outliers[c] = int(((col < q1 - 1.5 * (q3 - q1)) | (col > q3 + 1.5 * (q3 - q1))).sum())
    warnings = ["IQR flags are descriptive; they do not justify removing observations.",
                "Numeric dtype does not distinguish identifiers, ordinal codes and continuous measurements.",
                "Marginal distributions do not verify regression residual assumptions."]
    if relations.complete_rows < len(frame):
        warnings.append("Relations use complete finite rows only; execution does not automatically drop missing rows.")
    return DataProfile(
        source=source,
        structure=StructureProfile(n=len(frame), p=len(frame.columns), p_over_n=len(frame.columns) / len(frame),
            duplicate_rows=int(frame.duplicated().sum()),
            candidate_keys=[c for c in frame if frame[c].notna().all() and frame[c].is_unique]),
        variables=variables,
        quality=QualityProfile(missing_cells=int(missing.to_numpy().sum()), missing_rate=float(missing.to_numpy().mean()),
            missing_patterns=patterns, iqr_outlier_counts=outliers,
            constant_columns=[v.name for v in variables if v.n_unique == 1],
            all_missing_columns=[v.name for v in variables if v.missing_count == len(frame)], warnings=warnings),
        relations=relations,
        applicability=describe_applicability(frame, task, selected_features(frame, task)),
        design=DesignProfile(goal=task.task_type, response_types={v.name: v.kind for v in variables if v.name in task.target_variables}),
        evidence={
            "source": computed(source, "SHA256 and local reader metadata"),
            "structure": computed(source, "shape, duplicated, nunique; key candidates are uniqueness only"),
            "quality": computed(source, "missing masks and Tukey 1.5 IQR descriptive flags"),
            "relations": computed(source, relations.method),
            "applicability": computed(source, "Selected finite observations, group counts/centered ranks and bounded missing-pattern overlap; no preprocessing"),
            "design": Evidence(origin="unknown", source="study protocol not supplied", method="not inferred", status="unknown"),
        },
        unknowns=["measurement_scales", "independence", "pairing", "sampling", "repeated_measures", "missingness_mechanism"],
    )
