"""Whole application workflow, using only the isolated fixture database."""
import sys
from pathlib import Path
from alembic import command
from sqlalchemy import inspect, text
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from validation.journey import journey


def test_integrated_workflow_and_idempotent_upgrade_preserves_all_rows(api):
    client, session, config = api
    result = journey(client, {role: (role, 'test-password-123') for role in ('administrador', 'analista', 'observador')})
    # Snapshot every table AFTER actual experiments, ML, evidence and exports exist.
    with session() as db:
        tables = sorted(inspect(db.connection()).get_table_names())
        before = {table: sorted([tuple(row) for row in db.execute(text(f'SELECT * FROM {table}'))], key=repr) for table in tables}
    command.upgrade(config, 'head')
    with session() as db:
        for table in tables:
            assert sorted([tuple(row) for row in db.execute(text(f'SELECT * FROM {table}'))], key=repr) == before[table]
    assert result['counts'] == {'events': 6, 'incidents': 4}


def test_concurrent_transition_and_action_share_revision_guard(api, headers, batch):
    client, _, _ = api
    admin = headers('administrador')
    assert client.post('/api/events/import', json={'events': [batch['events'][0]]}, headers=admin).status_code == 200
    incident = client.get('/api/incidents', headers=admin).json()[0]
    path = '/api/incidents/'+incident['id']
    uid = client.get('/api/auth/me', headers=admin).json()['id']
    assigned = client.patch(path+'/assignment', headers=admin, json={'assigned_to_id': uid,
        'expected_revision': incident['revision'], 'justification': 'Synthetic concurrency fixture'}).json()
    analyzing = client.patch(path+'/status', headers=admin, json={'status': 'En análisis',
        'expected_revision': assigned['revision'], 'justification': 'Synthetic concurrency fixture'}).json()
    barrier = Barrier(2)
    def mutate(action):
        barrier.wait(timeout=10)
        if action:
            return client.post(path+'/actions', headers=admin, json={'description': 'Concurrent synthetic action',
                'expected_revision': analyzing['revision']}).status_code
        return client.patch(path+'/status', headers=admin, json={'status': 'En respuesta',
            'expected_revision': analyzing['revision'], 'justification': 'Concurrent synthetic transition'}).status_code
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(mutate, [True, False]))
    assert statuses in ([201, 409], [409, 200])
    current = client.get(path, headers=admin).json()
    assert current['revision'] == analyzing['revision']+1
    assert len(client.get(path+'/actions', headers=admin).json()) == (1 if statuses[0] == 201 else 0)
