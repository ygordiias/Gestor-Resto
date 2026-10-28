"""Gestor Resto - tarefas, histórico paginado de notas e relatórios por datas.

Módulo adicional; registra apenas rotas novas. Não modifica pagamentos,
fechamentos de caixa, estoque nem emissão fiscal.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import re
import uuid

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING

TZ = ZoneInfo('America/Sao_Paulo')
SECTORS = {'kitchen', 'bar', 'cashier', 'service', 'stock', 'purchasing', 'maintenance'}
STAFF_SECTOR = {'kitchen': 'kitchen', 'bar': 'bar', 'cashier': 'cashier', 'waiter': 'service'}
TASK_TYPES = {'cleaning', 'stock', 'expiry', 'oil_change', 'preparation', 'purchasing', 'maintenance', 'other'}
FREQUENCIES = {'once', 'daily', 'weekly', 'occurrence'}
PAYMENT_METHODS = {'cash', 'pix', 'credit', 'debit', 'card', 'voucher', 'platform'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def br_today():
    return datetime.now(TZ).date()


def as_cents(value):
    try:
        dec = Decimal(str(value or 0))
        if not dec.is_finite() or dec < 0 or dec > Decimal('1000000000'):
            raise ValueError
        return int((dec * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def reais(cents):
    return round(cents / 100, 2)


def parsed_day(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f'{field}: use AAAA-MM-DD')


def date_limits(start: str, end: str):
    first, last = parsed_day(start, 'Início'), parsed_day(end, 'Fim')
    if last < first:
        raise HTTPException(status_code=422, detail='Data final deve ser igual ou posterior à inicial')
    if (last - first).days > 365:
        raise HTTPException(status_code=422, detail='Selecione no máximo 366 dias por consulta')
    start_utc = datetime.combine(first, datetime.min.time(), tzinfo=TZ).astimezone(timezone.utc).isoformat()
    exclusive_utc = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=TZ).astimezone(timezone.utc).isoformat()
    return first, last, start_utc, exclusive_utc


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default='', max_length=500)
    sector: str
    task_type: str = 'other'
    frequency: str = 'once'
    due_on: str
    due_time: str = '20:00'
    assignee_id: str | None = None


class TaskEdit(TaskCreate):
    active: bool = True


class TaskNote(BaseModel):
    note: str = Field(default='', max_length=500)


def register_operational_routes(api_router, db, require_role, UserRole):
    admin = require_role([UserRole.ADMIN])
    staff = require_role([UserRole.ADMIN, UserRole.CASHIER, UserRole.KITCHEN, UserRole.BAR, UserRole.WAITER])

    def allowed(task, user):
        role = user.get('role')
        if role in ('admin', 'superadmin'):
            return True
        if STAFF_SECTOR.get(role) != task.get('sector'):
            return False
        assignee = task.get('assignee_id')
        return not assignee or assignee == user.get('id')

    async def validate_task_input(payload):
        if payload.sector not in SECTORS:
            raise HTTPException(status_code=422, detail='Setor inválido')
        if payload.task_type not in TASK_TYPES or payload.frequency not in FREQUENCIES:
            raise HTTPException(status_code=422, detail='Tipo ou frequência inválidos')
        parsed_day(payload.due_on, 'Vencimento')
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', payload.due_time):
            raise HTTPException(status_code=422, detail='Horário deve ser HH:MM')
        if payload.assignee_id:
            user = await db.users.find_one({'id': payload.assignee_id}, {'_id': 0, 'role': 1})
            if not user:
                raise HTTPException(status_code=422, detail='Responsável não encontrado')
            if user['role'] not in ('admin', 'superadmin') and STAFF_SECTOR.get(user['role']) != payload.sector:
                raise HTTPException(status_code=422, detail='Responsável não pertence ao setor da tarefa')

    def public_task(t):
        now = datetime.now(TZ)
        today = now.date().isoformat()
        due = t.get('due_on')
        late = due < today or (due == today and (t.get('due_time') or '23:59') < now.strftime('%H:%M'))
        return {k: v for k, v in t.items() if k not in ('_id', 'events')} | {
            'status': 'done' if t.get('completed') else ('inactive' if not t.get('active', True) else ('overdue' if late else 'pending')),
            'events_count': len(t.get('events', [])),
            'last_event': (t.get('events') or [None])[-1],
        }

    @api_router.get('/operations/assignees')
    async def task_assignees(current_user: dict = Depends(admin)):
        users = await db.users.find({'role': {'$in': ['superadmin', 'admin', 'waiter', 'cashier', 'kitchen', 'bar']}},
                                    {'_id': 0, 'id': 1, 'name': 1, 'role': 1}).sort('name', 1).to_list(300)
        return {'users': users}

    @api_router.get('/operations/tasks')
    async def list_tasks(sector: str = 'all', state: str = 'active', current_user: dict = Depends(staff)):
        if sector != 'all' and sector not in SECTORS:
            raise HTTPException(status_code=422, detail='Setor inválido')
        if state not in {'active', 'all', 'done'}:
            raise HTTPException(status_code=422, detail='Filtro inválido')
        qry = {}
        if state == 'active':
            qry = {'active': True, 'completed': False}
        if state == 'done':
            qry = {'completed': True}
        if sector != 'all':
            qry['sector'] = sector
        if current_user.get('role') not in ('admin', 'superadmin'):
            qry['sector'] = STAFF_SECTOR[current_user['role']]
            qry['$or'] = [{'assignee_id': None}, {'assignee_id': current_user['id']}, {'assignee_id': {'$exists': False}}]
        docs = await db.operational_tasks.find(qry, {'_id': 0}).sort([('due_on', ASCENDING), ('due_time', ASCENDING)]).to_list(1000)
        return {'tasks': [public_task(x) for x in docs], 'total': await db.operational_tasks.count_documents(qry), 'today': br_today().isoformat()}

    @api_router.post('/operations/tasks')
    async def create_task(data: TaskCreate, current_user: dict = Depends(admin)):
        await validate_task_input(data)
        record = {
            'id': str(uuid.uuid4()), 'title': data.title.strip(), 'description': data.description.strip(),
            'sector': data.sector, 'task_type': data.task_type, 'frequency': data.frequency,
            'due_on': data.due_on, 'due_time': data.due_time, 'assignee_id': data.assignee_id,
            'active': True, 'completed': False, 'completed_count': 0, 'events': [],
            'created_at': utc_now(), 'created_by': current_user.get('id'),
        }
        await db.operational_tasks.insert_one(record)
        return {'task': public_task(record)}

    @api_router.put('/operations/tasks/{task_id}')
    async def edit_task(task_id: str, data: TaskEdit, current_user: dict = Depends(admin)):
        await validate_task_input(data)
        t = await db.operational_tasks.find_one({'id': task_id}, {'_id': 0})
        if not t:
            raise HTTPException(status_code=404, detail='Tarefa não encontrada')
        # Sem apagar o histórico nem reabrir uma tarefa pontual já concluída.
        if t.get('completed') and data.active:
            raise HTTPException(status_code=409, detail='Tarefa concluída; crie uma nova para repetir')
        fields = {
            'title': data.title.strip(), 'description': data.description.strip(), 'sector': data.sector,
            'task_type': data.task_type, 'frequency': data.frequency, 'due_on': data.due_on,
            'due_time': data.due_time, 'assignee_id': data.assignee_id, 'active': data.active,
            'updated_at': utc_now(), 'updated_by': current_user.get('id'),
        }
        await db.operational_tasks.update_one({'id': task_id}, {'$set': fields})
        return {'message': 'Tarefa atualizada'}

    @api_router.post('/operations/tasks/{task_id}/complete')
    async def complete_task(task_id: str, data: TaskNote, current_user: dict = Depends(staff)):
        t = await db.operational_tasks.find_one({'id': task_id}, {'_id': 0})
        if not t:
            raise HTTPException(status_code=404, detail='Tarefa não encontrada')
        if not allowed(t, current_user):
            raise HTTPException(status_code=403, detail='Você não pode concluir tarefas de outro setor')
        if not t.get('active') or t.get('completed'):
            raise HTTPException(status_code=409, detail='Tarefa inativa ou já concluída')
        cycle = parsed_day(t.get('due_on'), 'Vencimento')
        freq = t.get('frequency')
        new_due = cycle + timedelta(days=1 if freq == 'daily' else 7) if freq in ('daily', 'weekly') else None
        event = {'id': str(uuid.uuid4()), 'action': 'completed', 'cycle_due_on': t['due_on'],
                 'at': utc_now(), 'by_id': current_user.get('id'), 'by_name': current_user.get('name'), 'note': data.note.strip()}
        changes = {'last_completed_at': event['at']}
        if new_due:
            # Se existirem dias atrasados, não os descarta: a próxima ocorrência permanece vencida.
            changes['due_on'] = new_due.isoformat()
        else:
            changes['completed'] = True
        result = await db.operational_tasks.update_one(
            {'id': task_id, 'active': True, 'completed': False, 'due_on': t['due_on']},
            {'$set': changes, '$inc': {'completed_count': 1}, '$push': {'events': event}}
        )
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail='Tarefa atualizada por outro operador. Atualize a tela')
        return {'message': 'Concluída; histórico registrado', 'next_due_on': new_due.isoformat() if new_due else None}

    @api_router.post('/operations/tasks/{task_id}/blocker')
    async def record_blocker(task_id: str, data: TaskNote, current_user: dict = Depends(staff)):
        if len(data.note.strip()) < 5:
            raise HTTPException(status_code=422, detail='Explique o motivo da pendência')
        t = await db.operational_tasks.find_one({'id': task_id}, {'_id': 0})
        if not t or not t.get('active') or t.get('completed'):
            raise HTTPException(status_code=404, detail='Tarefa não encontrada ou finalizada')
        if not allowed(t, current_user):
            raise HTTPException(status_code=403, detail='Sem acesso ao setor')
        event = {'id': str(uuid.uuid4()), 'action': 'blocker', 'cycle_due_on': t['due_on'],
                 'at': utc_now(), 'by_id': current_user.get('id'), 'by_name': current_user.get('name'), 'note': data.note.strip()}
        result = await db.operational_tasks.update_one({'id': task_id, 'active': True, 'completed': False, 'due_on': t['due_on']},
                                                        {'$push': {'events': event}})
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail='Tarefa alterada por outro operador')
        return {'message': 'Motivo registrado; tarefa continua pendente'}

    @api_router.get('/operations/tasks/{task_id}/history')
    async def task_history(task_id: str, current_user: dict = Depends(staff)):
        t = await db.operational_tasks.find_one({'id': task_id}, {'_id': 0})
        if not t:
            raise HTTPException(status_code=404, detail='Tarefa não encontrada')
        if not allowed(t, current_user):
            raise HTTPException(status_code=403, detail='Sem acesso')
        return {'task_id': task_id, 'title': t['title'], 'events': list(reversed(t.get('events', [])))}

    @api_router.get('/invoices/history')
    async def invoice_history(
        page: int = Query(default=1, ge=1, le=100000),
        page_size: int = Query(default=50, ge=1, le=100),
        start: str | None = None, end: str | None = None,
        status: str = 'all', number: str = '', customer: str = '',
        current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER])),
    ):
        query = {}
        if start or end:
            first = start or '2000-01-01'
            last = end or br_today().isoformat()
            # Busca de histórico pode atravessar vários anos; sem limite de 366 dias.
            a, b = parsed_day(first, 'Data inicial'), parsed_day(last, 'Data final')
            if b < a:
                raise HTTPException(status_code=422, detail='Intervalo inválido')
            query['created_at'] = {
                '$gte': datetime.combine(a, datetime.min.time(), tzinfo=TZ).astimezone(timezone.utc).isoformat(),
                '$lt': datetime.combine(b + timedelta(days=1), datetime.min.time(), tzinfo=TZ).astimezone(timezone.utc).isoformat(),
            }
        if status != 'all':
            if status not in ('mock', 'pending', 'issued', 'cancelled'):
                raise HTTPException(status_code=422, detail='Status inválido')
            query['status'] = status
        if number.strip():
            query['number'] = {'$regex': re.escape(number.strip()[:70]), '$options': 'i'}
        if customer.strip():
            query['customer_name'] = {'$regex': re.escape(customer.strip()[:70]), '$options': 'i'}
        total = await db.invoices.count_documents(query)
        items = await db.invoices.find(query, {'_id': 0, 'customer_cpf': 0}).sort([('created_at', DESCENDING), ('_id', DESCENDING)]).skip((page-1)*page_size).limit(page_size).to_list(page_size)
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'pages': max(1, (total + page_size - 1)//page_size),
                'note': 'Histórico de registros existentes no MongoDB; não emite nem recupera notas ausentes.'}

    @api_router.get('/reports/advanced')
    async def advanced_report(
        start: str, end: str, channel: str = 'all', payment: str = 'all',
        group_by: str = 'day', search: str = '',
        current_user: dict = Depends(admin),
    ):
        if channel not in ('all', 'local', 'online'):
            raise HTTPException(status_code=422, detail='Canal inválido')
        if payment not in PAYMENT_METHODS | {'all'}:
            raise HTTPException(status_code=422, detail='Pagamento inválido')
        if group_by not in ('day', 'week', 'month'):
            raise HTTPException(status_code=422, detail='Agrupamento inválido')
        first, last, from_utc, to_utc = date_limits(start, end)
        q = {'is_closed': True, 'is_comp': {'$ne': True}, 'status': {'$ne': 'cancelled'},
             'closed_at': {'$gte': from_utc, '$lt': to_utc}}
        # Não há limite arbitrário de 500 notas/pedidos; recusamos consultas gigantes ao invés de truncar silenciosamente.
        count = await db.orders.count_documents(q)
        if count > 30000:
            raise HTTPException(status_code=422, detail='Período com muitos pedidos: divida a consulta em intervalos menores')
        orders = await db.orders.find(q, {'_id': 0}).to_list(length=count or 1)
        order_ids = [o['id'] for o in orders if o.get('id')]
        methods = defaultdict(list)
        for i in range(0, len(order_ids), 1000):
            for p in await db.payments.find({'order_id': {'$in': order_ids[i:i+1000]}}, {'_id': 0}).to_list(length=None):
                methods[p.get('order_id')].append(p)
        totals = defaultdict(lambda: {'orders': 0, 'products_cents': 0, 'fee_cents': 0, 'gross_cents': 0, 'online_cents': 0, 'local_cents': 0})
        products = defaultdict(lambda: {'quantity': 0, 'revenue_cents': 0})
        payment_totals = defaultdict(int)
        searched = search.strip().lower()[:100]
        unreconciled = 0
        included = 0
        for o in orders:
            is_online = o.get('source') == 'online' or o.get('platform') in ('ifood', '99food', 'other')
            if channel == 'local' and is_online or channel == 'online' and not is_online:
                continue
            pay = methods.get(o.get('id'), [])
            if payment != 'all' and (payment == 'platform') != is_online:
                # Online não utiliza métodos de gaveta; presencial não utiliza plataforma.
                continue
            if payment not in ('all', 'platform') and not any(p.get('method') == payment for p in pay):
                continue
            if searched and not any(searched in str(o.get(key, '')).lower() for key in ('id', 'tab_number', 'table_number', 'external_order_number', 'waiter_name', 'platform')):
                continue
            try:
                dt = datetime.fromisoformat(str(o['closed_at']).replace('Z', '+00:00'))
                day = dt.astimezone(TZ).date()
            except (KeyError, TypeError, ValueError):
                continue
            if group_by == 'month':
                key = day.strftime('%Y-%m')
            elif group_by == 'week':
                key = (day-timedelta(days=day.weekday())).isoformat()
            else:
                key = day.isoformat()
            total = as_cents(o.get('total'))
            fee = 0 if is_online else min(total, as_cents(o.get('service_fee')))
            b = totals[key]
            b['orders'] += 1
            b['products_cents'] += total-fee
            b['fee_cents'] += fee
            b['gross_cents'] += total
            b['online_cents' if is_online else 'local_cents'] += total
            included += 1
            for it in o.get('items', []):
                if it.get('status') == 'cancelled' or it.get('is_courtesy'):
                    continue
                pname = it.get('product_name') or 'Produto sem nome'
                qty = max(0, int(it.get('quantity', 0) or 0))
                products[pname]['quantity'] += qty
                products[pname]['revenue_cents'] += as_cents(it.get('unit_price')) * qty
            if not is_online:
                raw_received = sum(as_cents(p.get('amount')) for p in pay)
                if raw_received < total:
                    unreconciled += 1
                raw_cash = sum(as_cents(p.get('amount')) for p in pay if p.get('method') == 'cash')
                change = max(0, raw_received-total)
                for p in pay:
                    amt = as_cents(p.get('amount'))
                    if p.get('method') == 'cash':
                        # O troco é removido apenas da parcela em espécie.
                        reduced = min(change, amt)
                        amt -= reduced
                        change -= reduced
                    payment_totals[p.get('method', 'unknown')] += amt
        rows = [{'period': key, 'orders': b['orders'], 'product_sales': reais(b['products_cents']),
                 'service_fee': reais(b['fee_cents']), 'gross_total': reais(b['gross_cents']),
                 'local_total': reais(b['local_cents']), 'online_total': reais(b['online_cents'])}
                for key, b in sorted(totals.items())]
        all_gross = sum(b['gross_cents'] for b in totals.values())
        response = {
            'filters': {'start': first.isoformat(), 'end': last.isoformat(), 'channel': channel, 'payment': payment, 'group_by': group_by, 'search': searched},
            'summary': {'orders': included, 'gross_total': reais(all_gross),
                        'product_sales': reais(sum(b['products_cents'] for b in totals.values())),
                        'service_fee': reais(sum(b['fee_cents'] for b in totals.values())),
                        'local_total': reais(sum(b['local_cents'] for b in totals.values())),
                        'online_total': reais(sum(b['online_cents'] for b in totals.values())),
                        'avg_ticket': reais(round(all_gross / included)) if included else 0,
                        'unreconciled_local_orders': unreconciled},
            'rows': rows,
            'top_products': [{'name': name, 'quantity': vals['quantity'], 'revenue': reais(vals['revenue_cents'])}
                             for name, vals in sorted(products.items(), key=lambda kv: kv[1]['quantity'], reverse=True)[:20]],
            'payment_methods': [{'method': k, 'amount': reais(v)} for k, v in sorted(payment_totals.items())],
            'note': ('Pedidos fechados, não cancelados/não cortesia. Valores online indicam pedido concluído, não repasse recebido. '
                     'Com filtro por pagamento, o valor é do pedido inteiro se usou o método (pode ser pagamento misto). '
                     'Pagamentos presenciais podem incluir parcelas ainda não conciliadas; confira o indicador de pendências. '
                     'Gorjeta de 10% separada. Não é cálculo de lucro líquido.'),
        }
        return response
