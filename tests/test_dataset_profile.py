import json

from stat_agent.cli import main
from stat_agent.dataset_profile import profile_dataset


def test_dataset_only_cli_needs_no_analysis_goal_or_model(examples, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Dataset-only profiling must not invoke a model or analysis pipeline.')
    monkeypatch.setattr('stat_agent.llm.DeepSeekClient.structured', forbidden)
    monkeypatch.setattr('stat_agent.cli.run_pipeline', forbidden)
    assert main(['profile', str(examples/'pca.csv'), '--out', str(tmp_path)]) == 0
    folder = next(p for p in tmp_path.iterdir() if p.is_dir())
    profile = json.loads((folder/'profile.json').read_text(encoding='utf-8'))
    run = json.loads((folder/'run.json').read_text(encoding='utf-8'))
    assert profile['structure']['n'] == 8 and profile['variables'][0]['mean'] == 4.5
    assert profile['design']['independence'] == 'unknown'
    assert run['api_calls'] == 0 and not run['analysis_executed']
    assert not (folder/'execution.json').exists()
    assert (folder/'report.md').exists()


def test_profile_retains_explicit_variable_roles(examples, tmp_path):
    folder = profile_dataset(examples/'regression.csv', tmp_path, targets=['y'], predictors=['x1','x2'])
    profile = json.loads((folder/'profile.json').read_text(encoding='utf-8'))
    assert profile['relations']['columns'] == ['x1','x2']
    assert profile['design']['response_types'] == {'y':'numeric'}
