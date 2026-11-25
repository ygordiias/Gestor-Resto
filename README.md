# Gestor Restô

Sistema de gestão para restaurante: salão (mesas e comandas físicas), cozinha, bar e chapa em tempo real, caixa, pedidos online, estoque com ficha técnica e CMV, relatórios e rotinas operacionais.

Criado e desenvolvido por **Ygor Dias**, CEO e fundador da **Tecno Dias** e do EMAÚS. O primeiro restaurante a usar o sistema é o **EMAÚS**, em São Carlos/SP.

> Software proprietário. Todos os direitos reservados. Veja [LICENSE](LICENSE) e [AUTHORS.md](AUTHORS.md).

## Módulos

| Módulo | O que faz | Tela principal | Perfis |
|---|---|---|---|
| Mesas e comandas | Mesas, comandas físicas numeradas (200 a 291), lançamento de itens pelo garçom | `/tables`, `/order/:mesa` | admin, garçom |
| Cozinha, bar e chapa (KDS) | Fila de preparo em tempo real por Socket.IO, status por item | `/kitchen`, `/bar`, `/grill` | admin, cozinha, bar |
| Caixa | Fechamento de comanda com várias formas de pagamento, cortesia, cancelamento, pedidos online, abertura, sangria, reforço, prévia impressa e fechamento do caixa | `/cashier` | admin, caixa |
| Pedidos online | Cardápio público do cliente (`/cliente`) e lançamento manual de pedidos do iFood, 99Food e outros | `/cliente`, `/cashier` | público, admin, caixa |
| Cardápio | Categorias e produtos | `/menu` | admin |
| Estoque, ficha técnica e CMV | Matéria-prima, semiacabados e produtos; receitas por produto; baixa automática; produção; custo e margem | `/stock`, `/technical-sheets`, `/cmv`, `/production` | admin (fichas técnicas: leitura para todos) |
| Relatórios | Vendas, consumo por mesa, taxa de serviço semanal, relatório avançado por período | `/reports` | admin |
| Crédito de funcionários | Consumo a prazo com limite mensal e acerto manual | `/cashier` (painel financeiro) | admin, caixa |
| Tarefas operacionais | Checklists por setor com comprovação por foto e aprovação | `/tasks` | todos os perfis internos |
| Notas | Registro de notas (emissão fiscal ainda simulada) e histórico | `/invoices`, `/invoices/history` | admin, caixa |
| Usuários e configurações | Contas, perfis, dados do restaurante | `/users`, `/settings` | admin |

## Stack

- **Backend:** Python 3.12, FastAPI, Motor (MongoDB assíncrono), python-socketio, JWT (python-jose), bcrypt (passlib).
- **Frontend:** React 19 (Create React App com CRACO), Tailwind CSS, componentes shadcn/ui (Radix), axios, socket.io-client.
- **Banco:** MongoDB Atlas (TLS). Fotos de tarefas em GridFS no mesmo banco.
- **Hospedagem:** Render.

Detalhes em [docs/arquitetura.md](docs/arquitetura.md).

## Como rodar (ambiente local)

Use sempre um **banco de teste**, nunca o de produção. Passo a passo completo em [docs/operacao.md](docs/operacao.md).

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# crie backend/.env com MONGO_URL, DB_NAME e SECRET_KEY (veja docs/operacao.md)
uvicorn server:app --reload --port 8001
```

O servidor não sobe sem `SECRET_KEY` (mínimo de 32 caracteres) ou sem conseguir falar com o MongoDB.

### Frontend

```bash
cd frontend
npm ci
REACT_APP_BACKEND_URL=http://localhost:8001 npm start   # abre na porta 3000
```

Build de produção: `npm run build`.

### Testes

```bash
cd backend
pip install pytest
python -m pytest tests/test_bootstrap_superadmin.py tests/test_close_order.py \
  tests/test_route_permissions.py tests/test_user_management.py \
  tests/test_physical_tabs_range.py tests/test_secret_key.py \
  tests/test_diagnostico_caixa.py tests/test_corrigir_comandas_caixa.py \
  tests/test_ajustar_excesso_pagamento.py tests/test_versao.py
```

Esses são os testes **offline**: não usam rede nem banco. Os demais arquivos de `backend/tests/` são de integração: precisam de um servidor rodando com banco de teste e das variáveis `TEST_<PERFIL>_EMAIL` / `TEST_<PERFIL>_PASSWORD`.

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/arquitetura.md](docs/arquitetura.md) | Stack, coleções do MongoDB, eventos Socket.IO, perfis e diagrama |
| [docs/api.md](docs/api.md) | Rotas da API por módulo, autenticação e permissões |
| [docs/openapi.json](docs/openapi.json) | Especificação OpenAPI exportada do FastAPI |
| [docs/regras-de-negocio.md](docs/regras-de-negocio.md) | Comandas, taxa de serviço, caixa, repasse, cancelamento, cortesia, permuta, estoque e CMV |
| [docs/integracoes/nostfood.md](docs/integracoes/nostfood.md) | Integração NostFood (pedidos do iFood e da 99) |
| [docs/integracoes/ifood-preparacao.md](docs/integracoes/ifood-preparacao.md) | O que falta para homologar direto com a Merchant API do iFood |
| [docs/operacao.md](docs/operacao.md) | Variáveis de ambiente, deploy no Render, backup, rollback e ambiente local |
| [docs/seguranca-lgpd.md](docs/seguranca-lgpd.md) | Dados pessoais guardados, acesso, retenção e exclusão |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de mudanças |

## Versão em execução

`GET /api/versao` devolve sistema, versão, autor, empresa e o hash do commit em execução. A rota é pública e não consulta o banco.

## Autor

**Ygor Dias**, CEO e fundador da Tecno Dias e do EMAÚS.
Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias.
