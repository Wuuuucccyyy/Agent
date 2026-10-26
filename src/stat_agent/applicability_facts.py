"""Bounded observations for method conditions; no imputation or deletion is authorized."""
import numpy as np
from pandas.api.types import is_numeric_dtype, is_bool_dtype

from .schemas import ApplicabilityProfile


def describe_applicability(frame, task, features):
    cols = list(features)
    result = ApplicabilityProfile(columns=cols, group_columns=list(task.group_variables), notes=[
        'Facts use selected columns and supplied group roles; no rows are deleted or imputed.',
        'Matrix symmetry uses atol=1e-10, rtol=1e-8; group rank uses NumPy SVD tolerance.',
        'Passing a necessary condition does not establish scientific or inferential applicability.'])
    if not cols:
        return result
    data = frame[cols]
    result.numeric_only = all(is_numeric_dtype(data[c]) and not is_bool_dtype(data[c]) for c in cols)
    result.numeric_or_boolean = all(is_numeric_dtype(data[c]) or is_bool_dtype(data[c]) for c in cols)
    result.missing_count = int(data.isna().to_numpy().sum())
    if not result.numeric_or_boolean:
        return result
    values = data.to_numpy(dtype=float, na_value=np.nan)
    result.nonfinite_count = int((~np.isfinite(values) & ~np.isnan(values)).sum())
    present = np.isfinite(values)
    if len(frame) >= 2 and not result.nonfinite_count:
        if present.all():
            result.pairwise_observed_overlap = True
        elif np.any(present.sum(axis=1) == 0):
            result.pairwise_observed_overlap = False
        else:
            patterns = np.unique(present, axis=0)
            if len(patterns) <= 512:
                masks = patterns.astype(np.int32)
                result.pairwise_observed_overlap = bool(np.all(masks @ masks.T > 0))
            else:
                result.notes.append('Pairwise overlap unavailable: more than 512 distinct observation masks.')
    result.square = values.shape[0] == values.shape[1]
    if np.isfinite(values).all():
        result.nonnegative = bool(np.all(values >= 0))
        result.correlation_bounds = bool(np.all(np.abs(values) <= 1+1e-10))
        if result.square:
            result.symmetric = bool(np.allclose(values, values.T, rtol=1e-8, atol=1e-10))
            result.diagonal_zero = bool(np.allclose(np.diag(values), 0, rtol=0, atol=1e-10))
            result.diagonal_one = bool(np.allclose(np.diag(values), 1, rtol=0, atol=1e-10))
    if len(task.group_variables) == 1:
        group = frame[task.group_variables[0]]
        result.group_missing_count = int(group.isna().sum())
        if not result.group_missing_count:
            sizes = group.value_counts()
            sizes = sizes[sizes > 0]
            result.group_count = len(sizes)
            result.minimum_group_size = int(sizes.min()) if len(sizes) else None
            if np.isfinite(values).all() and result.group_count:
                ranks, energy = [], np.zeros(len(cols))
                for label in sizes.index:
                    part = values[(group == label).to_numpy()]
                    centered = part-part.mean(axis=0)
                    ranks.append(int(np.linalg.matrix_rank(centered)) == len(cols))
                    energy += np.sum(centered**2, axis=0)
                result.within_group_full_rank = all(ranks)
                result.pooled_within_variance_nonzero = bool(np.all(energy > 0))
    return result
