"""Five bounded profiling components. v0.1 uses rules/tools, not LLM calls."""
import json
import re
from importlib.resources import files
from typing import Protocol

import pandas as pd

from .profiling import build_profile, describe_relations, describe_variables
from .schemas import DataProfile, Evidence, KnowledgeProfile, SourceProfile, TaskProfile


class TaskInterpreter(Protocol):
    """Future LLM adapter must return validated TaskProfile with inference evidence."""
    def run(self, goal: str, **roles) -> TaskProfile: ...


class TaskUnderstandingAgent:
    name = "task_understanding"
    keywords = {
        "pca": ["pca", "主成分"],
        "regression": ["regression", "回归"],
        "clustering": ["clustering", "kmeans", "k-means", "聚类"],
        "manova": ["manova", "多元方差"],
        "discriminant": ["discriminant", "判别", "lda"],
    }
    unsupported_requests = {
        "named_method_not_supported": r"\b(logistic|logit|ridge|lasso|poisson|cox|umap|tsne)\b|逻辑回归|逻辑斯[蒂谛]回归|岭回归|泊松回归|负二项回归|弹性网|核主成分|kernel\s+pca|t-sne",
        "unscaled_pca_not_supported": r"不标准化|不进行标准化|不缩放|未标准化|不中心化|unscaled|without\s+(scaling|standardization|centering)",
    }

    def run(self, goal: str, *, task_type: str | None = None, targets=None, predictors=None, groups=None) -> TaskProfile:
        goal = goal.strip()
        def matches(word):
            return bool(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", goal, re.I)) if word.isascii() else word in goal
        hits = [key for key, words in self.keywords.items() if any(matches(w) for w in words)]
        unsupported = [name for name, pattern in self.unsupported_requests.items()
                       if re.search(pattern, goal, re.I)
                       and (name != "unscaled_pca_not_supported" or "pca" in hits or task_type == "pca")]
        inferred = task_type or (hits[0] if len(hits) == 1 else "unknown")
        if unsupported:
            inferred = "unknown"
        evidence = Evidence(origin="user" if task_type else "rule_inference",
            source="CLI task flag" if task_type else "research_goal", method="explicit flag" if task_type else "keyword baseline",
            status="verified" if task_type else "unverified")
        if unsupported:
            evidence = Evidence(origin="rule_inference", source="research_goal", method="unsupported request guard",
                                status="unverified", note="Explicit task category does not authorize substituting another method or preprocessing policy.")
        role_evidence = Evidence(origin="user", source="CLI variable flags", method="explicit variable names", status="verified")
        return TaskProfile(research_goal=goal, task_type=inferred,
            target_variables=targets or [], predictor_variables=predictors or [], group_variables=groups or [],
            expected_output=["profiles", "method ranking", "validated analysis when supported"],
            unknowns=["study_design"] + (["task_type"] if inferred == "unknown" else []) + unsupported,
            evidence={"research_goal": Evidence(origin="user", source="CLI goal", method="verbatim", status="verified"),
                      "task_type": evidence, "variable_roles": role_evidence})


class StructureAgent:
    name = "data_structure"

    def run(self, frame: pd.DataFrame, source: SourceProfile):
        return describe_variables(frame, source)


class RelationsAgent:
    name = "distribution_quality_relations"

    def run(self, frame: pd.DataFrame, task: TaskProfile):
        return describe_relations(frame, task)


class KnowledgeAgent:
    name = "statistical_knowledge"

    def run(self, library: str = "seed") -> list[KnowledgeProfile]:
        """Offline curated seed import. Automatic document/LLM extraction is future work."""
        raw = files("stat_agent").joinpath("knowledge/seed.json").read_text(encoding="utf-8")
        profiles = [KnowledgeProfile.model_validate(item) for item in json.loads(raw)]
        if library == 'expanded':
            extra = files('stat_agent').joinpath('knowledge/expanded.json').read_text(encoding='utf-8')
            profiles.extend(KnowledgeProfile.model_validate(item) for item in json.loads(extra))
        elif library != 'seed':
            raise ValueError('Unknown knowledge library.')
        if len({p.id for p in profiles}) != len(profiles):
            raise ValueError("Duplicate knowledge IDs.")
        return profiles


class ProfileValidationAgent:
    name = "profile_validation"

    def validate_roles(self, frame: pd.DataFrame, task: TaskProfile) -> None:
        roles = task.target_variables + task.predictor_variables + task.group_variables
        missing = sorted(set(roles) - set(frame.columns))
        if missing:
            raise ValueError(f"Unknown variables: {missing}")
        if len(roles) != len(set(roles)):
            raise ValueError("Variable roles must be unique and non-overlapping in v0.1.")

    def run(self, frame, source, task, variables, relations) -> DataProfile:
        self.validate_roles(frame, task)
        profile = build_profile(frame, source, task, variables, relations)
        if len(profile.variables) != profile.structure.p:
            raise ValueError("Profile variable count conflicts with table shape.")
        return DataProfile.model_validate_json(profile.model_dump_json())
