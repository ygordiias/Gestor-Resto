"""Índices das coleções de vendas, pagamentos, notas e caixa.

Criados na subida do servidor (server.py, startup). `create_index` não faz
nada quando o índice já existe com a mesma definição, então rodar de novo é
seguro. Nenhum índice aqui apaga, altera ou reordena dados.

Uma falha (por exemplo, um índice com o mesmo nome e outra definição criado à
mão no Atlas) é registrada no log e o servidor continua: sem o índice as
consultas só ficam mais lentas.
"""
from pymongo import ASCENDING, DESCENDING

# (coleção, chaves, nome)
INDEXES = [
    ("orders", [("is_closed", ASCENDING), ("closed_at", DESCENDING)], "orders_is_closed_closed_at"),
    ("orders", [("created_at", DESCENDING), ("_id", DESCENDING)], "orders_created_at"),
    ("orders", [("table_id", ASCENDING), ("is_closed", ASCENDING)], "orders_table_is_closed"),
    ("payments", [("order_id", ASCENDING)], "payments_order_id"),
    ("payments", [("register_id", ASCENDING)], "payments_register_id"),
    ("payments", [("created_at", DESCENDING), ("_id", DESCENDING)], "payments_created_at"),
    ("invoices", [("order_id", ASCENDING)], "invoices_order_id"),
    ("invoices", [("created_at", DESCENDING), ("_id", DESCENDING)], "invoices_created_at"),
    ("invoices", [("status", ASCENDING), ("created_at", DESCENDING)], "invoices_status_created_at"),
    ("cash_registers", [("closed_at", DESCENDING)], "cash_registers_closed_at"),
    ("payment_reversals", [("order_id", ASCENDING)], "payment_reversals_order_id"),
]


async def ensure_indexes(db, logger):
    """Cria os índices que faltam. Retorna (criados_ou_existentes, falhas)."""
    ok, failed = [], []
    for collection, keys, name in INDEXES:
        try:
            await db[collection].create_index(keys, name=name)
            ok.append(name)
        except Exception as e:  # nunca derruba a subida do servidor
            failed.append(name)
            # Só o tipo do erro: a mensagem do driver pode conter dados do banco.
            logger.warning(f"Índice {collection}.{name} não foi criado ({type(e).__name__})")
    logger.info(f"Índices verificados: {len(ok)} ok, {len(failed)} com falha")
    return ok, failed
