"""Paired extraction/review continuation experiment. Never publishes to the production KB."""
import argparse
import copy
import json
import sys
import time
from pathlib import Path

from .cran import collect_locked
from .kb_agents import (ApplicabilityAgent, EvidenceReviewAgent, FunctionMetadataAgent,
    EXTRACT_SYSTEM, REVIEW_SYSTEM, ReferencedProfile, Review, SemanticProfile, validate_evidence)
from .kb_review import (candidate_items, comparison_form, json_text, read_json, score_review, write_new)
from .kb_store import checksum
from .llm import DeepSeekClient, LLMError, load_ccswitch

PROTOCOL = 'paired-source-profile-1'
ARMS = ['single', 'cooperative']


def prompts():
    return dict(extraction=EXTRACT_SYSTEM, review=REVIEW_SYSTEM,
                extraction_schema=ReferencedProfile.model_json_schema(), review_schema=Review.model_json_schema())


def make_plan(documents, client):
    sources = {d['function_id']: d for d in documents}
    if not documents or len(sources) != len(documents):
        raise ValueError('Experiment needs distinct, nonempty source functions.')
    for document in documents:
        FunctionMetadataAgent().run(document)
    metadata = client.metadata()
    metadata.pop('receipts', None)
    plan = dict(protocol=PROTOCOL, source_set_id=checksum(sources), functions=sorted(sources),
                model=metadata, prompts_sha256=checksum(prompts()), repetitions=1,
                settings=dict(max_output_tokens=client.max_output_tokens, timeout=client.timeout,
                              max_retries=client.max_retries, temperature=0, thinking='disabled'),
                design='One shared initial extraction per source; single stops, cooperative reviews and may correct once.',
                max_logical_calls_per_function=4, shared_initial_call_charged_to_both_arm_estimates=True,
                realized_cost_counts_shared_call_once=True)
    return dict(plan, plan_id=checksum(plan))


def case_path(folder, function_id):
    return Path(folder)/'cases'/(checksum(function_id)+'.json')


def save_case(path, record):
    body = {k:v for k,v in record.items() if k != 'record_sha256'}
    value = dict(body, record_sha256=checksum(body))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json_text(value), encoding='utf-8')
    temporary.replace(path)


def read_case(path, plan, function_id):
    record = read_json(path)
    body = {k:v for k,v in record.items() if k != 'record_sha256'}
    if record.get('record_sha256') != checksum(body) or record.get('plan_id') != plan['plan_id'] or record.get('function_id') != function_id:
        raise ValueError('Experiment case integrity or identity mismatch.')
    return record


def run_case(document, client, plan, folder, progress=None):
    identity = document['function_id']
    path = case_path(folder, identity)
    if path.exists():
        old = read_case(path, plan, identity)
        if old['state'] != 'completed':
            raise ValueError('An interrupted case has uncertain call completion; preserve it and use a new experiment directory.')
        return old
    record = dict(plan_id=plan['plan_id'], function_id=identity, source_rd_sha256=document['rd_sha256'],
                  state='running', pending_phase=None, phases=[], single=None, cooperative=None)

    def operation(name, call):
        record['pending_phase'] = name
        save_case(path, record)
        before, receipt_start, started = dict(client.usage), len(client.receipts), time.perf_counter()
        value, error = None, None
        try:
            value = call()
        except LLMError as exc:
            error = str(exc)  # Adapter errors are sanitized; raw provider bodies are never saved.
        except ValueError:
            error = 'Structured validation failed; raw values omitted.'
        phase = dict(name=name, status='error' if error else 'completed', error=error,
                     seconds=time.perf_counter()-started,
                     usage={k:v-before.get(k, 0) for k,v in client.usage.items()},
                     receipts=copy.deepcopy(client.receipts[receipt_start:]),
                     output=value.model_dump(mode='json') if value is not None else None)
        record['phases'].append(phase)
        record['pending_phase'] = None
        save_case(path, record)
        if progress:
            progress(dict(function_id=identity, phase=name, status=phase['status'], usage=phase['usage']))
        return value

    extraction, reviewer = ApplicabilityAgent(client), EvidenceReviewAgent(client)
    initial = operation('initial_extraction', lambda: extraction.run(document, []))
    if initial is None:
        record['single'] = dict(status='generation_error', semantic=None)
        record['cooperative'] = dict(status='initial_generation_error', semantic=None)
    else:
        initial_checks = validate_evidence(document, initial)
        record['single'] = dict(status='structurally_valid' if not initial_checks else 'structural_failure',
                                semantic=initial.model_dump(mode='json'), structural_issues=initial_checks,
                                semantic_review='not_performed')
        draft = initial
        review = operation('initial_review', lambda: reviewer.run(document, draft))
        if review is not None and not review.accepted:
            corrected = operation('correction_extraction', lambda: extraction.run(document, review.issues or [review.explanation]))
            if corrected is not None:
                draft = corrected
                review = operation('final_review', lambda: reviewer.run(document, draft))
            else:
                review = None
        record['cooperative'] = dict(status='review_error' if review is None else
            'machine_accepted' if review.accepted else 'needs_review', semantic=draft.model_dump(mode='json'),
            structural_issues=validate_evidence(document, draft),
            semantic_review='same_model_review_not_independent',
            review=review.model_dump(mode='json') if review is not None else None)
    record['state'] = 'completed'
    save_case(path, record)
    return read_case(path, plan, identity)


def usage_sum(phases):
    keys = {k for p in phases for k in p['usage']}
    return {k: sum(p['usage'].get(k, 0) for p in phases) for k in sorted(keys)}


def summarize(plan, cases):
    complete = [c for c in cases if c['state'] == 'completed']
    arms = {}
    for arm in ARMS:
        phases = [p for c in complete for p in (c['phases'][:1] if arm == 'single' else c['phases'])]
        candidates = [c[arm] for c in complete]
        arms[arm] = dict(planned_functions=len(plan['functions']), completed_functions=len(complete),
            candidates_available=sum(c['semantic'] is not None for c in candidates),
            structurally_valid=sum(c['semantic'] is not None and not c.get('structural_issues', []) for c in candidates),
            status_counts={s:sum(c['status']==s for c in candidates) for s in sorted({c['status'] for c in candidates})},
            accounted_usage=usage_sum(phases), phase_seconds=sum(p['seconds'] for p in phases),
            field_accuracy=None, field_completeness=None, semantic_accuracy=None,
            unsupported_inference_rate=None, api_cost_usd=None)
    all_phases = [p for c in cases for p in c['phases']]
    return dict(protocol=PROTOCOL, plan_id=plan['plan_id'],
        execution_status='completed' if len(complete) == len(plan['functions']) else 'incomplete',
        human_quality_status='awaiting_independent_reference_and_annotations',
        functions=plan['functions'], arms=arms, realized_usage=usage_sum(all_phases),
        realized_phase_seconds=sum(p['seconds'] for p in all_phases), api_cost_usd=None,
        limitations=['Paired continuation, not two independently sampled generations; initial extraction is shared.',
            'Arm cost estimates both include initial extraction. Do not add arms to obtain realized API usage.',
            'Provider model alias is not an immutable model revision; one repetition is not a significance test.',
            'Schema/evidence checks and model acceptance are not human correctness labels.',
            'Provider-reported tokens omit unreported consumption from failed calls; currency cost is not estimated.',
            'No production profiles, hand-authored rules, or Codex source corrections are used as experimental answers.'])


def run_experiment(documents, client, folder, progress=None):
    folder = Path(folder)
    plan = make_plan(documents, client)
    sources = {d['function_id']:d for d in documents}
    artifacts = {'plan.json':plan, 'sources.json':sources, 'prompts.json':prompts()}
    # Check the entire run identity before any paid call or output mutation.
    for name, value in artifacts.items():
        path = folder/name
        if path.exists() and read_json(path) != value:
            raise ValueError('Experiment configuration changed; use a new output directory.')
    for name, value in artifacts.items():
        write_new(folder/name, json_text(value))
    cases = []
    for identity in plan['functions']:
        result = run_case(sources[identity], client, plan, folder, progress)
        cases.append(result)
        (folder/'summary.json').write_text(json_text(summarize(plan, cases)), encoding='utf-8')
    return summarize(plan, cases)


def load_experiment(folder):
    folder = Path(folder)
    plan, sources = read_json(folder/'plan.json'), read_json(folder/'sources.json')
    body = {k:v for k,v in plan.items() if k != 'plan_id'}
    if (plan.get('protocol') != PROTOCOL or checksum(body) != plan.get('plan_id') or
            checksum(sources) != plan['source_set_id'] or sorted(sources) != plan['functions'] or
            checksum(read_json(folder/'prompts.json')) != plan['prompts_sha256']):
        raise ValueError('Experiment source, prompt or plan integrity check failed.')
    cases = [read_case(case_path(folder, identity), plan, identity) for identity in plan['functions']
             if case_path(folder, identity).exists()]
    return plan, sources, cases


def review_material(folder, arm):
    if arm not in ARMS:
        raise ValueError('Unknown experimental arm.')
    plan, sources, cases = load_experiment(folder)
    if len(cases) != len(plan['functions']) or any(c['state'] != 'completed' or c[arm]['semantic'] is None for c in cases):
        raise ValueError('All planned candidates must exist before review; failed functions cannot silently leave the denominator.')
    records = []
    for case in cases:
        record = dict(metadata={'function_id':case['function_id']}, source=sources[case['function_id']],
                      semantic=case[arm]['semantic'])
        SemanticProfile.model_validate(record['semantic'])
        record['revision'] = checksum(record)
        records.append(record)
    items = candidate_items(records)
    manifest = dict(policy='paired-experiment-review-1', source_set_id=plan['source_set_id'], plan_id=plan['plan_id'],
                    arm=arm, candidate_items_sha256=checksum(items), case_hashes=[c['record_sha256'] for c in cases])
    manifest['packet_id'] = checksum(manifest)
    return manifest, sources, items


def main(argv=None):
    parser = argparse.ArgumentParser(description='Paired single-extraction / cooperative-review profiling experiment')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--lock', type=Path, default=Path('configs/cran_sources.lock.json'))
    run.add_argument('--cache', type=Path, default=Path('.cache/cran'))
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--functions', nargs='+')
    report = commands.add_parser('report')
    report.add_argument('--experiment', type=Path, required=True)
    for name in ['review-form', 'review-score']:
        command = commands.add_parser(name)
        command.add_argument('--experiment', type=Path, required=True)
        command.add_argument('--arm', choices=ARMS, required=True)
        command.add_argument('--reference', type=Path, required=True)
        command.add_argument('--out', type=Path, required=True)
        if name == 'review-score':
            command.add_argument('--annotations', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            documents = collect_locked(args.lock, args.cache)
            if args.functions:
                requested = set(args.functions)
                if len(requested) != len(args.functions) or requested - {d['function_id'] for d in documents}:
                    raise ValueError('Requested functions must be distinct members of the source lock.')
                documents = [d for d in documents if d['function_id'] in requested]
            client = DeepSeekClient(load_ccswitch(), timeout=60, max_retries=1, max_output_tokens=4000)
            result = run_experiment(documents, client, args.out,
                progress=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
        elif args.command == 'report':
            plan, _, cases = load_experiment(args.experiment)
            result = summarize(plan, cases)
        else:
            manifest, sources, items = review_material(args.experiment, args.arm)
            reference = read_json(args.reference)
            if args.command == 'review-form':
                candidates, annotations = comparison_form(reference, manifest, sources, items)
                write_new(args.out/'candidates.json', json_text(candidates))
                write_new(args.out/'annotations.template.json', json_text(annotations))
                result = dict(status='awaiting_annotation', arm=args.arm, item_count=len(items))
            else:
                result = score_review(reference, read_json(args.annotations), manifest, sources, items)
                write_new(args.out, json_text(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'profile-experiment: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
