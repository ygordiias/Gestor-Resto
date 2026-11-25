"""Item 7: CORS restrito por CORS_ORIGINS e Socket.IO com token, salas por
perfil e sem dados pessoais de clientes para quem não deve recebê-los.

Teste OFFLINE: sem servidor, sem rede e sem MongoDB. Usa o socketio.AsyncServer
real do app; só a camada de transporte (engine.io) é trocada por uma falsa que
guarda os pacotes enviados a cada conexão.
Rodar: cd backend && python -m pytest tests/test_cors_socket.py
"""
import asyncio
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import socketio
from jose import jwt

from _offline_app import call, server, token_for
from bootstrap import require_cors_origins
from test_user_management import FakeUsers

ALLOWED = "http://frontend-teste.example"
OTHER = "https://site-estranho.example"


# =================================================================== CORS_ORIGINS
@pytest.mark.parametrize(
    "env",
    [{}, {"CORS_ORIGINS": ""}, {"CORS_ORIGINS": "  , ,"}, {"CORS_ORIGINS": "*"},
     {"CORS_ORIGINS": "https://a.example,*"}, {"CORS_ORIGINS": "a.example"},
     {"CORS_ORIGINS": "ftp://a.example"}, {"CORS_ORIGINS": "https://"}],
    ids=["ausente", "vazia", "so-virgulas", "asterisco", "asterisco-na-lista",
         "sem-esquema", "ftp", "so-esquema"],
)
def test_invalid_cors_origins_stops_server(env, capsys):
    with pytest.raises(SystemExit) as exc:
        require_cors_origins(env)
    assert exc.value.code == 1
    assert "CORS_ORIGINS" in capsys.readouterr().err


def test_cors_origins_are_cleaned():
    env = {"CORS_ORIGINS": " https://a.example/ ,http://localhost:3000,,https://a.example"}
    assert require_cors_origins(env) == ["https://a.example", "http://localhost:3000"]


def test_app_and_socket_use_the_same_list():
    assert server.CORS_ORIGINS == [ALLOWED, "http://localhost:3000"]
    assert server.sio.eio.cors_allowed_origins == server.CORS_ORIGINS


def test_socket_loggers_are_off():
    # Os loggers do Socket.IO gravavam o conteúdo das mensagens (dados de clientes).
    src = Path(server.__file__).read_text(encoding="utf-8")
    bloco = src[src.index("sio = socketio.AsyncServer("):]
    bloco = bloco[:bloco.index(")") + 1]
    assert "logger=False" in bloco and "engineio_logger=False" in bloco


def _preflight(origin):
    return call("OPTIONS", "/api/auth/login", with_headers=True, headers={
        "origin": origin, "access-control-request-method": "POST",
        "access-control-request-headers": "content-type,authorization"})


def test_preflight_allowed_origin():
    status, _, headers = _preflight(ALLOWED)
    assert status == 200
    assert headers.get("access-control-allow-origin") == ALLOWED
    assert "access-control-allow-credentials" not in headers


def test_preflight_other_origin_refused():
    status, _, headers = _preflight(OTHER)
    assert status == 400
    assert "access-control-allow-origin" not in headers


def test_simple_request_headers_by_origin():
    _, body, headers = call("GET", "/api/ping", with_headers=True, headers={"origin": ALLOWED})
    assert headers.get("access-control-allow-origin") == ALLOWED
    _, _, headers = call("GET", "/api/ping", with_headers=True, headers={"origin": OTHER})
    assert "access-control-allow-origin" not in headers


def test_ping_announces_socket_auth():
    status, body = call("GET", "/api/ping")
    assert status == 200 and body["socket_auth"] is True


# =================================================================== Socket.IO
class FakeTables:
    def __init__(self, docs):
        self.docs = docs
        self.writes = []

    async def update_one(self, query, update):
        self.writes.append((query, update))
        for d in self.docs:
            if d["id"] == query.get("id"):
                d.update(update.get("$set", {}))

    def find(self, query=None, projection=None):
        docs = [copy.deepcopy(d) for d in self.docs]

        class _Cursor:
            async def to_list(self, n):
                return docs[:n]
        return _Cursor()


class FakeDB:
    def __init__(self, users, tables):
        self.users = FakeUsers(users)
        self.tables = FakeTables(tables)


ROLES = ("superadmin", "admin", "cashier", "waiter", "kitchen", "bar")


def _u(uid, role, active=True):
    return {"id": uid, "name": uid, "email": f"{uid}@example.invalid", "role": role,
            "is_active": active, "password": "x"}


@pytest.fixture
def db(monkeypatch):
    users = [_u(r, r) for r in ROLES] + [_u("inativo", "waiter", active=False),
                                         _u("estranho", "cliente")]
    fake = FakeDB(users, [{"id": "mesa-1", "number": 1, "status": "occupied"}])
    monkeypatch.setattr(server, "db", fake)
    return fake


class Wire:
    """Transporte falso: guarda o que o servidor manda para cada conexão."""

    def __init__(self, sio, monkeypatch):
        self.sio = sio
        self.out = {}        # eio_sid -> [(tipo, dados)]
        self.sessions = {}   # eio_sid -> sessão engine.io
        self.n = 0
        manager = socketio.AsyncManager()
        manager.set_server(sio)
        manager.initialize()
        monkeypatch.setattr(sio, "manager", manager)
        monkeypatch.setattr(sio, "manager_initialized", True)
        monkeypatch.setattr(sio, "environ", {})
        monkeypatch.setattr(sio, "_send_packet", self._send_packet)
        monkeypatch.setattr(sio, "_send_eio_packet", self._send_eio_packet)

        async def get_session(eio_sid):
            return self.sessions.setdefault(eio_sid, {})
        monkeypatch.setattr(sio.eio, "get_session", get_session)

    async def _send_packet(self, eio_sid, pkt):
        self.out.setdefault(eio_sid, []).append((pkt.packet_type, pkt.data))

    async def _send_eio_packet(self, eio_sid, eio_pkt):
        raw = eio_pkt.data
        m = re.match(r"(\d)(.*)", raw, re.S)
        self.out.setdefault(eio_sid, []).append((int(m.group(1)), json.loads(m.group(2))))

    def connect(self, auth):
        self.n += 1
        eio_sid = f"eio-{self.n}"
        self.sio.environ[eio_sid] = {}
        asyncio.run(self.sio._handle_connect(eio_sid, "/", auth))
        return eio_sid

    def sid(self, eio_sid):
        return self.sio.manager.sid_from_eio_sid(eio_sid, "/")

    def accepted(self, eio_sid):
        return any(t == socketio.packet.CONNECT for t, _ in self.out.get(eio_sid, []))

    def refused(self, eio_sid):
        return any(t == socketio.packet.CONNECT_ERROR for t, _ in self.out.get(eio_sid, []))

    def events(self, eio_sid, name):
        return [d[1] for t, d in self.out.get(eio_sid, [])
                if t == socketio.packet.EVENT and d and d[0] == name]

    def rooms(self, eio_sid):
        sid = self.sid(eio_sid)
        return set(self.sio.manager.get_rooms(sid, "/")) - {sid} if sid else set()

    def run(self, coro):
        return asyncio.run(coro)


@pytest.fixture
def wire(monkeypatch, db):
    return Wire(server.sio, monkeypatch)


def _tok(uid):
    return {"token": token_for(uid)}


def _expired(uid):
    exp = datetime.now(timezone.utc) - timedelta(minutes=1)
    return {"token": jwt.encode({"sub": uid, "exp": exp}, server.SECRET_KEY, algorithm=server.ALGORITHM)}


def _other_key(uid):
    return {"token": jwt.encode({"sub": uid}, "outra-chave-" + "x" * 40, algorithm=server.ALGORITHM)}


# ------------------------------------------------------------- conexão
@pytest.mark.parametrize("auth", [
    None, {}, {"token": ""}, {"token": 123}, "texto", {"token": "nao-e-jwt"},
    "expirado", "outra-chave", "sem-sub", "inexistente", "inativo", "perfil-desconhecido",
])
def test_connection_without_valid_token_is_refused(wire, auth):
    auth = {
        "expirado": _expired("admin"),
        "outra-chave": _other_key("admin"),
        "sem-sub": {"token": jwt.encode({"x": 1}, server.SECRET_KEY, algorithm=server.ALGORITHM)},
        "inexistente": _tok("ninguem"),
        "inativo": _tok("inativo"),
        "perfil-desconhecido": _tok("estranho"),
    }.get(auth, auth) if isinstance(auth, str) else auth
    e = wire.connect(auth)
    assert wire.refused(e) and not wire.accepted(e)
    assert e not in wire.sio.manager.eio_to_sid
    err = next(d for t, d in wire.out[e] if t == socketio.packet.CONNECT_ERROR)
    assert err.get("message") == "unauthorized"


@pytest.mark.parametrize("role", ROLES)
def test_valid_token_joins_server_rooms(wire, role):
    e = wire.connect(_tok(role))
    assert wire.accepted(e)
    assert wire.rooms(e) == {"staff", f"role:{role}", f"user:{role}"}


def test_browser_cannot_choose_rooms(wire):
    e = wire.connect(_tok("kitchen"))
    sid = wire.sid(e)
    wire.run(server.join_room(sid, {"room": "role:admin"}))
    wire.run(server.leave_room(sid, {"room": "staff"}))
    assert wire.rooms(e) == {"staff", "role:kitchen", "user:kitchen"}


# ------------------------------------------------------------- dados pessoais
ORDER = {
    "id": "o1", "order_code": "EM-0001", "source": "online", "status": "pending",
    "customer_name": "Maria  da Silva", "customer_phone": "11999990000",
    "address": "Rua X, 10", "change_for": 50, "total": 30.0,
    "items": [{"id": "i1", "product_name": "Lanche", "status": "pending"}],
}


@pytest.fixture
def everyone(wire):
    conns = {r: wire.connect(_tok(r)) for r in ROLES}
    conns["recusado"] = wire.connect({"token": "nao-e-jwt"})
    return conns


@pytest.mark.parametrize("event", ["kitchen_update", "bar_update"])
def test_order_lists_hide_customer_data_from_kitchen_bar_waiter(wire, everyone, event):
    original = copy.deepcopy(ORDER)
    wire.run(server.emit_orders(event, [ORDER]))
    assert ORDER == original  # não altera o objeto usado pelo resto do código
    for role in ("superadmin", "admin", "cashier"):
        assert wire.events(everyone[role], event) == [[ORDER]]
    for role in ("waiter", "kitchen", "bar"):
        (got,) = wire.events(everyone[role], event)
        o = got[0]
        assert "customer_phone" not in o and "address" not in o and "change_for" not in o
        assert o["customer_name"] == "Maria"
        assert o["items"] == ORDER["items"] and o["total"] == 30.0
    assert wire.events(everyone["recusado"], event) == []


@pytest.mark.parametrize("event", ["order_updated", "new_online_order"])
def test_single_order_events_hide_customer_data(wire, everyone, event):
    wire.run(server.emit_orders(event, ORDER))
    assert wire.events(everyone["cashier"], event) == [ORDER]
    (got,) = wire.events(everyone["kitchen"], event)
    assert "customer_phone" not in got and got["customer_name"] == "Maria"


def test_each_connection_gets_one_copy(wire, everyone):
    wire.run(server.emit_orders("order_updated", ORDER))
    for role in ROLES:
        assert len(wire.events(everyone[role], "order_updated")) == 1


def test_strip_customer_data_edge_cases():
    assert server.strip_customer_data({"id": "x"}) == {"id": "x"}
    assert server.strip_customer_data({"customer_name": "  "}) == {"customer_name": "  "}
    assert server.strip_customer_data({"customer_name": None}) == {"customer_name": None}
    assert server.strip_customer_data("texto") == "texto"


def test_stock_events_only_for_admins(wire, everyone):
    wire.run(server.emit_admins("stock_updated", [{"id": "s1", "unit_cost": 2.5}]))
    for role in ROLES:
        got = wire.events(everyone[role], "stock_updated")
        assert got == ([[{"id": "s1", "unit_cost": 2.5}]] if role in ("superadmin", "admin") else [])


def test_staff_events_reach_only_logged_users(wire, everyone):
    wire.run(server.emit_staff("order_closed", {"order_id": "o1"}))
    for role in ROLES:
        assert wire.events(everyone[role], "order_closed") == [{"order_id": "o1"}]
    assert wire.events(everyone["recusado"], "order_closed") == []


def test_every_emit_in_server_has_a_room():
    """Nenhum sio.emit sem sala: nada vai para 'todo mundo conectado'."""
    src = Path(server.__file__).read_text(encoding="utf-8")
    calls = re.findall(r"sio\.emit\((.*?)\)\s*$", src, re.M)
    assert calls, "esperava encontrar sio.emit"
    for c in calls:
        assert "room=" in c, c


# ------------------------------------------------------------- eventos do navegador
def test_item_ready_only_from_kitchen_bar_waiter_admin(wire, everyone):
    payload = {"tableNumber": 5, "productName": "Suco"}
    wire.run(server.item_ready(wire.sid(everyone["cashier"]), payload))
    assert all(wire.events(everyone[r], "waiter_notification") == [] for r in ROLES)
    wire.run(server.item_ready(wire.sid(everyone["kitchen"]), payload))
    for role in ROLES:
        (n,) = wire.events(everyone[role], "waiter_notification")
        assert n["tableNumber"] == 5


def test_item_ready_ignores_bad_payload(wire, everyone):
    wire.run(server.item_ready(wire.sid(everyone["kitchen"]), "lixo"))  # não quebra


def test_request_cleaning_needs_table_role(wire, everyone, db):
    data = {"tableId": "mesa-1", "tableNumber": 1}
    for role in ("kitchen", "bar"):
        wire.run(server.request_cleaning(wire.sid(everyone[role]), data))
    assert db.tables.writes == []
    wire.run(server.request_cleaning(wire.sid(everyone["waiter"]), data))
    assert db.tables.writes == [({"id": "mesa-1"}, {"$set": {"status": "cleaning"}})]
    (tables,) = wire.events(everyone["kitchen"], "tables_updated")
    assert tables[0]["status"] == "cleaning"


def test_unknown_sid_does_nothing(wire, db):
    wire.run(server.request_cleaning("sid-que-nao-existe", {"tableId": "mesa-1"}))
    assert db.tables.writes == []


# ------------------------------------------------------------- desativar / trocar perfil
def _disconnected(wire, e):
    return any(t == socketio.packet.DISCONNECT for t, _ in wire.out.get(e, [])) and \
        e not in wire.sio.manager.eio_to_sid


def test_deactivating_user_drops_their_sockets(wire, db):
    alvo1, alvo2 = wire.connect(_tok("waiter")), wire.connect(_tok("waiter"))
    outro = wire.connect(_tok("kitchen"))
    status, _ = call("DELETE", "/api/users/waiter", token=token_for("admin"))
    assert status == 200
    assert _disconnected(wire, alvo1) and _disconnected(wire, alvo2)
    assert not _disconnected(wire, outro)
    # e não consegue voltar
    assert wire.refused(wire.connect(_tok("waiter")))


def test_role_change_drops_sockets(wire, db):
    alvo = wire.connect(_tok("waiter"))
    status, _ = call("PUT", "/api/users/waiter", token=token_for("admin"), body={"role": "cashier"})
    assert status == 200 and _disconnected(wire, alvo)
    novo = wire.connect(_tok("waiter"))
    assert wire.rooms(novo) == {"staff", "role:cashier", "user:waiter"}


def test_name_change_keeps_sockets(wire, db):
    alvo = wire.connect(_tok("waiter"))
    status, _ = call("PUT", "/api/users/waiter", token=token_for("admin"), body={"name": "Novo Nome"})
    assert status == 200 and not _disconnected(wire, alvo)


def test_deactivate_via_put_drops_sockets(wire, db):
    alvo = wire.connect(_tok("waiter"))
    status, _ = call("PUT", "/api/users/waiter", token=token_for("admin"), body={"is_active": False})
    assert status == 200 and _disconnected(wire, alvo)
