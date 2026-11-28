"""Banco MongoDB falso em memória para testes OFFLINE (sem servidor e sem rede).

Cobre só o que o Gestor usa nos fluxos testados: find/find_one com filtros
simples ($ne, $in, $gte, $lte, $exists, $type, $or), insert, update ($set,
$inc, $push, $addToSet, upsert), delete, count_documents e índices únicos
(inclusive parciais).
"""
import copy

from pymongo.errors import DuplicateKeyError


def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


class _Missing:
    pass


_MISSING = _Missing()


def _cond(value, cond):
    if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            present = value is not _MISSING
            v = value if present else None
            if op == "$ne" and v == arg:
                return False
            if op == "$in" and v not in arg:
                return False
            if op == "$nin" and v in arg:
                return False
            if op == "$exists" and present != bool(arg):
                return False
            if op == "$type" and arg == "string" and not isinstance(v, str):
                return False
            if op in ("$gte", "$lte", "$gt", "$lt"):
                if v is None:
                    return False
                if op == "$gte" and not v >= arg:
                    return False
                if op == "$lte" and not v <= arg:
                    return False
                if op == "$gt" and not v > arg:
                    return False
                if op == "$lt" and not v < arg:
                    return False
        return True
    if value is _MISSING:
        return cond is None
    if isinstance(value, list) and not isinstance(cond, list):
        return cond in value
    return value == cond


def match(doc, query):
    for key, cond in (query or {}).items():
        if key == "$or":
            if not any(match(doc, q) for q in cond):
                return False
            continue
        if key == "$and":
            if not all(match(doc, q) for q in cond):
                return False
            continue
        if not _cond(_get(doc, key), cond):
            return False
    return True


def _project(doc, projection):
    out = copy.deepcopy(doc)
    out.pop("_id", None)
    return out


class Result:
    def __init__(self, matched=0, modified=0, upserted_id=None, deleted=0):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id
        self.deleted_count = deleted


class Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        # Aceita sort("campo", -1) e sort([("a", 1), ("b", -1)]), como o Motor.
        keys = [(key, direction)] if isinstance(key, str) else list(key)
        for k, d in reversed(keys):  # ordenação estável: da última chave para a primeira
            self._docs.sort(key=lambda doc, k=k: (doc.get(k) is None, doc.get(k)),
                            reverse=d == -1)
        return self

    async def to_list(self, length=None):
        return self._docs if length is None else self._docs[:length]

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class Collection:
    def __init__(self, name):
        self.name = name
        self.docs = []
        self.unique = []  # (fields, partial)
        self.indexes = []  # (fields, opções) de cada create_index

    async def create_index(self, keys, unique=False, partialFilterExpression=None, name=None, **kw):
        fields = [keys] if isinstance(keys, str) else [k for k, _ in keys]
        self.indexes.append((fields, {"unique": unique, "partial": partialFilterExpression, "name": name, **kw}))
        if unique:
            self.unique.append((fields, partialFilterExpression))
        return name or "_".join(fields)

    def _check_unique(self, doc, ignore=None):
        for fields, partial in self.unique:
            if partial and not match(doc, partial):
                continue
            key = tuple(_get(doc, f) for f in fields)
            for other in self.docs:
                if other is ignore or (partial and not match(other, partial)):
                    continue
                if tuple(_get(other, f) for f in fields) == key:
                    raise DuplicateKeyError(f"duplicado em {self.name}: {fields}")

    async def insert_one(self, doc, session=None):
        self._check_unique(doc)
        doc.setdefault("_id", len(self.docs) + 1)
        self.docs.append(copy.deepcopy(doc))
        return Result(modified=1)

    async def insert_many(self, docs, session=None):
        for d in docs:
            await self.insert_one(d)

    async def find_one(self, query=None, projection=None, session=None, **kw):
        for d in self.docs:
            if match(d, query):
                return _project(d, projection)
        return None

    def find(self, query=None, projection=None, **kw):
        return Cursor([_project(d, projection) for d in self.docs if match(d, query)])

    async def count_documents(self, query=None, **kw):
        return sum(1 for d in self.docs if match(d, query))

    @staticmethod
    def _apply(doc, update):
        for op, fields in update.items():
            for k, v in fields.items():
                if op == "$set":
                    doc[k] = copy.deepcopy(v)
                elif op == "$setOnInsert":
                    pass
                elif op == "$unset":
                    doc.pop(k, None)
                elif op == "$inc":
                    doc[k] = doc.get(k, 0) + v
                elif op == "$push":
                    doc.setdefault(k, []).append(copy.deepcopy(v))
                elif op == "$addToSet":
                    lst = doc.setdefault(k, [])
                    if v not in lst:
                        lst.append(copy.deepcopy(v))
                else:
                    raise NotImplementedError(op)

    async def update_one(self, query, update, upsert=False, session=None):
        for d in self.docs:
            if match(d, query):
                before = copy.deepcopy(d)
                self._apply(d, update)
                try:
                    self._check_unique(d, ignore=d)
                except DuplicateKeyError:
                    d.clear()
                    d.update(before)
                    raise
                return Result(matched=1, modified=int(before != d))
        if upsert:
            new = {k: v for k, v in query.items() if not k.startswith("$") and not isinstance(v, dict)}
            self._apply(new, update)
            for k, v in update.get("$setOnInsert", {}).items():
                new[k] = v
            await self.insert_one(new)
            return Result(upserted_id=new["_id"])
        return Result()

    async def update_many(self, query, update, **kw):
        n = 0
        for d in self.docs:
            if match(d, query):
                self._apply(d, update)
                n += 1
        return Result(matched=n, modified=n)

    async def delete_one(self, query, **kw):
        for i, d in enumerate(self.docs):
            if match(d, query):
                self.docs.pop(i)
                return Result(deleted=1)
        return Result()

    async def delete_many(self, query, **kw):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not match(d, query)]
        return Result(deleted=before - len(self.docs))

    def aggregate(self, pipeline):
        raise NotImplementedError("aggregate")


class FakeDB:
    def __init__(self):
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cols:
            self._cols[name] = Collection(name)
        return self._cols[name]

    def __getitem__(self, name):
        return getattr(self, name)
