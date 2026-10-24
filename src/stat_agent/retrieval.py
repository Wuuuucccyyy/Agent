"""Shared-space encoders, cosine retrieval and explainable statistical constraints."""
from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .schemas import Candidate, DataProfile, KnowledgeProfile, Penalty, RetrievalResult, TaskProfile


class Encoder(Protocol):
    name: str
    def encode_pair(self, query: str, documents: list[str]) -> tuple[np.ndarray, np.ndarray]: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    values = np.asarray(vectors, dtype=float)
    if values.ndim != 2 or not values.shape[0] or not values.shape[1] or not np.isfinite(values).all():
        raise ValueError("Expected nonempty, finite 2D embeddings.")
    # Scale first to avoid overflow for large but finite embeddings.
    scale = np.max(np.abs(values), axis=1, keepdims=True)
    if np.any(scale == 0):
        raise ValueError("Zero embedding cannot be normalized.")
    scaled = values / scale
    return scaled / np.linalg.norm(scaled, axis=1, keepdims=True)


class LexicalEncoder:
    """Offline smoke-test baseline, explicitly NOT a pretrained semantic encoder."""
    name = "tfidf_char_lexical_smoke_only"

    def encode_pair(self, query, documents):
        if not query.strip() or not documents or any(not d.strip() for d in documents):
            raise ValueError("Empty query/document.")
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4))
        matrix = vectorizer.fit_transform(documents).toarray()
        return vectorizer.transform([query]).toarray(), matrix


class SentenceEncoder:
    """One pretrained model for both towers; caller pins model revision/path."""
    def __init__(self, model: str, revision: str | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ValueError("Install the semantic extra: pip install -e '.[semantic]'") from exc
        self.model = SentenceTransformer(model, revision=revision, trust_remote_code=False)
        self.name = f"sentence_transformers:{model}@{revision or 'unpinned'}"

    def encode_pair(self, query, documents):
        if not query.strip() or not documents or any(not d.strip() for d in documents):
            raise ValueError("Empty query/document.")
        return (self.model.encode_query([query], convert_to_numpy=True),
                self.model.encode_document(documents, convert_to_numpy=True))


def query_text(task: TaskProfile, profile: DataProfile) -> str:
    # Keep raw cells and entire conversations out of the query.
    return (f"{task.task_type} {task.research_goal[:1200]} "
            f"targets={','.join(task.target_variables)} predictors={','.join(task.predictor_variables)} "
            f"n={profile.structure.n} p={profile.structure.p} "
            f"missing={profile.quality.missing_rate:.3f} rank={profile.relations.centered_rank}")


def document_text(item: KnowledgeProfile) -> str:
    return " ".join([item.id, " ".join(item.task_types), item.summary,
                     " ".join(item.input_constraints), " ".join(item.assumptions)])


def constraints(task: TaskProfile, profile: DataProfile, item: KnowledgeProfile):
    hard, penalties = [], []
    unknowns = ["Study design and independence have not been verified."]
    if task.task_type not in item.task_types:
        hard.append(f"Task {task.task_type} is outside {item.id}'s supported tasks.")
    variables = {v.name: v for v in profile.variables}
    features = task.predictor_variables or profile.relations.columns
    selected = features + task.target_variables + task.group_variables
    if not features:
        hard.append("No predictor/numeric feature columns are available.")
    if any(variables[c].kind != "numeric" for c in features):
        hard.append("This baseline knowledge signature requires numeric predictors; encode or select columns first.")
    if task.task_type in {"regression", "manova"}:
        if not task.target_variables:
            unknowns.append("Explicit target variables are required before execution.")
        elif any(variables[c].kind != "numeric" for c in task.target_variables):
            hard.append("Numeric response variables are required for this method signature.")
    if task.task_type == "manova" and len(task.target_variables) == 1:
        hard.append("MANOVA requires multiple responses; consider univariate ANOVA.")
    if task.task_type in {"manova", "discriminant"} and not task.group_variables:
        unknowns.append("Explicit group variable and study design are required.")
    if profile.structure.n < 2:
        hard.append("At least two observations are required by this baseline workflow.")
    selected_profiles = [variables[c] for c in selected]
    rate = max((v.missing_rate for v in selected_profiles), default=0)
    if rate:
        penalties.append(Penalty(name="missing_values", severity=rate, weight=0.5,
            reason="Selected variables contain missing values; a missing-data policy must be chosen."))
        unknowns.append("Missingness mechanism is unknown; complete-case validity is not established.")
    if any(v.nonfinite_count for v in selected_profiles):
        hard.append("Selected variables contain infinite values; repair or transform input first.")
    if any(v.name in profile.quality.all_missing_columns for v in selected_profiles):
        hard.append("A selected variable has no observed values.")
    if item.id == "stats::lm":
        if profile.relations.singular:
            penalties.append(Penalty(name="collinearity", severity=1, weight=0.5,
                reason="Centered predictor matrix is rank deficient; unique coefficient interpretation fails."))
        if profile.structure.n <= len(features) + 1:
            penalties.append(Penalty(name="residual_df", severity=1, weight=0.5,
                reason="No positive residual degrees of freedom for full-rank OLS with intercept."))
        unknowns.extend(["Linearity, homoscedasticity and residual distribution require model-specific diagnostics."])
    if item.id == "stats::prcomp":
        if any(c in profile.quality.constant_columns for c in features):
            penalties.append(Penalty(name="constant_features", severity=1, weight=0.5,
                reason="Constant variables prevent unit-variance scaling; unscaled PCA may still be possible."))
        unknowns.append("Scaling and feature selection need scientific justification; PCA needs no marginal normality assumption.")
    if item.id in {"MASS::lda", "stats::manova"}:
        unknowns.append("Within-group covariance, group sample sizes and inferential assumptions need diagnostics.")
    return hard, penalties, unknowns


def retrieve(task: TaskProfile, profile: DataProfile, knowledge: list[KnowledgeProfile],
             encoder: Encoder | None = None, *, alpha=1.0, penalty_lambda=0.5, mode="C") -> RetrievalResult:
    if mode not in {"A", "B", "C"} or not np.isfinite([alpha, penalty_lambda]).all() or alpha < 0 or penalty_lambda < 0:
        raise ValueError("Invalid retrieval mode or nonnegative finite weights.")
    encoder = encoder or LexicalEncoder()
    status = "needs_clarification" if task.task_type == "unknown" else "no_compatible_method"
    result = RetrievalResult(status=status, encoder=encoder.name, mode=mode, alpha=alpha,
                             penalty_lambda=penalty_lambda, ranked=[], excluded=[])
    if task.task_type == "unknown" or not knowledge:
        return result
    query, docs = encoder.encode_pair(query_text(task, profile), [document_text(k) for k in knowledge])
    query, docs = normalize(query), normalize(docs)
    if query.shape[0] != 1 or docs.shape[0] != len(knowledge) or query.shape[1] != docs.shape[1]:
        raise ValueError("Query and document embeddings must share an aligned space and correct row counts.")
    similarities = np.clip((query @ docs.T)[0], -1, 1)
    for item, cosine in zip(knowledge, similarities):
        hard, penalties, unknowns = constraints(task, profile, item)
        total = sum(p.severity * p.weight for p in penalties)
        candidate = Candidate(knowledge_id=item.id, cosine=float(cosine), hard_failures=hard,
            penalties=penalties, unknowns=unknowns, penalty_total=total,
            score=float(alpha * cosine - (penalty_lambda * total if mode == "C" else 0)), source_url=item.source_url)
        (result.excluded if hard and mode != "A" else result.ranked).append(candidate)
    result.ranked.sort(key=lambda c: (-c.score, c.knowledge_id))
    result.status = "ranked" if result.ranked else "no_compatible_method"
    return result
