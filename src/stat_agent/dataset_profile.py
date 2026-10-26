"""Standalone local dataset profiling, independent of method retrieval or execution."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import __version__
from .agents import TaskUnderstandingAgent, StructureAgent, RelationsAgent, ProfileValidationAgent
from .io import read_table


def render_profile(profile):
    def cell(value):
        if value is None:
            return '未计算'
        text = f'{value:.6g}' if isinstance(value, float) else str(value)
        return text.replace('|', '\\|').replace('\n', ' ')
    lines = ['# 数据集画像', '', f'样本数：{profile.structure.n}；变量数：{profile.structure.p}。', '',
             f'来源：{cell(profile.source.file_name)}；SHA256：`{profile.source.sha256}`。', '',
             f'缺失单元格：{profile.quality.missing_cells}；缺失比例：{profile.quality.missing_rate:.2%}；重复行：{profile.structure.duplicate_rows}。', '',
             '| 变量 | 类型 | 缺失数 | 无穷值数 | 唯一值数 | 均值 | 样本方差 |',
             '|---|---|---:|---:|---:|---:|---:|']
    for variable in profile.variables:
        values = [variable.name, variable.kind, variable.missing_count, variable.nonfinite_count,
                  variable.n_unique, variable.mean, variable.variance]
        lines.append('| '+' | '.join(map(cell, values))+' |')
    lines += ['', '## 多元关系', '', '参与数值关系计算的变量：'+', '.join(map(cell, profile.relations.columns)), '',
              f'完整有限观测数：{profile.relations.complete_rows}；中心化矩阵秩：{cell(profile.relations.centered_rank)}。', '',
              '相关、协方差、分位数、偏度、峰度、缺失模式与逐字段证据详见 profile.json。', '',
              '## 未知条件与解释边界', '']
    lines += ['- '+item for item in profile.unknowns+profile.quality.warnings]
    lines += ['', '本次仅生成数据画像，没有执行统计分析或调用外部模型。', '']
    return '\n'.join(lines)


def profile_dataset(input_path, output_root, *, goal='数据探索与质量检查', sheet=0, **roles):
    frame, source = read_table(Path(input_path), sheet)
    task = TaskUnderstandingAgent().run(goal, **roles)
    validator = ProfileValidationAgent()
    validator.validate_roles(frame, task)
    variables = StructureAgent().run(frame, source)
    relations = RelationsAgent().run(frame, task)
    profile = validator.run(frame, source, task, variables, relations)
    folder = Path(output_root)/uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    payloads = {'task': task.model_dump(mode='json'), 'profile': profile.model_dump(mode='json'),
                'run': {'status': 'profiled', 'application_version': __version__,
                        'created_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': source.sha256,
                        'api_calls': 0, 'analysis_executed': False}}
    for name, payload in payloads.items():
        (folder/(name+'.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (folder/'report.md').write_text(render_profile(profile), encoding='utf-8')
    return folder
