import io
import json
import sqlite3
import urllib.error

import pytest
from pydantic import SecretStr

from stat_agent.llm import DeepSeekClient, DeepSeekConfig, DeepSeekTaskAgent, LLMError, load_ccswitch
from stat_agent.pipeline import run_pipeline


def config():
    return DeepSeekConfig(base_url='https://api.deepseek.com/anthropic', configured_model='deepseek-v4-pro[1m]', api_key=SecretStr('test-secret'))


def task(**changes):
    result = dict(task_type='regression', requested_method='stats::lm', target_variables=['y'],
                  predictor_variables=['x1', 'x2'], group_variables=[], expected_output=['coefficients'], constraints=[], unknowns=[])
    result.update(changes)
    return result


def transport(payload, captures=None, stop_reason='tool_use'):
    def send(request, **kwargs):
        if captures is not None:
            captures.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'model': 'deepseek-v4-pro', 'stop_reason': stop_reason,
            'content': [{'type': 'tool_use', 'name': 'emit_profile', 'input': payload}],
            'usage': {'input_tokens': 100, 'output_tokens': 20, 'cache_read_input_tokens': 10}}).encode())
    return send


def test_ccswitch_readonly_selection_and_secret(tmp_path):
    database = tmp_path / 'providers.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE providers(name TEXT, app_type TEXT, settings_config TEXT, is_current INTEGER)')
        env = {'ANTHROPIC_BASE_URL': 'https://api.deepseek.com/anthropic', 'ANTHROPIC_AUTH_TOKEN': 'test-secret', 'ANTHROPIC_MODEL': 'deepseek-v4-pro[1m]'}
        db.execute('INSERT INTO providers VALUES (?,?,?,?)', ('DeepSeek', 'claude', json.dumps({'env': env}), 1))
    before = database.read_bytes()
    loaded = load_ccswitch(database)
    assert loaded.request_model == 'deepseek-v4-pro'
    assert 'test-secret' not in loaded.model_dump_json()
    assert database.read_bytes() == before


def test_structured_roles_evidence_usage_and_no_raw_rows():
    captures = []
    client = DeepSeekClient(config(), transport=transport(task(), captures))
    result = DeepSeekTaskAgent(client).run('用 x1 和 x2 解释 y', columns=['x1', 'x2', 'y'])
    assert result.target_variables == ['y']
    assert result.evidence['target_variables'].origin == 'llm_inference'
    assert result.evidence['target_variables'].status == 'unverified'
    assert client.usage['tokens'] == 130
    assert client.usage['api_calls'] == 1
    assert 'test-secret' not in json.dumps(client.metadata())
    assert set(json.loads(captures[0]['messages'][0]['content'])) == {'goal', 'columns', 'available_methods', 'explicit_roles'}


@pytest.mark.parametrize('changes', [dict(predictor_variables=['absent']), dict(predictor_variables=['y']),
                                     dict(requested_method='invented::fn'), dict(requested_method='stats::prcomp')])
def test_invalid_model_roles_or_method_are_rejected(changes):
    agent = DeepSeekTaskAgent(DeepSeekClient(config(), transport=transport(task(**changes))))
    with pytest.raises(LLMError):
        agent.run('linear regression', columns=['x1', 'x2', 'y'])


def test_truncated_tool_output_rejected():
    client = DeepSeekClient(config(), transport=transport(task(), stop_reason='max_tokens'))
    with pytest.raises(LLMError, match='complete structured'):
        DeepSeekTaskAgent(client).run('regression', columns=['x1', 'x2', 'y'])


def test_http_error_sanitized_and_retry_bounded(monkeypatch):
    monkeypatch.setattr('stat_agent.llm.time.sleep', lambda _: None)
    def fail(request, **kwargs):
        raise urllib.error.HTTPError('https://example.invalid', 429, 'test-secret', {}, io.BytesIO(b'test-secret'))
    client = DeepSeekClient(config(), transport=fail, max_retries=1)
    with pytest.raises(LLMError) as exc:
        client.structured('system', {}, {})
    assert 'test-secret' not in str(exc.value)
    assert client.usage['api_calls'] == 2 and client.usage['retries'] == 1


def test_llm_pipeline_usage_is_per_run(examples, tmp_path):
    agent = DeepSeekTaskAgent(DeepSeekClient(config(), transport=transport(task())))
    for _ in range(2):
        folder = run_pipeline(examples / 'regression.csv', 'linear regression', tmp_path, task_agent=agent)
        run = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
        assert run['status'] == 'success'
        assert run['usage']['api_calls'] == 1
        assert run['usage']['api_cost_usd'] is None
        assert len(run['llm']['receipts']) == 1
        assert 'test-secret' not in (folder / 'run.json').read_text(encoding='utf-8')


@pytest.mark.parametrize('envelope', [[], {'usage': None}, {'content': [None]}, {'content': 'bad'}])
def test_malformed_envelopes_fail_with_sanitized_error(envelope):
    client = DeepSeekClient(config(), transport=lambda *a, **k: io.BytesIO(json.dumps(envelope).encode()))
    with pytest.raises(LLMError):
        client.structured('system', {}, {})
