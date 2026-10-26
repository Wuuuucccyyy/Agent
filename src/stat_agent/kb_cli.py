"""Offline knowledge database collection, construction, restoration and search CLI."""
import argparse
import json
import sys
from pathlib import Path

from .cran import lock_sources
from .kb_build import build_database
from .kb_store import KnowledgeDatabase
from .retrieval import LexicalEncoder, pinned_encoder, query_text


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description='CRAN function applicability knowledge database')
    commands = parser.add_subparsers(dest='command', required=True)
    collect = commands.add_parser('collect', help='Resolve selected CRAN versions and download source archives')
    collect.add_argument('--config', type=Path, default=Path('configs/cran_seed.json'))
    collect.add_argument('--lock', type=Path, default=Path('configs/cran_sources.lock.json'))
    collect.add_argument('--cache', type=Path, default=Path('.cache/cran'))
    build = commands.add_parser('build', help='Use DeepSeek extraction and review to create a versioned database')
    build.add_argument('--lock', type=Path, default=Path('configs/cran_sources.lock.json'))
    build.add_argument('--cache', type=Path, default=Path('.cache/cran'))
    build.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    build.add_argument('--export', type=Path, default=Path('database/cran_profiles.json'))
    build.add_argument('--report', type=Path, default=Path('evaluation/results/cran_build.json'))
    build.add_argument('--refresh', action='store_true', help='Re-run model calls even when a matching checked profile exists')
    restore = commands.add_parser('restore', help='Restore checked JSON export without network or credentials')
    restore.add_argument('--export', type=Path, default=Path('database/cran_profiles.json'))
    restore.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    index = commands.add_parser('index', help='Create/reuse persistent vectors for the active snapshot')
    index.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    index.add_argument('--embedding-config', type=Path, default=Path('configs/embedding.json'))
    search = commands.add_parser('search', help='Return candidate profiles; does not execute methods')
    search.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    search.add_argument('--goal', required=True)
    search.add_argument('--input', type=Path, help='Optional CSV/XLSX used to create an actual data profile')
    search.add_argument('--task', choices=['pca', 'regression', 'clustering', 'manova', 'discriminant'])
    search.add_argument('--targets', nargs='*', default=[])
    search.add_argument('--predictors', nargs='*', default=[])
    search.add_argument('--groups', nargs='*', default=[])
    search.add_argument('--embedding-config', type=Path)
    search.add_argument('--top-k', type=int, default=5)
    search.add_argument('--out', type=Path)
    inspect = commands.add_parser('inspect', help='Inspect active snapshot and all review states')
    inspect.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'collect':
            result = lock_sources(args.config, args.lock, args.cache)
            print(json.dumps({'lock': str(args.lock), 'packages': [(p['name'], p['version']) for p in result['packages']]}))
            return 0
        db = KnowledgeDatabase(args.db, create=args.command in {'build', 'restore'})
        if args.command == 'build':
            from .llm import DeepSeekClient, load_ccswitch
            client = DeepSeekClient(load_ccswitch(), max_output_tokens=4000, timeout=60)
            result = build_database(db, args.lock, args.cache, client, refresh=args.refresh,
                                    progress=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
            write_json(args.report, result)
            if result['snapshot']:
                db.export(args.export)
            print(json.dumps({k:result[k] for k in ['status', 'function_count', 'machine_checked', 'needs_review', 'errors', 'usage']}))
            return 0 if result['status'] == 'success' else 2
        if args.command == 'restore':
            result = db.restore(args.export)
        elif args.command == 'index':
            result = db.index(pinned_encoder(args.embedding_config))
        elif args.command == 'inspect':
            result = {'snapshot': db.snapshot(), 'profiles': [{'id': r['metadata']['function_id'],
                'version': r['metadata']['package_version'], 'status': r['status'], 'revision': r['revision']}
                for r in db.records(include_needs_review=True)]}
        else:
            encoder = pinned_encoder(args.embedding_config) if args.embedding_config else LexicalEncoder()
            query, profiles = args.goal, None
            if args.input:
                from .agents import TaskUnderstandingAgent, StructureAgent, RelationsAgent, ProfileValidationAgent
                from .io import read_table
                frame, source = read_table(args.input)
                task = TaskUnderstandingAgent().run(args.goal, task_type=args.task,
                    targets=args.targets, predictors=args.predictors, groups=args.groups)
                validator = ProfileValidationAgent()
                validator.validate_roles(frame, task)
                profile = validator.run(frame, source, task, StructureAgent().run(frame, source), RelationsAgent().run(frame, task))
                query = query_text(task, profile)
                profiles = {'task': task.model_dump(mode='json'), 'data': profile.model_dump(mode='json')}
            result = {'snapshot_id': db.snapshot()['snapshot_id'], 'encoder': encoder.name,
                      'query': query, 'profiles': profiles, 'candidates': db.search(query, encoder, args.top_k),
                      'scope': 'Candidate discovery only. Conditions are displayed, not executed as automatic hard rules.'}
            if args.out:
                write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f'stat-agent kb: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
