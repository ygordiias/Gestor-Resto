# Operação

Variáveis de ambiente, deploy, backup, rollback e ambiente local. **Nenhum valor real aparece aqui**: senhas, chaves e endereços de banco ficam só no painel do Render e no `.env` local, que o `.gitignore` já ignora.

## Variáveis de ambiente

### Backend (`main`)

| Variável | Obrigatória | Para quê |
|---|---|---|
| `MONGO_URL` | sim | Endereço do MongoDB. Com `mongodb+srv://` ou `mongodb.net`, o TLS é ligado com validação de certificado |
| `DB_NAME` | sim | Nome do banco |
| `SECRET_KEY` | sim | Assina os tokens JWT e o token da prévia do caixa. Mínimo de 32 caracteres. Sem ela o servidor não sobe. Gerar com `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `INITIAL_SUPERADMIN_EMAIL` | não | Cria o primeiro superadmin no startup, só se não existir nenhum |
| `INITIAL_SUPERADMIN_PASSWORD` | não | Senha desse superadmin (mínimo de 12 caracteres). Pode ser removida depois da criação |
| `INITIAL_SUPERADMIN_NAME` | não | Nome (padrão "Super Admin") |
| `PHYSICAL_TAB_MIN` | não | Primeira comanda física (padrão 200) |
| `PHYSICAL_TAB_MAX` | não | Última comanda física (padrão 291) |
| `RENDER_GIT_COMMIT` | automática | Definida pelo próprio Render; aparece em `GET /api/versao` |
| `GIT_COMMIT` | não | Alternativa ao `RENDER_GIT_COMMIT` fora do Render |

### Frontend

| Variável | Obrigatória | Para quê |
|---|---|---|
| `REACT_APP_BACKEND_URL` | sim | URL do backend, sem `/api` no fim. Entra no build: mudar exige novo build |
| `ENABLE_HEALTH_CHECK` | não | Liga o plugin de health check do CRACO em desenvolvimento |

### Testes de integração

`TEST_ADMIN_EMAIL`, `TEST_ADMIN_PASSWORD`, `TEST_WAITER_EMAIL`, `TEST_WAITER_PASSWORD`, `TEST_CASHIER_EMAIL`, `TEST_CASHIER_PASSWORD`, `TEST_BAR_EMAIL`, `TEST_BAR_PASSWORD` e `REACT_APP_BACKEND_URL` (servidor de teste). Sempre contas de um **banco de teste**.

### Pendentes em outras branches

| Variável | Branch | Para quê |
|---|---|---|
| `CORS_ORIGINS` | `fix/cors-socket` (PR #4) | Origens permitidas no CORS e no Socket.IO. Vai ser obrigatória |
| `NOSTFOOD_ENABLED`, `NOSTFOOD_API_KEY`, `NOSTFOOD_WEBHOOK_SECRET`, `NOSTFOOD_BASE_URL`, `NOSTFOOD_POLL_SECONDS`, `NOSTFOOD_SEND_STATUS` | `feat/integracao-nostfood` | Veja [integracoes/nostfood.md](integracoes/nostfood.md) |

## Deploy no Render

Não há `render.yaml` no repositório: a configuração fica no painel do Render. A tabela abaixo é a configuração esperada para este código; **confira no painel** antes de mudar qualquer coisa.

| | Backend (Web Service) | Frontend (Static Site) |
|---|---|---|
| Pasta raiz | `backend` | `frontend` |
| Build | `pip install -r requirements.txt` | `npm ci && npm run build` |
| Start | `uvicorn server:app --host 0.0.0.0 --port $PORT` | (estático) pasta publicada `build` |
| Health check | `/api/health` (só o processo). `/health` também testa o MongoDB | — |
| Rotas | — | Reescrever `/*` para `/index.html` (SPA: `/kitchen`, `/cliente/...`) |
| Variáveis | as do backend acima | `REACT_APP_BACKEND_URL` |

- A branch publicada é a `main`. Todo merge na `main` vai para produção. Mudanças entram por PR revisado.
- O servidor **para no startup** (e o Render mantém a versão anterior no ar) se faltar `SECRET_KEY`, se ela for curta ou se o MongoDB não responder. Nos logs aparece só o tipo do erro, nunca o endereço do banco.
- O IP de saída do Render precisa estar liberado no Atlas (Network Access).
- O fechamento de comanda usa **transação**: o MongoDB precisa ser replica set (o Atlas já é).
- Depois do deploy, conferir `GET /api/versao`: o `commit` precisa ser o do merge.

## Backup

As fotos das tarefas ficam no próprio MongoDB (GridFS). Um backup do banco cobre tudo; nada fica no disco do Render.

1. **Backup do Atlas:** conferir no painel do Atlas se o cluster tem backup automático e a retenção. Depende do plano do cluster **[confirmar no Atlas]**.
2. **Cópia manual antes de mudanças sensíveis** (deploy com script de dados, correção de caixa, integração nova):

   ```bash
   # MONGO_URL e DB_NAME vêm do ambiente; nunca escreva o endereço no comando
   mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --archive="gestor-$(date +%F-%H%M).archive.gz"
   ```

   Guarde o arquivo fora do repositório, em local com acesso restrito: ele tem dados pessoais de clientes e funcionários (veja [seguranca-lgpd.md](seguranca-lgpd.md)).
3. **Teste de restauração:** restaure em um banco de **teste**, nunca por cima da produção:

   ```bash
   mongorestore --uri="$MONGO_URL_TESTE" --gzip --archive=gestor-AAAA-MM-DD-HHMM.archive.gz \
     --nsFrom="$DB_NAME.*" --nsTo="gestor_restauracao.*"
   ```

## Rollback

- **Código:** no Render, "Rollback" para o deploy anterior, que volta o serviço na hora. Em seguida, reverter o commit na `main` por PR (`git revert`), para o próximo deploy não trazer o problema de volta.
- **Dados:** os scripts de correção (`corrigir_comandas_caixa.py`, `ajustar_excesso_pagamento.py`, `criar_comandas_faltantes.py`) rodam em **simulação** por padrão e só gravam com `--apply`. Rode sempre a simulação antes. Para desfazer uma gravação, restaure o backup feito antes em um banco separado e copie de lá só os documentos afetados.
- **Frontend:** o `REACT_APP_BACKEND_URL` entra no build. Rollback do site estático volta também a URL usada.

## Ambiente local

Use sempre um banco **local ou de teste**, nunca o de produção.

### MongoDB local com transação

O fechamento de comanda exige transação, que não funciona em MongoDB avulso (a rota responde 503). Suba como replica set de um nó:

```bash
docker run -d --name mongo-gestor -p 27017:27017 mongo:7 --replSet rs0
docker exec mongo-gestor mongosh --quiet --eval 'rs.initiate()'
```

### Backend

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cat > .env <<'EOF'
MONGO_URL=mongodb://localhost:27017/?replicaSet=rs0&directConnection=true
DB_NAME=gestor_local
SECRET_KEY=<gere com o comando da tabela acima>
INITIAL_SUPERADMIN_EMAIL=<seu e-mail de teste>
INITIAL_SUPERADMIN_PASSWORD=<senha de teste com 12+ caracteres>
EOF
uvicorn server:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm ci
REACT_APP_BACKEND_URL=http://localhost:8001 npm start
```

Se as portas 3000 ou 8001 estiverem ocupadas (outra cópia do projeto rodando), use outras: `uvicorn ... --port 8002` e `PORT=3002 REACT_APP_BACKEND_URL=http://localhost:8002 npm start`.

### Testes

- **Offline** (sem rede e sem banco): os arquivos que não importam `requests`. Lista no [README](../README.md#testes).
- **Integração:** os demais, com servidor de teste rodando e as variáveis `TEST_*`. O padrão de `REACT_APP_BACKEND_URL` em alguns desses arquivos aponta para um servidor externo antigo: defina a variável sempre.
- **OpenAPI:** `python backend/scripts/exportar_openapi.py` atualiza `docs/openapi.json` sem servidor e sem banco.

## Scripts de manutenção (`backend/scripts/`)

| Script | Grava? | Para quê |
|---|---|---|
| `diagnostico_caixa.py` | não | Lista o que trava o fechamento do caixa aberto |
| `corrigir_comandas_caixa.py` | só com `--apply` | Registra pagamento que faltou, com autoria e justificativa |
| `ajustar_excesso_pagamento.py` | só com `--apply` | Corrige cartão ou Pix maior que o total sem dinheiro para troco |
| `criar_comandas_faltantes.py` | só sem `--dry-run` | Cria as comandas físicas que faltam (idempotente) |
| `listar_usuarios.py` | não | Nome, e-mail, perfil e situação das contas (nunca senha) |
| `checar_senhas_padrao.py` | não | Verifica se contas antigas ainda usam senha padrão |
| `exportar_openapi.py` | só o arquivo | Gera `docs/openapi.json` |

Os scripts que falam com o banco leem `MONGO_URL` e `DB_NAME` do ambiente.
