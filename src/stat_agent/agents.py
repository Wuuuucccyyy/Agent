"""Five bounded profiling components. v0.1 uses rules/tools, not LLM calls."""
import json
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
        "pca": ["pca", "主成分", "降维"],
        "regression": ["regression", "回归"],
        "clustering": ["clustering", "kmeans", "k-means", "聚类"],
        "manova": ["manova", "多元方差", "组间比较"],
        "discriminant": ["discriminant", "判别", "lda"],
    }

    def run(self, goal: str, *, task_type: str | None = None, targets=None, predictors=None, groups=None) -> TaskProfile:
        goal = goal.strip()
        hits = [key for key, words in self.keywords.items() if any(w in goal.lower() for w in words)]
        inferred = task_type or (hits[0] if len(hits) == 1 else "unknown")
        evidence = Evidence(origin="user" if task_type else "rule_inference",
            source="CLI task flag" if task_type else "research_goal", method="explicit flag" if task_type else "keyword baseline",
            status="verified" if task_type else "unverified")
        role_evidence = Evidence(origin="user", source="CLI variable flags", method="explicit variable names", status="verified")
        return TaskProfile(research_goal=goal, task_type=inferred,
            target_variables=targets or [], predictor_variables=predictors or [], group_variables=groups or [],
            expected_output=["profiles", "method ranking", "validated analysis when supported"],
            unknowns=["study_design"] + (["task_type"] if inferred == "unknown" else []),
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

    def run(self) -> list[KnowledgeProfile]:
        """Offline curated seed import. Automatic document/LLM extraction is future work."""
        raw = files("stat_agent").joinpath("knowledge/seed.json").read_text(encoding="utf-8")
        profiles = [KnowledgeProfile.model_validate(item) for item in json.loads(raw)]
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
