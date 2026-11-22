"""Shared assertions for isolated ASGI and real TCP validation. No credentials exported."""
import hashlib
import json

PERIOD = {'start': '2026-01-01T00:00:00Z', 'end': '2026-01-02T00:00:00Z', 'time_basis': 'event_timestamp'}


def journey(client, credentials):
    checks = []

    def call(method, path, expected=200, role='administrador', **kwargs):
        headers = dict(tokens.get(role, {}))
        if 'content' in kwargs: headers['Content-Type'] = 'application/x-ndjson'
        response = client.request(method, path, headers=headers, **kwargs)
        assert response.status_code == expected, f'{method} {path}: HTTP {response.status_code}, expected {expected}'
        checks.append({'method': method, 'path': path, 'status': response.status_code})
        return response

    tokens = {}
    users = {}
    for role, (username, password) in credentials.items():
        result = call('POST', '/api/auth/login', role=None, json={'username': username, 'password': password}).json()
        tokens[role] = {'Authorization': 'Bearer '+result['access_token']}
        users[role] = call('GET', '/api/auth/me', role=role).json()['id']
    call('GET', '/api/incidents', expected=401, role=None)
    event = {'source': 'ITER10-SYNTHETIC', 'event_timestamp': '2026-01-01T00:01:00Z',
             'source_ip': '192.0.2.1', 'destination_ip': '198.51.100.1', 'event_type': 'dos',
             'severity': 10, 'asset_criticality': 10, 'message': 'Synthetic integral validation'}
    batch = {'events': [event, {**event, 'event_timestamp': '2026-01-01T00:02:00Z'},
                        {**event, 'event_timestamp': '2026-01-01T00:16:00Z'},
                        {**event, 'source_ip': '192.0.2.2'}]}
    call('POST', '/api/events/import', 403, role='observador', json=batch)
    assert call('POST', '/api/events/import', role='analista', json=batch).json()['imported'] == 4
    assert call('POST', '/api/events/import', json=batch).json()['duplicates'] == 4
    incidents = call('GET', '/api/incidents').json()
    assert len(incidents) == 3
    iid = next(i['id'] for i in incidents if i['event_count'] == 2)
    path = '/api/incidents/'+iid

    def detail(): return call('GET', path).json()
    first = detail()
    assert first['explanation']['algorithm_version'] == 'weighted-v2'
    assert sum(f['contribution'] for f in first['explanation']['factors'].values()) == first['explanation']['unrounded_score']
    eve = {'timestamp': '2025-12-31T18:03:00-06:00', 'event_type': 'alert', 'src_ip': '203.0.113.1',
           'dest_ip': '203.0.113.2', 'src_port': 51000, 'dest_port': 443, 'proto': 'TCP',
           'alert': {'signature': 'ITER10 SYNTHETIC ONLY', 'signature_id': 1000010, 'category': 'trojan-activity', 'severity': 2}}
    eve_path = '/api/events/import/eve?filename=synthetic.eve.jsonl&sensor_id=iter10'
    body = (json.dumps(eve)+'\n{invalid\n').encode()
    result = call('POST', eve_path, role='analista', content=body).json()
    assert result['imported'] == 1 and result['errors']
    assert call('POST', eve_path, content=(json.dumps(eve)+'\n').encode()).json()['duplicates'] == 1
    eve_inc = next(i for i in call('GET', '/api/incidents').json() if i['event_type'] == 'malware')
    eid = call('GET', '/api/incidents/'+eve_inc['id']).json()['events'][0]['id']
    evidence = call('GET', '/api/events/'+eid+'/evidence').json()
    assert evidence  # Original plus both appearances are independently tested by test_suricata.

    rev = first['revision']
    assignment = {'assigned_to_id': users['analista'], 'justification': 'Synthetic E2E assignment', 'expected_revision': rev}
    assert call('PATCH', path+'/assignment', json=assignment).json()['status'] == 'Asignado'
    call('PATCH', path+'/assignment', expected=409, json=assignment)
    for status in ('En análisis', 'En respuesta', 'Resuelto', 'Cerrado'):
        current = detail()
        if status == 'Resuelto':
            action = {'description': 'Synthetic response record; executes no commands', 'category': 'contencion',
                      'expected_revision': current['revision']}
            call('POST', path+'/actions', expected=201, role='analista', json=action)
            call('POST', path+'/actions', expected=409, role='analista', json=action)
        call('PATCH', path+'/status', role='analista', json={'status': status, 'justification': 'Synthetic E2E transition',
                                                          'expected_revision': detail()['revision']})
    frozen = detail()
    evaluations = call('GET', path+'/evaluations').json()
    late = {**event, 'severity': 100, 'asset_criticality': 100, 'message': 'Synthetic new evidence received after closure'}
    assert call('POST', '/api/events/import', json={'events': [late]}).json()['imported'] == 1
    closed = detail()
    assert closed['status'] == 'Cerrado' and closed['needs_review'] and closed['score'] == frozen['score']
    assert call('GET', path+'/evaluations').json() == evaluations
    call('PATCH', path+'/status', json={'status': 'En análisis', 'justification': 'Explicit synthetic reopening', 'expected_revision': closed['revision']})
    call('POST', path+'/reevaluate', expected=201, role='analista', json={'justification': 'Review synthetic closed evidence', 'expected_revision': detail()['revision']})
    assert call('GET', path+'/evaluations').json()[:-1] == evaluations
    assert detail()['score'] > frozen['score'] and not detail()['risk_reevaluation_pending']
    timeline = call('GET', path+'/timeline').json()
    assert {'state', 'assignment', 'action', 'review_signal', 'risk_reassessment'}.issubset({r['kind'] for r in timeline})
    life = call('GET', path+'/lifecycle', role='observador').json()
    for name in ('mttd', 'mttr'):
        assert life['metrics'][name]['value'] is None and life['metrics'][name]['reason']

    filters = {**PERIOD, 'event_type': 'dos', 'status': 'En análisis', 'assignee': users['analista'], 'source': event['source']}
    dash = call('GET', '/api/analytics/dashboard', role='observador', params=filters).json()
    assert dash['totals']['incidents'] == 1 and dash['totals']['events'] == 3
    report = call('POST', '/api/analytics/reports', expected=201, json=filters).json()
    exports = {}
    for fmt in ('json', 'csv', 'pdf'):
        response = call('GET', '/api/analytics/reports/'+report['id'], role='observador', params={'format': fmt})
        assert all(s not in response.content for s in (b'password_hash', b'Bearer ', b'access_token', b'Synthetic new evidence'))
        if fmt == 'pdf': assert response.content.startswith(b'%PDF')
        exports[fmt] = hashlib.sha256(response.content).hexdigest()
    did = call('POST', '/api/evaluation/datasets/synthetic', expected=201, json={'seed': 202610, 'count': 60}).json()['id']
    experiment = call('POST', '/api/evaluation/experiments', expected=201, json={'dataset_id': did, 'budget': 10}).json()
    assert 'results' not in call('GET', '/api/evaluation/experiments/'+experiment['id'], role='observador').json()
    ml_dataset = call('POST', '/api/ml/datasets/laboratory', expected=201, json={'seed': 202606, 'groups': 96}).json()['id']
    run = call('POST', '/api/ml/train', expected=201, json={'dataset_id': ml_dataset, 'seed': 202606, 'budget': 10}).json()
    assert run['status'] == 'completed' and {'logistic', 'forest', 'weighted-v2'}.issubset(run['results'])
    case = call('GET', '/api/evaluation/datasets/'+ml_dataset+'/cases', role='observador').json()[0]
    prediction = call('POST', '/api/ml/runs/'+run['id']+'/predict', role='observador', json=case).json()
    assert abs(sum(prediction['probabilities'].values())-1) < 1e-9 and prediction['uncalibrated']
    call('POST', '/api/ml/train', expected=403, role='analista', json={'dataset_id': ml_dataset})
    call('GET', '/api/analytics/comparisons')
    malformed = call('POST', '/api/auth/login', expected=422, role=None, json={'username': 'missing', 'password': 'ITER10-DO-NOT-ECHO'*20})
    assert 'ITER10-DO-NOT-ECHO' not in malformed.text
    return {'data_kind': 'synthetic', 'checks': checks, 'incident_id': iid, 'report_id': report['id'],
            'experiment_id': experiment['id'], 'ml_run_id': run['id'], 'export_sha256': exports,
            'counts': {'events': 6, 'incidents': 4}, 'mttd': 'No calculable', 'mttr': 'No calculable'}
