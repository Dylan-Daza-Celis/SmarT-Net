from datetime import datetime, timedelta, timezone
import jwt
import pytest
from sqlalchemy import select, text
from alembic import command
from app import security
from app.models import User, IncidentHistory


def test_authentication(api, headers):
    client, session, _ = api
    assert client.get("/health").status_code == 200
    for path in ("/api/incidents", "/api/stats", "/api/users", "/api/auth/me", "/api/incidents/missing", "/api/incidents/missing/history", "/api/incidents/missing/actions"):
        assert client.get(path).status_code == 401
    assert client.post("/api/auth/login", json={"username":"administrador", "password":"wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username":"missing", "password":"wrong"}).status_code == 401
    assert client.get("/api/auth/me", headers=headers("analista")).json()["role"] == "analista"
    with session() as db:
        assert db.scalar(select(User)).password_hash.startswith("$argon2id$")
    h = headers("administrador")
    token = h["Authorization"].split()[1]
    claims = jwt.decode(token, security.JWT_SECRET, algorithms=["HS256"], audience="smartir-api", issuer="smartir-net")
    assert claims["exp"] - claims["iat"] == 900
    claims["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = jwt.encode(claims, security.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/incidents", headers={"Authorization":"Bearer " + expired}).status_code == 401
    forged = jwt.encode(claims, "wrong-key" * 8, algorithm="HS256")
    assert client.get("/api/incidents", headers={"Authorization":"Bearer " + forged}).status_code == 401
    assert client.get("/api/incidents", headers={"Authorization":"Bearer garbage"}).status_code == 401


def test_user_management_and_live_permissions(api, headers):
    client, _, _ = api
    admin, analyst = headers("administrador"), headers("analista")
    data = {"username":"newuser", "password":"long-password-123", "role":"observador"}
    assert client.post("/api/users", json=data, headers=analyst).status_code == 403
    response = client.post("/api/users", json=data, headers=admin)
    assert response.status_code == 201
    assert "password_hash" not in response.json()
    uid = response.json()["id"]
    assert client.post("/api/users", json=data, headers=admin).status_code == 409
    assert client.post("/api/users", json={**data,"role":"root"}, headers=admin).status_code == 422
    assert client.get("/api/users", headers=analyst).status_code == 403
    login = client.post("/api/auth/login",json={"username":"newuser","password":data["password"]}).json()
    h = {"Authorization":"Bearer " + login["access_token"]}
    assert client.get("/api/users",headers=h).status_code == 403
    assert client.patch(f"/api/users/{uid}",json={"role":"administrador"},headers=admin).status_code == 200
    assert client.get("/api/users",headers=h).status_code == 200
    assert client.patch(f"/api/users/{uid}",json={"active":False},headers=admin).status_code == 200
    assert client.get("/api/incidents",headers=h).status_code == 401
    assert client.post("/api/auth/login",json={"username":"newuser","password":data["password"]}).status_code == 401


@pytest.mark.parametrize("role", ["administrador", "analista", "observador"])
def test_permissions_import_status_actions(api, headers, batch, role):
    client, _, _ = api
    h = headers(role)
    assert client.post("/api/events/import", json=batch).status_code == 401
    assert client.post("/api/events/import",json=batch,headers=headers("analista")).status_code == 200
    iid = client.get("/api/incidents",headers=h).json()[0]["id"]
    for path in ("/api/incidents", "/api/stats", f"/api/incidents/{iid}", f"/api/incidents/{iid}/history", f"/api/incidents/{iid}/actions"):
        assert client.get(path,headers=h).status_code == 200
    allowed = role != "observador"
    assert client.post("/api/events/import",json=batch,headers=h).status_code == (200 if allowed else 403)
    assert client.patch(f"/api/incidents/{iid}/status",json={"status":"Asignado","justification":"Revisión inicial"},headers=h).status_code == (200 if allowed else 403)
    assert client.post(f"/api/incidents/{iid}/actions",json={"description":"Aislar equipo"},headers=h).status_code == (201 if allowed else 403)


def test_import_deduplication_and_validation(api, headers, batch):
    client, _, _ = api
    h = headers("analista")
    response = client.post("/api/events/import",json=batch,headers=h)
    assert response.json() == {"imported":4,"duplicates":0,"incidents_updated":4}
    assert client.post("/api/events/import",json=batch,headers=h).json() == {"imported":0,"duplicates":4,"incidents_updated":0}
    assert client.get("/api/stats",headers=h).json()["events"] == 4
    assert client.post("/api/events/import",json={"events":[]},headers=h).status_code == 422
    invalid = {**batch["events"][0],"severity":101}
    assert client.post("/api/events/import",json={"events":[invalid]},headers=h).status_code == 422
    naive = {**batch["events"][0],"event_timestamp":"2026-01-01T12:00:00"}
    assert client.post("/api/events/import",json={"events":[naive]},headers=h).status_code == 422
    assert client.get("/api/stats",headers=h).json()["events"] == 4


def test_status_audit_and_actions(api, headers, batch):
    client, session, _ = api
    h = headers("analista")
    client.post("/api/events/import",json=batch,headers=h)
    iid = client.get("/api/incidents",headers=h).json()[0]["id"]
    path = f"/api/incidents/{iid}"
    for state in ("Asignado","En análisis","En respuesta","Resuelto","Cerrado","Nuevo"):
        assert client.patch(path+"/status",json={"status":state,"justification":"Motivo documentado"},headers=h).status_code == 200
    assert client.patch(path+"/status",json={"status":"Nuevo","justification":"Duplicado"},headers=h).status_code == 409
    assert client.patch(path+"/status",json={"status":"Inválido","justification":"Motivo"},headers=h).status_code == 422
    assert client.patch(path+"/status",json={"status":"Cerrado","justification":"   "},headers=h).status_code == 422
    history = client.get(path+"/history",headers=h).json()
    assert len(history) == 7
    assert history[-1]["previous_status"] == "Cerrado"
    assert all(row["author"] == "analista" and row["author_id"] and row["created_at"] and row["justification"] for row in history)
    with session() as db:
        assert len(db.scalars(select(IncidentHistory).where(IncidentHistory.incident_id==iid)).all()) == 7
    assert client.post(path+"/actions",json={"description":"Bloqueo de IP"},headers=h).status_code == 201
    assert client.post(path+"/actions",json={"description":" "},headers=h).status_code == 422
    assert client.get(path+"/actions",headers=h).json()[0]["author"] == "analista"
    assert client.patch("/api/incidents/missing/status",json={"status":"Cerrado","justification":"Motivo"},headers=h).status_code == 404


@pytest.mark.parametrize("api", ["0002"], indirect=True)
def test_migration_preserves_legacy_data(api):
    _, session, config = api
    # Base con tablas originales, sin control Alembic ni tablas nuevas.
    with session.begin() as db:
        for table in ("incident_history", "response_actions", "users", "alembic_version"):
            db.execute(text(f"DROP TABLE {table}"))
        db.execute(text("INSERT INTO incidents (id,correlation_key,event_type,status,score,priority,explanation,created_at) VALUES ('legacy','legacy-key','dos','Nuevo',10,'Baja','{}',CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO events (id,fingerprint,source,event_timestamp,received_at,event_type,severity,asset_criticality,message,raw_event,incident_id) VALUES ('old-event','old-fingerprint','legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'dos',10,10,'legacy','{}','legacy')"))
    command.upgrade(config,"head")
    command.upgrade(config,"head")
    with session() as db:
        assert db.execute(text("SELECT status FROM incidents WHERE id='legacy'")).scalar() == "Nuevo"
        assert db.execute(text("SELECT incident_id FROM events WHERE id='old-event'")).scalar() == "legacy"
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0005"
