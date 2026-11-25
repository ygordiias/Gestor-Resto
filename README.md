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
# crie backend/.env com MONGO_URL, DB_NAME, SECRET_KEY e CORS_ORIGINS (veja docs/operacao.md)
uvicorn server:app --reload --port 8001
```

O servidor não sobe sem `SECRET_KEY` (mínimo de 32 caracteres) ou sem conseguir falar com o MongoDB.

Variáveis obrigatórias do backend:

| Variável | O que é |
|---|---|
| `MONGO_URL`, `DB_NAME` | Banco MongoDB (local: `mongodb://localhost:27017` e um banco de teste) |
| `SECRET_KEY` | Chave do JWT, mínimo de 32 caracteres |
| `CORS_ORIGINS` | Origens do frontend aceitas pela API e pelo Socket.IO, separadas por vírgula, com `http://` ou `https://` (ex.: `http://localhost:3000`). `*` não é aceito. Sem ela, o servidor não sobe |

#### Versão do Python

Use **Python 3.12**, a mesma versão do Render (está em `backend/.python-version`).

- **Python 3.14 não funciona** com o `motor==3.3.1` fixado no `requirements.txt`. No 3.14, `asyncio.get_event_loop()` não cria mais um event loop sozinho, e o `server.py` quebra já no import com `RuntimeError: There is no current event loop in thread 'MainThread'`.
- O `tzdata` está no `requirements.txt` porque o backend usa o fuso `America/Sao_Paulo` e o Windows não traz a base de fusos horários. Sem ele, o import quebra com `ZoneInfoNotFoundError`.

```bash
cd backend
py -3.12 -m venv .venv          # Windows (no Linux: python3.12 -m venv .venv)
.venv\Scripts\activate          # Windows (no Linux: source .venv/bin/activate)
pip install -r requirements.txt pytest requests
python -m pytest tests -q
```

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

Alguns testes não rodam só com o código:
- `test_health`, `test_register_removed` e `test_seed_removed` precisam de um backend rodando em `localhost:8001`.
- Os testes que usam `tests/_credenciais.py` são pulados sem as credenciais de um banco de teste.
- No Windows, os dois testes que conferem a permissão `600` do arquivo de backup falham, porque o Windows não aplica `chmod`.

## Kiosk da cozinha (Linux Mint): som automático

O KDS (Cozinha, Bar e Churrasqueira) toca sons sozinho. Cada evento tem um som diferente:

| Evento | Som |
|---|---|
| Pedido novo | "plim": duas notas agudas subindo |
| Pedido atrasado | três toques médios e ásperos, repetidos a cada 3 min |
| Pedido cancelado | tom grave descendo, repetido até alguém dar "Ciente" |
| Observação nova | dois bipes curtos |

O Chromium bloqueia som sem um clique do usuário. Quando isso acontece, a tela mostra o aviso amarelo **"Ativar som (o navegador bloqueou)"**, e um toque na tela libera o som. Para o kiosk nunca bloquear, abra o Chromium com:

```bash
chromium --kiosk --autoplay-policy=no-user-gesture-required "https://SEU-GESTOR/kitchen"
```

No Linux Mint, o executável pode se chamar `chromium-browser` (pacote apt) ou ser aberto por `flatpak run org.chromium.Chromium` (Flatpak). Troque `/kitchen` por `/bar` ou `/grill` nas outras telas. Para abrir sozinho ao ligar o computador, coloque o mesmo comando em **Aplicativos de sessão** (Startup Applications).

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
