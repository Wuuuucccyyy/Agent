"""Source-bound, non-executable conditions with three-valued logic."""
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from .kb_agents import EvidenceSpan

Fact = Literal['task.type', 'input.kind', 'data.n', 'features.count', 'features.numeric',
    'features.numeric_or_boolean', 'features.missing', 'features.nonfinite', 'features.pairwise_overlap',
    'groups.provided', 'groups.count', 'groups.min_size', 'groups.no_missing', 'groups.full_rank',
    'groups.within_variance_nonzero', 'response.provided', 'response.numeric', 'response.missing',
    'matrix.square', 'matrix.symmetric', 'matrix.diagonal_zero', 'matrix.diagonal_one',
    'matrix.nonnegative', 'matrix.correlation_bounds', 'matrix.condensed_valid',
    'param.k', 'param.nfactors', 'param.sampsize', 'param.metric', 'param.method', 'param.na_action',
    'processing.complete']
Scalar = StrictStr | StrictInt | StrictFloat | StrictBool


class Parameters(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    input_kind: Literal['observations', 'dissimilarity', 'dissimilarity_condensed', 'correlation', 'covariance'] = 'observations'
    k: StrictInt | None = None
    nfactors: StrictInt | None = None
    sampsize: StrictInt | None = None
    metric: str | None = Field(default=None, max_length=64)
    method: str | None = Field(default=None, max_length=64)
    na_action: Literal['fail', 'omit', 'unspecified'] | None = None


class Predicate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    fact: Fact
    op: Literal['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in']
    value: Scalar | list[Scalar] | None = None
    other_fact: Fact | None = None

    @model_validator(mode='after')
    def validate_operand(self):
        if (self.other_fact is None) == (self.value is None):
            raise ValueError('Exactly one non-null value or other_fact is required.')
        if self.op == 'in' and not isinstance(self.value, list):
            raise ValueError('Membership requires a literal list.')
        if self.op != 'in' and isinstance(self.value, list):
            raise ValueError('Lists are only allowed for membership.')
        return self


class ConditionRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z0-9_]+$', max_length=80)
    description: str = Field(min_length=1, max_length=600)
    severity: Literal['hard', 'advisory'] = 'hard'
    origin: Literal['official_document', 'derived', 'input_contract']
    derivation: str = Field(default='', max_length=1000)
    when: list[Predicate] = Field(default_factory=list, max_length=8)
    conditions: list[Predicate] = Field(min_length=1, max_length=12)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=6)

    @model_validator(mode='after')
    def derived_explanation(self):
        if self.origin != 'official_document' and not self.derivation:
            raise ValueError('Derived conditions require an explicit explanation.')
        return self


class RuleSet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1.0'] = '1.0'
    function_id: str
    source_rd_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    semantic_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    defaults: Parameters = Field(default_factory=Parameters)
    rules: list[ConditionRule] = Field(min_length=1, max_length=64)
    coverage_notes: list[str] = Field(min_length=1)


def validate_rule_set(record):
    from .kb_store import checksum
    if 'rules' not in record:
        return None
    rules = RuleSet.model_validate(record['rules'])
    if (rules.function_id != record['metadata']['function_id'] or
            rules.source_rd_sha256 != record['source']['rd_sha256'] or
            rules.semantic_sha256 != checksum(record['semantic'])):
        raise ValueError('Rules do not match the source and semantic profile version.')
    if len({r.id for r in rules.rules}) != len(rules.rules):
        raise ValueError('Duplicate rule identifiers.')
    for rule in rules.rules:
        for span in rule.evidence:
            source = record['source']['sections'].get(span.section, '')
            normal = lambda s: re.sub(r'\s+', ' ', s).strip()
            if normal(span.quote) not in normal(source):
                raise ValueError('Rule evidence does not occur in the locked source.')
    return rules


def _and(values):
    return False if False in values else None if None in values else True


def compare(predicate, facts):
    left = facts.get(predicate.fact)
    right = facts.get(predicate.other_fact) if predicate.other_fact else predicate.value
    if left is None or right is None:
        return None
    if predicate.op in {'lt', 'le', 'gt', 'ge'}:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in [left, right]):
            return None
    if predicate.op == 'eq':
        return type(left) is type(right) and left == right
    if predicate.op == 'ne':
        return not (type(left) is type(right) and left == right)
    if predicate.op == 'in':
        return any(type(left) is type(v) and left == v for v in right)
    return {'lt': lambda: left < right, 'le': lambda: left <= right,
            'gt': lambda: left > right, 'ge': lambda: left >= right}[predicate.op]()


def observed_facts(profile, task, parameters, *, function_id=None):
    facts = {'task.type': None if task is None or task.task_type == 'unknown' else task.task_type,
             'input.kind': parameters.input_kind}
    for name in ['k', 'nfactors', 'sampsize', 'metric', 'method', 'na_action']:
        facts['param.'+name] = getattr(parameters, name)
    if profile is None:
        return facts
    app = profile.applicability
    variables = {v.name: v for v in profile.variables}
    if task:
        features = task.predictor_variables or [v.name for v in profile.variables
            if v.kind == 'numeric' and v.name not in task.group_variables + task.target_variables]
    else:
        features = app.columns if app else profile.relations.columns
    if any(c not in variables for c in features):
        raise ValueError('Task feature roles do not match the supplied profile.')
    selected = [variables[c] for c in features]
    facts.update({'data.n': profile.structure.n, 'features.count': len(features),
                  'features.numeric': all(v.kind == 'numeric' for v in selected) if selected else None,
                  'features.numeric_or_boolean': all(v.kind in {'numeric', 'boolean'} for v in selected) if selected else None,
                  'features.missing': sum(v.missing_count for v in selected) if selected else None,
                  'features.nonfinite': sum(v.nonfinite_count for v in selected) if selected else None})
    if parameters.input_kind in {'correlation', 'covariance'}:
        facts['data.n'] = None  # Matrix dimension is not an observed sample size.
    if parameters.input_kind == 'dissimilarity_condensed':
        length = profile.structure.n
        n = (1+math.isqrt(1+8*length))//2
        valid = len(features) == 1 and n*(n-1)//2 == length
        facts['matrix.condensed_valid'] = valid
        facts['data.n'] = n if valid else None
    if app and features == app.columns:
        for name, value in {'features.pairwise_overlap': app.pairwise_observed_overlap,
                'groups.count': app.group_count, 'groups.min_size': app.minimum_group_size,
                'groups.full_rank': app.within_group_full_rank,
                'groups.within_variance_nonzero': app.pooled_within_variance_nonzero,
                'groups.no_missing': None if app.group_missing_count is None else app.group_missing_count == 0,
                'matrix.square': app.square, 'matrix.symmetric': app.symmetric,
                'matrix.diagonal_zero': app.diagonal_zero, 'matrix.diagonal_one': app.diagonal_one,
                'matrix.nonnegative': app.nonnegative, 'matrix.correlation_bounds': app.correlation_bounds}.items():
            facts[name] = value
        if task is None or task.group_variables != app.group_columns:
            for name in list(facts):
                if name.startswith('groups.'):
                    facts[name] = None
    if task:
        if any(c not in variables for c in task.group_variables + task.target_variables):
            raise ValueError('Task roles do not match the supplied profile.')
        facts['groups.provided'] = None if not task.group_variables else len(task.group_variables) == 1
        facts['response.provided'] = None if not task.target_variables else len(task.target_variables) == 1
        if task.target_variables:
            responses = [variables[c] for c in task.target_variables]
            facts['response.numeric'] = all(v.kind == 'numeric' for v in responses)
            facts['response.missing'] = sum(v.missing_count for v in responses)
    complete = facts.get('features.missing') == 0 and facts.get('features.nonfinite') == 0
    if facts.get('response.missing', 0) or facts.get('groups.no_missing') is False:
        complete = False
    facts['processing.complete'] = True if complete else None
    if not complete:
        # A declared omission policy is not evidence that preprocessing has occurred.
        facts['groups.full_rank'] = None
        facts['groups.within_variance_nonzero'] = None
        if parameters.na_action == 'omit':
            facts['groups.min_size'] = None
    if (function_id == 'cluster::clara' and facts['param.sampsize'] is None
            and facts.get('data.n') is not None and parameters.k is not None):
        facts['param.sampsize'] = min(facts['data.n'], 40+2*parameters.k)
    return facts


def evaluate_conditions(record, *, profile=None, task=None, parameters=None):
    rules = validate_rule_set(record)
    if rules is None:
        return {'state': 'unknown', 'excluded': False, 'rules': [], 'reason': 'No reviewed structured rules.'}
    overrides = parameters or {}
    values = rules.defaults.model_dump()
    values.update(overrides)
    params = Parameters.model_validate(values)
    facts = observed_facts(profile, task, params, function_id=rules.function_id)
    outcomes = []
    labels = {True: 'satisfied', False: 'violated', None: 'unknown'}
    for rule in rules.rules:
        applies = _and([compare(p, facts) for p in rule.when])
        value = _and([compare(p, facts) for p in rule.conditions]) if applies is True else None
        details = [{'predicate': p.model_dump(exclude_none=True), 'observed': facts.get(p.fact),
                    'expected': facts.get(p.other_fact) if p.other_fact else p.value,
                    'state': labels[compare(p, facts)]} for p in rule.conditions]
        outcomes.append({'id': rule.id, 'description': rule.description, 'severity': rule.severity,
                         'origin': rule.origin, 'derivation': rule.derivation, 'applicable': applies,
                         'state': labels[value], 'checks': details,
                         'reason': 'Branch not enabled; excluded from verdict.' if applies is False else
                                   'Branch facts are unavailable.' if applies is None else 'Compared observed facts with the declared condition.',
                         'evidence': [e.model_dump() for e in rule.evidence]})
    active = [r for r in outcomes if r['applicable'] is not False]
    excluded = any(r['state'] == 'violated' and r['severity'] == 'hard' for r in active)
    state = 'violated' if excluded else 'unknown' if any(r['state'] != 'satisfied' for r in active) or not active else 'satisfied'
    return {'state': state, 'excluded': excluded, 'rules': outcomes, 'facts': facts,
            'parameters': params.model_dump(), 'source_rd_sha256': rules.source_rd_sha256,
            'scope': 'Implemented necessary conditions only; no execution or general statistical validity is authorized.',
            'coverage_notes': rules.coverage_notes, 'unresolved_assumptions': record['semantic']['unknowns']}
