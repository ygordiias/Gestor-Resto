# Here are your Instructions

## Backend: versão do Python

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
