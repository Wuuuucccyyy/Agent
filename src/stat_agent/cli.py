import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_pipeline
from .retrieval import LexicalEncoder, SentenceEncoder, pinned_encoder
from .schemas import DataProfile, KnowledgeProfile, TaskProfile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="多模态统计分析 Agent v0.2：表格画像与方法检索")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Read a CSV/XLSX, profile, retrieve and run an audited template")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--goal", required=True)
    analyze.add_argument("--task", choices=["pca", "regression", "clustering", "manova", "discriminant"])
    analyze.add_argument("--targets", nargs="*", default=[])
    analyze.add_argument("--predictors", nargs="*", default=[])
    analyze.add_argument("--groups", nargs="*", default=[])
    analyze.add_argument("--sheet", default="0", help="Zero-based index or sheet name")
    analyze.add_argument("--out", type=Path, default=Path("runs"))
    analyze.add_argument("--encoder", choices=["lexical", "sentence"], default="lexical")
    analyze.add_argument("--model", help="Local model path or sentence-transformers model ID")
    analyze.add_argument("--revision", help="Pin model revision for reproducible semantic runs")
    analyze.add_argument('--embedding-config', type=Path, help='Pinned local model configuration; implies sentence encoder')
    analyze.add_argument('--task-agent', choices=['rules', 'deepseek'], default='rules')
    analyze.add_argument('--knowledge', choices=['seed', 'expanded'], default='seed')
    schemas = commands.add_parser("schemas")
    schemas.add_argument("--out", type=Path, default=Path("schemas"))
    args = parser.parse_args(argv)
    try:
        if args.command == "schemas":
            args.out.mkdir(parents=True, exist_ok=True)
            for model in [TaskProfile, DataProfile, KnowledgeProfile]:
                (args.out / f"{model.__name__}.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
            return 0
        if args.encoder == "sentence" and not args.model and not args.embedding_config:
            parser.error("--encoder sentence requires --model")
        encoder = (pinned_encoder(args.embedding_config) if args.embedding_config else
                   SentenceEncoder(args.model, args.revision) if args.encoder == "sentence" else LexicalEncoder())
        task_agent = None
        if args.task_agent == 'deepseek':
            from .llm import DeepSeekClient, DeepSeekTaskAgent, load_ccswitch
            task_agent = DeepSeekTaskAgent(DeepSeekClient(load_ccswitch()))
        sheet = int(args.sheet) if args.sheet.isdecimal() else args.sheet
        folder = run_pipeline(args.input, args.goal, args.out, sheet=sheet, encoder=encoder,
                              task_agent=task_agent, knowledge_library=args.knowledge,
                              task_type=args.task, targets=args.targets, predictors=args.predictors, groups=args.groups)
        outcome = json.loads((folder / "execution.json").read_text(encoding="utf-8"))
        print(json.dumps({"output": str(folder.resolve()), "status": outcome["status"]}, ensure_ascii=False))
        return 0 if outcome["status"] == "success" else 2
    except (ValueError, OSError, KeyError) as exc:
        print(f"stat-agent: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
