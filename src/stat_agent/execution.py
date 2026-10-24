"""Audited PCA/OLS templates only. This is not a generated-code sandbox."""
import numpy as np
import pandas as pd

from .profiling import selected_features
from .schemas import ExecutionResult, RetrievalResult, TaskProfile


def execute(frame: pd.DataFrame, task: TaskProfile, ranking: RetrievalResult) -> ExecutionResult:
    if ranking.status != "ranked" or not ranking.ranked:
        return ExecutionResult(status="blocked", message="No compatible recommendation; resolve task or data constraints.")
    chosen = ranking.ranked[0]
    if chosen.hard_failures:
        return ExecutionResult(status="blocked", method=chosen.knowledge_id, message="Hard constraints block execution, including in ablation A.")
    method = chosen.knowledge_id
    if method not in {"stats::prcomp", "stats::lm"}:
        return ExecutionResult(status="not_implemented", method=method, message="v0.1 profiles and ranks this method; execution adapter is pending.")
    cols = selected_features(frame, task)
    if method == "stats::lm" and len(task.target_variables) != 1:
        return ExecutionResult(status="blocked", method=method, message="The OLS demo needs exactly one explicit numeric target.")
    used = cols + (task.target_variables if method == "stats::lm" else [])
    if not used or not np.isfinite(frame[used].to_numpy(dtype=float)).all():
        return ExecutionResult(status="blocked", method=method, inputs=used, message="Finite complete inputs are required; no rows are silently dropped or imputed.")
    x = frame[cols].to_numpy(dtype=float)
    n, p = x.shape
    if n < 2 or p == 0:
        return ExecutionResult(status="blocked", method=method, message="Insufficient observations or features.")
    if method == "stats::prcomp":
        scale = x.std(axis=0, ddof=1)
        if np.any(scale == 0):
            return ExecutionResult(status="blocked", method=method, inputs=used,
                message="This standardized PCA template requires nonconstant features; choose a preprocessing policy.")
        standardized = (x - x.mean(axis=0)) / scale
        u, singular, vt = np.linalg.svd(standardized, full_matrices=False)
        variance = singular ** 2 / (n - 1)
        ratio = variance / variance.sum()
        scores = u * singular
        reconstruction_error = float(np.max(np.abs(scores @ vt - standardized)))
        valid = bool(np.isclose(ratio.sum(), 1) and reconstruction_error < 1e-8)
        return ExecutionResult(status="success" if valid else "blocked", method=method, inputs=used,
            metrics={"explained_variance": variance.tolist(), "explained_variance_ratio": ratio.tolist(),
                     "loadings": vt.T.tolist(), "scores": scores.tolist(),
                     "components_for_95_percent": int(np.searchsorted(np.cumsum(ratio), .95) + 1)},
            diagnostics={"n": n, "p": p, "center": x.mean(axis=0).tolist(), "scale_ddof1": scale.tolist(),
                         "reconstruction_max_abs_error": reconstruction_error},
            limitations=["Python SVD equivalent to centered, scaled PCA; no R runtime was invoked.",
                         "Exploratory summary only; study design and feature meaning are not verified."],
            validation_passed=valid, message="PCA reconstruction and variance accounting checked.")
    y = frame[task.target_variables[0]].to_numpy(dtype=float)
    design = np.column_stack([np.ones(n), x])
    rank = int(np.linalg.matrix_rank(design))
    if rank < p + 1 or n <= p + 1:
        return ExecutionResult(status="blocked", method=method, inputs=used,
            message="OLS template requires a full-rank design and positive residual degrees of freedom.")
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ coefficients
    residuals = y - predicted
    sse = float(residuals @ residuals)
    tss = float(np.sum((y - y.mean()) ** 2))
    normal_error = float(np.max(np.abs(design.T @ residuals)))
    tolerance = 1e-8 * max(1.0, float(np.linalg.norm(design) * np.linalg.norm(y)))
    valid = bool(np.isfinite(coefficients).all() and normal_error <= tolerance)
    return ExecutionResult(status="success" if valid else "blocked", method=method, inputs=used,
        metrics={"coefficients": dict(zip(["intercept"] + cols, coefficients.tolist())),
                 "r_squared": 1 - sse / tss if tss > 0 else None, "sse": sse,
                 "predictions": predicted.tolist(), "residuals": residuals.tolist()},
        diagnostics={"n": n, "design_rank": rank, "residual_df": n - rank,
                     "normal_equation_max_abs_error": normal_error, "normal_equation_tolerance": tolerance,
                     "residual_mean": float(residuals.mean())},
        limitations=["In-sample fit only, not predictive validation.",
                     "No p-values or causal claims: independence, heteroscedasticity and residual assumptions remain unchecked.",
                     "Python least squares template; R lm was not executed."],
        validation_passed=valid, message="OLS finite coefficients and least-squares orthogonality checked.")
