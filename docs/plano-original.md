# Sebo na Nuvem AWS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar, na AWS Academy Learner Lab, uma aplicação de livraria estilo sebo em que o cliente pede um livro, recebe e-mail (disponível agora, ou quando chegar) e tudo fica gravado no banco, com a documentação exigida pelo enunciado.

**Architecture:** Interface web estática chama 4 Lambdas Python via Function URLs. As Lambdas compartilham uma **Lambda Layer** (`sebo-common`) e usam 3 tabelas DynamoDB; e-mails saem por um tópico SNS cujas assinaturas filtram pelo atributo `emailCliente`. O estoque é reservado de forma atômica (escrita condicional), e a chegada de livros atende a fila de espera em ordem FIFO.

**Tech Stack:** Python 3.12 (Lambda + testes), boto3, pytest + moto (testes unitários), AWS CLI v2 (deploy), HTML/JS puro + Node `node:test` (frontend), Mermaid (diagramas).

**Spec:** `docs/Trab2_2026_2.pdf` (enunciado do professor — copiar de `/mnt/user-data/uploads/Trab2_2026_2.pdf` na Task 1). Este plano **substitui** `AGENTE_AUTONOMO_sebo_aws.md`.

## Global Constraints

Do enunciado (valores verbatim):
- "Pelo menos três funções Lambda."
- "Pelo menos uma tabela em um banco de dados."
- "Envio de e-mail."
- "Interfaces com usuário (pessoa física, comprador ou colaborador da livraria) em qualquer linguagem de programação."
- "considere que o cliente já se inscreveu no tópico – usando a interface da AWS."
- Entrega: relatório "do que foi implementado contendo o que funcionou e o que não funcionou", documentação "de como instalar a aplicação", "instruções de como operar", "diagrama em blocos" e "diagrama UML de sequência"; informar no EaD a conta da AWS Academy.
- "Na dúvida, não invente, pergunte!"

Decisões do projeto (valem para todas as tasks):
- Região **`us-east-1`**; role das Lambdas = **`LabRole`**; é **proibido** criar/alterar IAM e usar serviços que gastam o orçamento do lab (RDS, EC2, NAT, OpenSearch).
- Recursos sempre com prefixo **`sebo-`**; nunca tocar em recursos sem esse prefixo.
- Runtime **Python 3.12**. **Lambda Layer Python obrigatória** (pedido do grupo): `sebo-common`, zip com pasta **`python/`** na raiz; sem `boto3` dentro da layer.
- Tabelas: `sebo-Livros` (PK `livroId`), `sebo-Interesses` (PK `interesseId`; GSI `livroId-status-index` com PK `livroId`, SK `status`, projeção ALL), `sebo-Vendas` (PK `vendaId`). Todas `PAY_PER_REQUEST`.
- `status` de interesse ∈ {`PENDENTE`, `RESERVADO`, `VENDIDO`}. `status` é palavra reservada do DynamoDB → usar `#s` em expressões de string.
- Atributo de mensagem SNS: `emailCliente` (String, sempre minúsculo). Tópico: `sebo-notificacoes`. Filter policy por assinatura: `{"emailCliente":["<email em minúsculo>"]}`.
- Variáveis de ambiente das Lambdas: `TABELA_LIVROS`, `TABELA_INTERESSES`, `TABELA_VENDAS`, `SNS_TOPIC_ARN`.
- Funções: `sebo-listar-livros`, `sebo-solicitar-livro`, `sebo-cadastrar-livro`, `sebo-efetivar-venda` (handler `app.lambda_handler`, Function URL `AuthType NONE`, CORS configurado **na URL**, nunca dentro do código).
- Nunca gravar credenciais AWS em arquivo, log ou commit. Nunca derrubar (teardown) os recursos ao final. Nunca inventar resultado de teste. Documentação em pt-BR.

## Review Focus

Entradas/falhas que o enunciado implica mas não menciona (cada uma tem teste na task dona):
1. **E-mail com maiúsculas/espaços** (`" Ana@Exemplo.COM "`) não casaria com a filter policy e o e-mail nunca chegaria → normalizar para minúsculo/sem espaços. *(Task 2 e Task 4)*
2. **Pedido repetido do mesmo cliente para o mesmo livro** (duplo clique) → não pode reservar 2 exemplares; responde 409. *(Task 4)*
3. **Chegada com menos exemplares que clientes na fila** → atende só quantos couberem, FIFO, estoque nunca negativo, o resto continua `PENDENTE`. *(Task 5)*
4. **Falha do SNS** → a reserva é mantida e a resposta informa `emailEnviado: false`; nada de erro 500 que "perde" o exemplar. *(Task 4 e Task 5)*
5. **Título com HTML** (`<script>…`) → a interface escapa; não executa. *(Task 7)*

## Mapa enunciado → tasks

| Exigência | Task |
|---|---|
| ≥ 3 Lambdas | 3, 4, 5, 6 (+ layer na 2) |
| ≥ 1 tabela | 2 (schemas), 8 |
| Envio de e-mail | 2 (`publicar_email`), 4, 5, 8 (SNS), 10 (verificação) |
| Interface cliente/colaborador | 7, 10 |
| Livro disponível → e-mail; indisponível → e-mail na chegada | 4, 5, 10 |
| Dados guardados p/ estoque e vendas | 2, 6, 8 |
| Relatório, instalação, operação, diagramas | 11 |
| Conta AWS Academy / apresentação | 12 |

## Pontos humanos (peça tudo numa única mensagem no início; siga com o que não estiver bloqueado)

- **H1** Credenciais do Learner Lab exportadas no terminal (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`).
- **H2** `TEST_EMAIL` e demais e-mails a assinar no tópico (`EMAILS_ASSINANTES`).
- **H3** Clicar no link de confirmação da assinatura SNS (checar spam).
- **H4** Confirmar que os 2 e-mails (disponível; chegada) caíram na caixa de entrada.
- **H5** Prints, divisão de trabalho no relatório, informar a conta no EaD, apresentar.

## Regras de execução autônoma

- Execute as tasks na ordem; marque `- [ ]` → `- [x]` conforme conclui; cada task termina com commit.
- Antes de cada task de AWS rode `bash scripts/check_env.sh`; se falhar → H1.
- Erro: diagnosticar (mensagem completa, `aws logs tail`, `describe-*`), corrigir, repetir até 3 vezes; persistindo, registrar em `docs/problemas.md` e aplicar o fallback:

| Problema | Fallback |
|---|---|
| Function URL pública dá 403 | reaplicar as 2 permissões da Task 9; persistindo, API Gateway HTTP API (rotas `GET /livros`, `POST /solicitar`, `POST /cadastrar`, `POST /efetivar`, integração `AWS_PROXY` payload 2.0, CORS `*`) e ajustar `frontend/config.js` |
| Layer não publica/anexa | copiar `layers/sebo_common/python/sebo_common/` para dentro do zip de cada Lambda e registrar a troca no relatório |
| Assinatura SNS com filtro conflita | `aws sns unsubscribe` + recriar; último caso, sem filtro e documentar que todos os assinantes recebem tudo |
| `python3.12` indisponível | usar `python3.11` e ajustar `--runtime` e `--compatible-runtimes` |
| S3 website bloqueado | servir `frontend/` com `python3 -m http.server 8080` |
| Sem shell/AWS CLI | gerar tudo; instruir o humano a rodar `bash deploy.sh` e `pytest -m e2e` no **AWS CloudShell** e colar as saídas |

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `config.env.example` / `config.env` (ignorado pelo git) | `REGION`, `TEST_EMAIL`, `EMAILS_ASSINANTES` |
| `infra/tabela_livros.json`, `tabela_interesses.json`, `tabela_vendas.json` | Schema único das tabelas (usado pelo deploy **e** pelos testes — DRY) |
| `layers/sebo_common/python/sebo_common/__init__.py` | Layer: utilitários HTTP/JSON, e-mail SNS, reserva atômica |
| `lambdas/{listar_livros,solicitar_livro,cadastrar_livro,efetivar_venda}/app.py` | Uma Lambda por responsabilidade |
| `frontend/{index.html,app.js,util.js,util.test.js,config.js}` | Interface; `config.js` é gerado pelo deploy |
| `scripts/{check_env.sh,01_dados.sh,02_lambdas.sh}`, `deploy.sh`, `seed.sh`, `reset_dados.sh` | Automação idempotente |
| `tests/unit/` | pytest + moto (sem AWS real) |
| `tests/e2e/` | pytest contra a AWS real (`RUN_E2E=1`, marcador `e2e`) |
| `docs/` | README, instalação, operação, relatório, diagramas, resultados |

---

### Task 1: Esqueleto do projeto e verificação do ambiente

**Files:**
- Create: `.gitignore`, `config.env.example`, `requirements-dev.txt`, `scripts/check_env.sh`, `docs/Trab2_2026_2.pdf`
- Test: execução de `scripts/check_env.sh`

**Interfaces:**
- Consumes: —
- Produces: `config.env` com `REGION="us-east-1"`, `TEST_EMAIL`, `EMAILS_ASSINANTES` (espaço-separados); `scripts/check_env.sh` → exit 0 e imprime `Conta: <id> | Região: us-east-1 | Role: arn:aws:iam::<id>:role/LabRole`, exit 1 caso contrário.

- [ ] **Step 1: Pedir H1 e H2** ao humano (mensagem única) e `git init`.
- [ ] **Step 2: Criar `.gitignore`** (`build/`, `__pycache__/`, `.venv/`, `config.env`, `frontend/config.js`, `node_modules/`), `config.env.example` e `requirements-dev.txt` (`pytest`, `moto[dynamodb,sns]>=5`, `boto3`), copiar o PDF para `docs/`, criar `config.env` real com os valores de H2.
- [ ] **Step 3: Implementar `scripts/check_env.sh`**: `set -euo pipefail`; carrega `config.env`; falha com a mensagem `credenciais AWS ausentes ou expiradas (ponto humano H1)` se `aws sts get-caller-identity` falhar; falha se `REGION` ≠ `us-east-1`; `aws iam get-role --role-name LabRole` só gera aviso se negado.
- [ ] **Step 4: Verificar**

Run (sem credenciais): `env -u AWS_ACCESS_KEY_ID bash scripts/check_env.sh; echo $?` → Expected: mensagem H1 e `1`.
Run (com credenciais): `bash scripts/check_env.sh` → Expected: linha `Conta: ... | Região: us-east-1 | Role: ...` e `0`.
Run: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest --collect-only -q` → Expected: instala sem erro.

- [ ] **Step 5: Commit**
```bash
git add .gitignore config.env.example requirements-dev.txt scripts/check_env.sh docs/Trab2_2026_2.pdf
git commit -m "chore: esqueleto do projeto e check_env"
```

---

### Task 2: Layer `sebo-common`, schemas das tabelas e infraestrutura de testes

**Files:**
- Create: `layers/sebo_common/python/sebo_common/__init__.py`, `infra/tabela_livros.json`, `infra/tabela_interesses.json`, `infra/tabela_vendas.json`, `tests/unit/conftest.py`
- Test: `tests/unit/test_sebo_common.py`

**Interfaces:**
- Consumes: —
- Produces (módulo `sebo_common`):
  - `VERSAO: str`; `class Enc(json.JSONEncoder)` (Decimal → int se inteiro, senão float)
  - `resposta(status: int, corpo: dict) -> dict` — `{"statusCode", "headers": {"Content-Type": "application/json"}, "body": <json str, ensure_ascii=False>}`
  - `agora() -> str` (ISO-8601 UTC)
  - `ler_corpo(event: dict) -> dict` — aceita `isBase64Encoded`; corpo ausente = `{}`; JSON inválido levanta `ValueError`
  - `normalizar_email(email: str) -> str` — `strip().lower()`
  - `email_valido(email: str) -> bool` — regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`
  - `publicar_email(sns, topic_arn: str, email: str, assunto: str, mensagem: str) -> str` — retorna `MessageId`; `Subject` truncado a 99 chars; `MessageAttributes={"emailCliente": {"DataType": "String", "StringValue": email}}`; imprime `SNS publish OK MessageId=<id> para=<email>`
  - `reservar_exemplar(tabela_livros, livro_id: str) -> bool` — `UpdateItem` `SET quantidade = quantidade - :um` com `ConditionExpression="quantidade >= :um"`; `True` se reservou, `False` em `ConditionalCheckFailedException`, demais erros propagam
- Produces (fixtures em `tests/unit/conftest.py`, usadas pelas Tasks 3–6):
  - `aws` → dict `{"livros", "interesses", "vendas"}` de `Table` criadas sob `moto.mock_aws` a partir de `infra/tabela_*.json`; define env `AWS_DEFAULT_REGION=us-east-1`, credenciais falsas, `TABELA_*` e `SNS_TOPIC_ARN="arn:aws:sns:us-east-1:123456789012:sebo-notificacoes"`
  - `fake_sns` → objeto com `.chamadas: list[dict]` (kwargs de cada `publish`), `.falhar: bool` (se `True`, `publish` levanta `RuntimeError("sns down")`), `publish(**kw)` retorna `{"MessageId": f"m-{n}"}` (n a partir de 1)
  - `carregar_lambda(nome: str) -> ModuleType` — importa `lambdas/<nome>/app.py` do zero (depende de `aws`) e, se o módulo tiver `sns`, troca por `fake_sns`
  - `evento(corpo: dict | str | None = None, query: dict | None = None) -> dict` — evento Function URL (corpo dict vira JSON string)
  - `layers/sebo_common/python` entra no `sys.path`.

- [ ] **Step 1: Criar os 3 JSONs de schema** (formato `aws dynamodb create-table --cli-input-json`: `TableName`, `AttributeDefinitions`, `KeySchema`, `BillingMode`, e `GlobalSecondaryIndexes` em `sebo-Interesses`) conforme Global Constraints.
- [ ] **Step 2: Escrever os testes que falham** em `tests/unit/test_sebo_common.py`:

```python
def test_resposta_converte_decimal():
    r = resposta(200, {"preco": Decimal("2.5"), "qtd": Decimal("3")})
    assert r["statusCode"] == 200 and r["headers"]["Content-Type"] == "application/json"
    assert json.loads(r["body"]) == {"preco": 2.5, "qtd": 3}

def test_ler_corpo_base64_ausente_e_invalido():
    ev = {"body": base64.b64encode(b'{"a":1}').decode(), "isBase64Encoded": True}
    assert ler_corpo(ev) == {"a": 1}
    assert ler_corpo({}) == {}
    with pytest.raises(ValueError):
        ler_corpo({"body": "{"})

def test_normalizar_e_validar_email():            # Review Focus 1
    assert normalizar_email("  Ana@Exemplo.COM ") == "ana@exemplo.com"
    assert email_valido("a@b.co")
    assert not email_valido("") and not email_valido("a@b") and not email_valido("a b@c.com")

def test_publicar_email_envia_atributo_e_trunca_assunto(fake_sns):
    mid = publicar_email(fake_sns, "arn:t", "a@b.co", "x" * 200, "Msg")
    c = fake_sns.chamadas[0]
    assert mid == "m-1" and c["TopicArn"] == "arn:t" and len(c["Subject"]) == 99
    assert c["MessageAttributes"]["emailCliente"] == {"DataType": "String", "StringValue": "a@b.co"}

def test_reservar_exemplar_nunca_fica_negativo(aws):
    t = aws["livros"]; t.put_item(Item={"livroId": "L1", "quantidade": 1})
    assert reservar_exemplar(t, "L1") is True
    assert reservar_exemplar(t, "L1") is False
    assert t.get_item(Key={"livroId": "L1"})["Item"]["quantidade"] == 0
```
- [ ] **Step 3: Rodar e ver falhar:** `pytest tests/unit/test_sebo_common.py -v` → Expected: erro de import (`sebo_common` / fixtures inexistentes).
- [ ] **Step 4: Implementar `conftest.py` e o módulo `sebo_common`** conforme o bloco Interfaces (única escolha em aberto: `fake_sns` pode ser uma classe simples).
- [ ] **Step 5: Rodar:** `pytest tests/unit/test_sebo_common.py -v` → Expected: 5 passed.
- [ ] **Step 6: Commit**
```bash
git add layers infra tests/unit
git commit -m "feat: layer sebo-common, schemas das tabelas e fixtures de teste"
```

---

### Task 3: Lambda `sebo-listar-livros`

**Files:**
- Create: `lambdas/listar_livros/app.py`
- Test: `tests/unit/test_listar_livros.py`

**Interfaces:**
- Consumes: `sebo_common.resposta`; fixtures `aws`, `carregar_lambda`, `evento`.
- Produces: `lambda_handler(event: dict, context) -> dict`. `GET ?recurso=livros|interesses|vendas` (padrão `livros`) → `200 {"recurso", "total": int, "itens": list}`; recurso desconhecido → `400 {"erro": ...}`. Tabela por `TABELA_LIVROS|TABELA_INTERESSES|TABELA_VENDAS`. `livros` ordenados por `titulo` (case-insensitive); `interesses`/`vendas` por `dataCriacao`/`dataVenda` decrescente. `Scan` com paginação (`LastEvaluatedKey`).

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_recurso_invalido_400(aws, carregar_lambda, evento):
    r = carregar_lambda("listar_livros").lambda_handler(evento(query={"recurso": "x"}), None)
    assert r["statusCode"] == 400

def test_tabela_vazia_200_total_zero(aws, carregar_lambda, evento):
    r = carregar_lambda("listar_livros").lambda_handler(evento(), None)
    assert r["statusCode"] == 200 and json.loads(r["body"]) == {"recurso": "livros", "total": 0, "itens": []}

def test_livros_ordenados_e_decimal_serializado(aws, carregar_lambda, evento):
    aws["livros"].put_item(Item={"livroId": "2", "titulo": "bravo", "preco": Decimal("25.9"), "quantidade": 1})
    aws["livros"].put_item(Item={"livroId": "1", "titulo": "Alfa", "preco": Decimal("10"), "quantidade": 0})
    corpo = json.loads(carregar_lambda("listar_livros").lambda_handler(evento(), None)["body"])
    assert [i["titulo"] for i in corpo["itens"]] == ["Alfa", "bravo"]
    assert corpo["itens"][1]["preco"] == 25.9 and corpo["total"] == 2
```
- [ ] **Step 2: Rodar e ver falhar:** `pytest tests/unit/test_listar_livros.py -v` → Expected: FAIL (arquivo `app.py` não existe).
- [ ] **Step 3: Implementar `lambda_handler`** em `lambdas/listar_livros/app.py` (`from sebo_common import resposta`; helper `varrer(tabela) -> list` com paginação).
- [ ] **Step 4: Rodar:** → Expected: 3 passed.
- [ ] **Step 5: Commit**
```bash
git add lambdas/listar_livros tests/unit/test_listar_livros.py
git commit -m "feat: lambda sebo-listar-livros"
```

---

### Task 4: Lambda `sebo-solicitar-livro`

**Files:**
- Create: `lambdas/solicitar_livro/app.py`
- Test: `tests/unit/test_solicitar_livro.py`

**Interfaces:**
- Consumes: `sebo_common.{resposta, agora, ler_corpo, normalizar_email, email_valido, publicar_email, reservar_exemplar}`; módulo-nível `sns = boto3.client("sns")` (as fixtures o substituem).
- Produces: `lambda_handler(event, context) -> dict`. `POST {"livroId", "emailCliente", "nomeCliente"?}`:
  - `200 {"mensagem", "disponivel": bool, "status": "RESERVADO"|"PENDENTE", "interesseId": str, "emailEnviado": bool}`
  - `400` (JSON inválido, `livroId` vazio, e-mail inválido), `404` (livro inexistente), `409 {"erro"}` (cliente já tem interesse `PENDENTE`/`RESERVADO` no mesmo livro).
  - Item gravado em `sebo-Interesses`: `interesseId` (uuid4), `livroId`, `titulo`, `emailCliente` (normalizado), `nomeCliente` (padrão `"Cliente"`), `status`, `dataCriacao`, `dataAtualizacao`, e `dataNotificacao` só se o e-mail foi enviado.

- [ ] **Step 1: Escrever os testes que falham** (livro semente: `{"livroId":"L1","titulo":"Dom Casmurro","quantidade":1,"preco":Decimal("25.90")}`; helper `pedir(mod, evento, **corpo)` chama o handler e devolve `(status, dict)`):

```python
def test_disponivel_reserva_e_notifica(aws, fake_sns, ...):
    s, d = pedir(mod, evento, livroId="L1", emailCliente="ana@exemplo.com", nomeCliente="Ana")
    assert s == 200 and d["status"] == "RESERVADO" and d["disponivel"] and d["emailEnviado"]
    assert aws["livros"].get_item(Key={"livroId": "L1"})["Item"]["quantidade"] == 0
    assert aws["interesses"].get_item(Key={"interesseId": d["interesseId"]})["Item"]["status"] == "RESERVADO"
    assert fake_sns.chamadas[0]["MessageAttributes"]["emailCliente"]["StringValue"] == "ana@exemplo.com"

def test_indisponivel_fica_pendente_sem_email(...):   # quantidade 0
    assert (s, d["status"], d["emailEnviado"]) == (200, "PENDENTE", False) and fake_sns.chamadas == []

def test_inexistente_404_e_entradas_invalidas_400(...):
    assert pedir(..., livroId="X", emailCliente="a@b.co")[0] == 404
    assert pedir(..., livroId="L1", emailCliente="")[0] == 400
    assert pedir(..., livroId="", emailCliente="a@b.co")[0] == 400
    assert mod.lambda_handler(evento("{"), None)["statusCode"] == 400

def test_email_e_normalizado(...):                    # Review Focus 1
    s, d = pedir(..., livroId="L1", emailCliente=" Ana@Exemplo.COM ")
    assert fake_sns.chamadas[0]["MessageAttributes"]["emailCliente"]["StringValue"] == "ana@exemplo.com"
    assert aws["interesses"].get_item(Key={"interesseId": d["interesseId"]})["Item"]["emailCliente"] == "ana@exemplo.com"

def test_pedido_duplicado_409_sem_consumir_estoque(...):   # Review Focus 2 (estoque inicial 2)
    assert pedir(..., livroId="L1", emailCliente="a@b.co")[0] == 200
    assert pedir(..., livroId="L1", emailCliente="a@b.co")[0] == 409
    assert aws["livros"].get_item(Key={"livroId": "L1"})["Item"]["quantidade"] == 1

def test_falha_no_sns_mantem_reserva(...):                 # Review Focus 4
    fake_sns.falhar = True
    s, d = pedir(..., livroId="L1", emailCliente="a@b.co")
    assert s == 200 and d["emailEnviado"] is False and d["status"] == "RESERVADO"
    assert aws["interesses"].get_item(Key={"interesseId": d["interesseId"]})["Item"]["status"] == "RESERVADO"
```
- [ ] **Step 2: Rodar e ver falhar:** `pytest tests/unit/test_solicitar_livro.py -v` → Expected: FAIL (`app.py` inexistente).
- [ ] **Step 3: Implementar `lambda_handler`.** Ordem fixa: validar entrada (400) → `get_item` do livro (404) → checar duplicado consultando o GSI `livroId-status-index` para `PENDENTE` e `RESERVADO` e filtrando `emailCliente` (409) → `reservar_exemplar` → `put_item` do interesse → se reservou, `publicar_email` dentro de `try/except Exception` (loga `ERRO ao publicar no SNS: ...`) e, em sucesso, `update_item` setando `dataNotificacao`. Mensagem do e-mail: assunto `Sebo: '<titulo>' está disponível!`; corpo pede para **comparecer à livraria para efetivar a compra** e traz o código da reserva (`interesseId`).
- [ ] **Step 4: Rodar:** → Expected: 6 passed.
- [ ] **Step 5: Commit**
```bash
git add lambdas/solicitar_livro tests/unit/test_solicitar_livro.py
git commit -m "feat: lambda sebo-solicitar-livro (reserva atômica, dedupe, falha de SNS)"
```

---

### Task 5: Lambda `sebo-cadastrar-livro` (chegada de livros e fila de espera)

**Files:**
- Create: `lambdas/cadastrar_livro/app.py`
- Test: `tests/unit/test_cadastrar_livro.py`

**Interfaces:**
- Consumes: `sebo_common.{resposta, agora, ler_corpo, publicar_email, reservar_exemplar}`; `sns` módulo-nível; GSI `livroId-status-index`.
- Produces: `lambda_handler(event, context) -> dict`. `POST {"livroId"?, "titulo", "autor", "quantidade": int>=1, "preco": número>=0, "ano"?, "condicao"?}`:
  - `200 {"mensagem", "livro": {...ALL_NEW}, "clientesNotificados": int, "emailsNotificados": list[str]}`
  - `400` para JSON inválido, `titulo`/`autor` vazios, `quantidade` < 1 ou não numérica, `preco` negativo ou não numérico.
  - `livroId` ausente → gera `LIV-<8 hex maiúsculos>`. `preco` gravado como `Decimal(str(preco))`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_cria_livro_novo_gera_id(...):
    s, d = cadastrar(mod, evento, titulo="O Alienista", autor="Machado", quantidade=3, preco=18)
    assert s == 200 and d["livro"]["livroId"].startswith("LIV-") and d["livro"]["quantidade"] == 3
    assert d["clientesNotificados"] == 0

def test_soma_exemplares_se_ja_existe(...):            # existente com quantidade 1
    s, d = cadastrar(..., livroId="L1", titulo="T", autor="A", quantidade=2, preco=10)
    assert d["livro"]["quantidade"] == 3

def test_chegada_atende_fila_fifo_ate_o_estoque(...):  # Review Focus 3
    # 3 interesses PENDENTE de L1: dataCriacao "2026-01-01", "2026-01-02", "2026-01-03" (a@x.com, b@x.com, c@x.com); estoque L1 = 0
    s, d = cadastrar(..., livroId="L1", titulo="T", autor="A", quantidade=2, preco=10)
    assert d["clientesNotificados"] == 2 and d["emailsNotificados"] == ["a@x.com", "b@x.com"]
    assert status_de("c@x.com") == "PENDENTE" and status_de("a@x.com") == "RESERVADO"
    assert aws["livros"].get_item(Key={"livroId": "L1"})["Item"]["quantidade"] == 0
    assert len(fake_sns.chamadas) == 2

def test_falha_no_sns_nao_perde_reserva(...):          # Review Focus 4 (1 pendente, fake_sns.falhar = True)
    s, d = cadastrar(..., livroId="L1", titulo="T", autor="A", quantidade=1, preco=10)
    assert s == 200 and d["clientesNotificados"] == 0 and status_de("a@x.com") == "RESERVADO"

@pytest.mark.parametrize("corpo", [
    dict(titulo="T", autor="A", quantidade=0, preco=1), dict(titulo="", autor="A", quantidade=1, preco=1),
    dict(titulo="T", autor="A", quantidade=1, preco=-1), dict(titulo="T", autor="A", quantidade="abc", preco=1)])
def test_validacoes_400(..., corpo):
    assert cadastrar(..., **corpo)[0] == 400
```
- [ ] **Step 2: Rodar e ver falhar:** `pytest tests/unit/test_cadastrar_livro.py -v` → Expected: FAIL.
- [ ] **Step 3: Implementar `lambda_handler`.** Ordem: validar → `update_item` com `SET titulo, autor, preco, ano, condicao ADD quantidade :q` (`ReturnValues="ALL_NEW"`) → consultar GSI (`livroId` + `status = PENDENTE`), ordenar por `dataCriacao` crescente → para cada pendente: `reservar_exemplar` (se `False`, **parar**), `update_item` do interesse para `RESERVADO` com `dataAtualizacao`/`dataNotificacao`, `publicar_email` em `try/except` (só conta em `emailsNotificados` se enviou). E-mail: assunto `Sebo: '<titulo>' acabou de chegar!`, corpo pedindo para comparecer à livraria.
- [ ] **Step 4: Rodar:** → Expected: 8 passed (4 testes + 4 parametrizações).
- [ ] **Step 5: Commit**
```bash
git add lambdas/cadastrar_livro tests/unit/test_cadastrar_livro.py
git commit -m "feat: lambda sebo-cadastrar-livro (chegada atende fila FIFO)"
```

---

### Task 6: Lambda `sebo-efetivar-venda`

**Files:**
- Create: `lambdas/efetivar_venda/app.py`
- Test: `tests/unit/test_efetivar_venda.py`

**Interfaces:**
- Consumes: `sebo_common.{resposta, agora, ler_corpo}`; tabelas `livros`, `interesses`, `vendas`.
- Produces: `lambda_handler(event, context) -> dict`. `POST {"interesseId"}` → `200 {"mensagem", "venda": {vendaId, interesseId, livroId, titulo, emailCliente, valor, dataVenda}, "status": "VENDIDO"}`; `400` (JSON inválido/`interesseId` vazio); `404` (inexistente); `409 {"erro", "statusAtual"}` se o interesse não está `RESERVADO` (transição condicional `#s = :atual`). `valor` = `preco` do livro.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_venda_ok_grava_venda_e_marca_vendido(...):    # interesse RESERVADO de L1 (preco 25.90)
    s, d = vender(mod, evento, interesseId="I1")
    assert s == 200 and d["status"] == "VENDIDO" and d["venda"]["valor"] == 25.9
    assert aws["interesses"].get_item(Key={"interesseId": "I1"})["Item"]["status"] == "VENDIDO"
    assert aws["vendas"].scan()["Count"] == 1

def test_vender_duas_vezes_409(...):
    assert vender(..., interesseId="I1")[0] == 200
    s, d = vender(..., interesseId="I1")
    assert s == 409 and d["statusAtual"] == "VENDIDO" and aws["vendas"].scan()["Count"] == 1

def test_pendente_nao_pode_ser_vendido_409(...):      # interesse PENDENTE
    assert vender(..., interesseId="I2")[0] == 409

def test_inexistente_404_e_vazio_400(...):
    assert vender(..., interesseId="nao-existe")[0] == 404
    assert vender(..., interesseId="")[0] == 400
```
- [ ] **Step 2: Rodar e ver falhar:** `pytest tests/unit/test_efetivar_venda.py -v` → Expected: FAIL.
- [ ] **Step 3: Implementar `lambda_handler`**: `get_item` (404) → `update_item` condicional para `VENDIDO` (`ConditionalCheckFailedException` → 409 com `statusAtual`) → `get_item` do livro para o `preco` → `put_item` em `sebo-Vendas` (`vendaId` uuid4).
- [ ] **Step 4: Rodar a suíte inteira:** `pytest tests/unit -v` → Expected: todos passam.
- [ ] **Step 5: Commit**
```bash
git add lambdas/efetivar_venda tests/unit/test_efetivar_venda.py
git commit -m "feat: lambda sebo-efetivar-venda"
```

---

### Task 7: Interface web (cliente e colaborador)

**Files:**
- Create: `frontend/util.js`, `frontend/index.html`, `frontend/app.js`
- Test: `frontend/util.test.js`

**Interfaces:**
- Consumes: `window.SEBO_CONFIG = {URL_LISTAR, URL_SOLICITAR, URL_CADASTRAR, URL_EFETIVAR}` (gerado na Task 9) e os contratos HTTP das Tasks 3–6.
- Produces: `util.js` exporta `esc(s: any) -> string`, `moeda(v: number) -> string` (pt-BR/BRL), `dt(iso: string) -> string` (CommonJS **e** `window.SeboUtil`). A UI tem duas abas: **Cliente** (catálogo, escolher livro, formulário nome/e-mail → `POST URL_SOLICITAR`, mensagem de resultado) e **Colaborador** (cadastrar/registrar chegada → `POST URL_CADASTRAR`; estoque; interesses com botão "Efetivar venda" só para `RESERVADO` → `POST URL_EFETIVAR`; vendas). Listagens via `GET URL_LISTAR + "?recurso=..."`.

- [ ] **Step 1: Escrever os testes que falham** (`node:test`):

```js
const test = require("node:test"), assert = require("node:assert");
const { esc, moeda } = require("./util.js");
test("esc neutraliza HTML", () => {                       // Review Focus 5
  assert.strictEqual(esc("<script>alert(1)</script>"), "&lt;script&gt;alert(1)&lt;/script&gt;");
  assert.strictEqual(esc(`"'&`), "&quot;&#39;&amp;");
  assert.strictEqual(esc(null), ""); assert.strictEqual(esc(undefined), "");
});
test("moeda formata em reais", () => assert.match(moeda(25.9), /25,90/));
```
- [ ] **Step 2: Rodar e ver falhar:** `node --test frontend/` → Expected: FAIL (`./util.js` inexistente).
- [ ] **Step 3: Implementar `util.js`** e depois `index.html` + `app.js`. Regra obrigatória: **todo** valor vindo da API passa por `esc()` antes de entrar em `innerHTML`; falha de rede/CORS vira mensagem na tela (não exceção muda); recarregar listas após cada ação.
- [ ] **Step 4: Rodar:** `node --test frontend/` → Expected: 2 passed. `cd frontend && python3 -m http.server 8080 & sleep 1; curl -sI http://localhost:8080/index.html | head -1` → Expected: `HTTP/1.0 200 OK` (depois `kill %1`).
- [ ] **Step 5: Commit**
```bash
git add frontend/util.js frontend/util.test.js frontend/index.html frontend/app.js
git commit -m "feat: interface web cliente/colaborador com escape de HTML"
```

---

### Task 8: Infraestrutura de dados (DynamoDB + SNS) e dados de teste

**Files:**
- Create: `scripts/01_dados.sh`, `seed.sh`, `reset_dados.sh`, `tests/e2e/conftest.py`, `pytest.ini`
- Test: `tests/e2e/test_infra.py`

**Interfaces:**
- Consumes: `infra/tabela_*.json` (Task 2); `config.env`.
- Produces:
  - `scripts/01_dados.sh` — idempotente: cria cada tabela só se `describe-table` falhar (`aws dynamodb create-table --cli-input-json file://infra/tabela_X.json`), `aws dynamodb wait table-exists`, `aws sns create-topic --name sebo-notificacoes`, e para cada e-mail de `EMAILS_ASSINANTES` um `sns subscribe --protocol email` com `--attributes` contendo `FilterPolicy` (JSON dentro de string, gerado via `python3 json.dumps` — não escrever à mão).
  - `seed.sh` — `put-item` dos livros: `SEED-001` "Dom Casmurro" qtd 2; `SEED-002` "Grande Sertão: Veredas" qtd 1; `SEED-003` "O Alienista" qtd 0; `SEED-004` "Capitães da Areia" qtd 0 (todos com `autor`, `ano`, `condicao`, `preco`).
  - `reset_dados.sh` — esvazia `sebo-Interesses` e `sebo-Vendas` (scan + delete-item) e roda `seed.sh`.
  - `pytest.ini` com marcador `e2e`; `tests/e2e/conftest.py` pula tudo sem `RUN_E2E=1` e fornece fixtures: `cfg` (dict de `config.env`), `urls` (dict de `frontend/config.js`), `dynamodb_client`, `sns_client`, `lambda_client`, `logs_client`, `http(metodo, url, corpo=None) -> (status, dict)` (urllib, sem dependências) e `esperar_log(grupo: str, padrao: str, desde_ms: int, timeout: int = 40) -> bool`.

- [ ] **Step 1: Escrever os testes que falham** (`@pytest.mark.e2e`):

```python
def test_tabelas_e_gsi_ativos(dynamodb_client):
    for nome in ("sebo-Livros", "sebo-Interesses", "sebo-Vendas"):
        assert dynamodb_client.describe_table(TableName=nome)["Table"]["TableStatus"] == "ACTIVE"
    gsis = dynamodb_client.describe_table(TableName="sebo-Interesses")["Table"]["GlobalSecondaryIndexes"]
    assert [(g["IndexName"], g["IndexStatus"]) for g in gsis] == [("livroId-status-index", "ACTIVE")]

def test_topico_e_assinaturas(sns_client, cfg):
    arn = next(t["TopicArn"] for t in sns_client.list_topics()["Topics"] if t["TopicArn"].endswith(":sebo-notificacoes"))
    endpoints = {s["Endpoint"] for s in sns_client.list_subscriptions_by_topic(TopicArn=arn)["Subscriptions"]}
    assert set(cfg["EMAILS_ASSINANTES"].split()) <= endpoints

def test_reset_deixa_4_livros_do_seed(dynamodb_client):
    subprocess.run(["bash", "reset_dados.sh"], check=True)
    itens = dynamodb_client.scan(TableName="sebo-Livros")["Items"]
    assert {i["livroId"]["S"]: int(i["quantidade"]["N"]) for i in itens} == {"SEED-001": 2, "SEED-002": 1, "SEED-003": 0, "SEED-004": 0}
```
- [ ] **Step 2: Rodar e ver falhar:** `RUN_E2E=1 pytest -m e2e tests/e2e/test_infra.py -v` → Expected: FAIL (tabelas não existem).
- [ ] **Step 3: Implementar `01_dados.sh`, `seed.sh`, `reset_dados.sh`, `pytest.ini`, `tests/e2e/conftest.py`**; executar `bash scripts/01_dados.sh && bash seed.sh`.
- [ ] **Step 4: Rodar duas vezes `bash scripts/01_dados.sh`** → Expected: segunda execução sem erro (idempotente). Rodar os testes → Expected: 3 passed.
- [ ] **Step 5: Ponto H3:** avisar o humano para confirmar as assinaturas; verificar `aws sns list-subscriptions-by-topic --topic-arn <arn> --query 'Subscriptions[].SubscriptionArn'` (enquanto `PendingConfirmation`, seguir para a Task 9 e voltar na Task 10).
- [ ] **Step 6: Commit**
```bash
git add scripts/01_dados.sh seed.sh reset_dados.sh pytest.ini tests/e2e
git commit -m "feat: infra de dados (DynamoDB, SNS com filter policy) e seed"
```

---

### Task 9: Layer + Lambdas + Function URLs (deploy)

**Files:**
- Create: `scripts/02_lambdas.sh`, `deploy.sh`
- Modify: `tests/e2e/test_infra.py`

**Interfaces:**
- Consumes: Tasks 2–6 (código), Task 8 (tabelas e tópico).
- Produces: `deploy.sh` (roda `check_env.sh` → `01_dados.sh` → `02_lambdas.sh`); `frontend/config.js` com `window.SEBO_CONFIG = {URL_LISTAR, URL_SOLICITAR, URL_CADASTRAR, URL_EFETIVAR}` (as 4 Function URLs); Layer `sebo-common` publicada e anexada às 4 funções.

- [ ] **Step 1: Escrever os testes que falham** (acrescentar em `test_infra.py`):

```python
FUNCOES = ("listar-livros", "solicitar-livro", "cadastrar-livro", "efetivar-venda")

def test_layer_anexada_as_quatro_lambdas(lambda_client):
    for f in FUNCOES:
        arns = [l["Arn"] for l in lambda_client.get_function_configuration(FunctionName=f"sebo-{f}").get("Layers", [])]
        assert any(":layer:sebo-common:" in a for a in arns), f

def test_function_url_listar_responde_com_cors(urls):
    req = urllib.request.Request(urls["URL_LISTAR"] + "?recurso=livros", headers={"Origin": "http://localhost:8080"})
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.status == 200 and r.headers["access-control-allow-origin"]
        assert json.loads(r.read())["total"] == 4

def test_deploy_idempotente_nao_publica_layer_nova(lambda_client):
    antes = lambda_client.list_layer_versions(LayerName="sebo-common")["LayerVersions"][0]["Version"]
    subprocess.run(["bash", "deploy.sh"], check=True)
    assert lambda_client.list_layer_versions(LayerName="sebo-common")["LayerVersions"][0]["Version"] == antes
```
- [ ] **Step 2: Rodar e ver falhar:** `RUN_E2E=1 pytest -m e2e tests/e2e/test_infra.py -k "layer or url or deploy" -v` → Expected: FAIL (funções inexistentes).
- [ ] **Step 3: Implementar `scripts/02_lambdas.sh` e `deploy.sh`.** Decisões que não são óbvias (seguir à risca):
  - `ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/LabRole"`, `ACCOUNT_ID` via `sts get-caller-identity`; `mkdir -p build`.
  - **Layer:** hash SHA-256 (32 primeiros hex) dos `*.py` de `layers/sebo_common` (caminho + conteúdo, ordenados) gravado em `--description`; se `list-layer-versions` já tem versão mais recente com essa descrição, **reutiliza** o `LayerVersionArn`; senão `rm -f build/layer.zip; (cd layers/sebo_common && python3 -m zipfile -c ../../build/layer.zip python)` e `aws lambda publish-layer-version --layer-name sebo-common --description <hash> --zip-file fileb://build/layer.zip --compatible-runtimes python3.12 --query LayerVersionArn --output text`.
  - **Funções** (para `listar_livros solicitar_livro cadastrar_livro efetivar_venda` → nome `sebo-${d//_/-}`): zip só do `app.py` (`python3 -m zipfile -c`); se existe → `update-function-code`, `wait function-updated`, `update-function-configuration --environment ... --layers "$LAYER_ARN" --timeout 15`, `wait function-updated`; senão `create-function --runtime python3.12 --role $ROLE_ARN --handler app.lambda_handler --layers "$LAYER_ARN" --timeout 15 --memory-size 256 --environment "Variables={TABELA_LIVROS=sebo-Livros,TABELA_INTERESSES=sebo-Interesses,TABELA_VENDAS=sebo-Vendas,SNS_TOPIC_ARN=$TOPIC_ARN}"`, `wait function-active`. `TOPIC_ARN` vem de `aws sns create-topic --name sebo-notificacoes` (idempotente).
  - **Function URL** (create ou update): `--auth-type NONE --cors '{"AllowOrigins":["*"],"AllowMethods":["*"],"AllowHeaders":["content-type"],"MaxAge":3600}'`, mais **duas** permissões, ignorando "já existe" (`|| true`):
    `add-permission --statement-id UrlPublicInvokeUrl --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE` e
    `add-permission --statement-id UrlPublicInvokeFn --action lambda:InvokeFunction --principal "*" --invoked-via-function-url`.
  - Gerar `frontend/config.js` com as 4 URLs (`get-function-url-config --query FunctionUrl`).
- [ ] **Step 3b: Verificação local rápida:** `python3 -m py_compile layers/sebo_common/python/sebo_common/__init__.py lambdas/*/app.py` → sem saída.
- [ ] **Step 4: Rodar** `bash deploy.sh` (1ª vez cria; ver `DEPLOY CONCLUÍDO`), `bash seed.sh`, e os testes do Step 2 → Expected: 3 passed. Se `No module named 'sebo_common'`: conferir `unzip -l build/layer.zip` (deve listar `python/sebo_common/__init__.py`) e `get-function-configuration ... --query Layers`.
- [ ] **Step 5: Commit**
```bash
git add scripts/02_lambdas.sh deploy.sh tests/e2e/test_infra.py
git commit -m "feat: deploy da layer, lambdas e function urls"
```

---

### Task 10: Testes de ponta a ponta e verificação de e-mail

**Files:**
- Create: `tests/e2e/test_fluxo.py`, `docs/resultados_testes.txt` (saída do pytest)

**Interfaces:**
- Consumes: fixtures e2e da Task 8, URLs da Task 9, `reset_dados.sh`.
- Produces: `docs/resultados_testes.txt` (fonte do "o que funcionou" do relatório) e a confirmação H3/H4.

- [ ] **Step 1: Escrever os testes** (fixture `limpo` roda `bash reset_dados.sh` antes de cada teste; `E = cfg["TEST_EMAIL"] or "teste@exemplo.com"`):

```python
def test_t1_disponivel_reserva_e_publica_no_sns(http, urls, esperar_log):   # esperar_log é fixture (callable)
    t0 = int(time.time() * 1000)
    s, d = http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-001", "emailCliente": E, "nomeCliente": "Teste"})
    assert s == 200 and d["status"] == "RESERVADO" and d["emailEnviado"] is True
    assert esperar_log("/aws/lambda/sebo-solicitar-livro", '"SNS publish OK"', t0)

def test_t2_indisponivel_fica_pendente(http, urls):
    s, d = http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-003", "emailCliente": E})
    assert (s, d["status"], d["emailEnviado"]) == (200, "PENDENTE", False)

def test_t3_chegada_notifica_pendente(http, urls):
    _, ped = http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-003", "emailCliente": E})
    s, d = http("POST", urls["URL_CADASTRAR"], {"livroId": "SEED-003", "titulo": "O Alienista", "autor": "Machado de Assis", "quantidade": 5, "preco": 18})
    assert s == 200 and d["clientesNotificados"] == 1
    ints = http("GET", urls["URL_LISTAR"] + "?recurso=interesses")[1]["itens"]
    assert next(i for i in ints if i["interesseId"] == ped["interesseId"])["status"] == "RESERVADO"

def test_t4_concorrencia_um_exemplar_seis_clientes(http, urls):       # SEED-002 tem 1 exemplar
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda i: http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-002", "emailCliente": f"cliente{i}@exemplo.com"}), range(6)))
    status = sorted(d["status"] for _, d in res)
    assert status == ["PENDENTE"] * 5 + ["RESERVADO"]
    livros = {l["livroId"]: l for l in http("GET", urls["URL_LISTAR"])[1]["itens"]}
    assert livros["SEED-002"]["quantidade"] == 0

def test_t5_erros_404_400_409(http, urls):
    assert http("POST", urls["URL_SOLICITAR"], {"livroId": "NAO-EXISTE", "emailCliente": E})[0] == 404
    assert http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-001", "emailCliente": ""})[0] == 400
    assert http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-001", "emailCliente": E})[0] == 200
    assert http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-001", "emailCliente": E})[0] == 409

def test_t6_efetivar_venda(http, urls):
    _, ped = http("POST", urls["URL_SOLICITAR"], {"livroId": "SEED-001", "emailCliente": E})
    assert http("POST", urls["URL_EFETIVAR"], {"interesseId": ped["interesseId"]})[0] == 200
    assert http("POST", urls["URL_EFETIVAR"], {"interesseId": ped["interesseId"]})[0] == 409
    assert http("GET", urls["URL_LISTAR"] + "?recurso=vendas")[1]["total"] == 1
```
- [ ] **Step 2: Rodar:** `RUN_E2E=1 pytest -m e2e tests/e2e -v | tee docs/resultados_testes.txt` → Expected: todos passam. Falha → ler `aws logs tail /aws/lambda/<função> --since 15m`, corrigir o código, `bash deploy.sh`, repetir.
- [ ] **Step 3: Verificar CORS da interface** com `curl -si -H "Origin: http://localhost:8080" "<URL_LISTAR>?recurso=livros" | grep -i access-control-allow-origin` → Expected: uma linha. Servir `frontend/` e confirmar que o catálogo lista os 4 livros do seed.
- [ ] **Step 4: H3/H4 — e-mails reais.** Confirmar que nenhuma assinatura do tópico está `PendingConfirmation`. Rodar `bash reset_dados.sh`, pedir `SEED-001` (e-mail "disponível") e depois `SEED-003` + cadastrar chegada (e-mail "chegou"); pedir ao humano para confirmar a chegada dos **2 e-mails** em `TEST_EMAIL`. Sem resposta, registrar "e-mails não validados" no relatório final; não bloquear as próximas tasks.
- [ ] **Step 5: Commit**
```bash
git add tests/e2e/test_fluxo.py docs/resultados_testes.txt
git commit -m "test: e2e do fluxo completo incluindo concorrência"
```

---

### Task 11: Documentação e diagramas

**Files:**
- Create: `README.md`, `docs/instalacao.md`, `docs/operacao.md`, `docs/relatorio.md`, `docs/diagramas.md`, `docs/prints_necessarios.md`
- Test: `tests/unit/test_docs.py`

**Interfaces:**
- Consumes: nomes reais de recursos, versão atual da layer, `docs/resultados_testes.txt`.
- Produces: documentação do enunciado em pt-BR.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_arquivos_obrigatorios_existem():
    for f in ("README.md", "docs/instalacao.md", "docs/operacao.md", "docs/relatorio.md", "docs/diagramas.md", "docs/prints_necessarios.md"):
        assert (RAIZ / f).is_file(), f

def test_relatorio_tem_secoes_do_enunciado():
    t = (RAIZ / "docs/relatorio.md").read_text(encoding="utf-8")
    for s in ("O que funcionou", "O que não funcionou", "Layer", "Diagrama em blocos", "Diagrama de sequência", "Divisão de trabalho"):
        assert s in t, s

def test_diagramas_mermaid():
    t = (RAIZ / "docs/diagramas.md").read_text(encoding="utf-8")
    assert t.count("```mermaid") >= 2 and "flowchart" in t and "sequenceDiagram" in t

def test_nenhum_segredo_no_repositorio():
    padrao = re.compile(r"AKIA[0-9A-Z]{16}|aws_secret_access_key|aws_session_token", re.I)
    for p in RAIZ.rglob("*"):
        if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts and p.suffix in {".md", ".sh", ".py", ".js", ".json", ".env", ".txt"} and p.name != "test_docs.py":
            assert not padrao.search(p.read_text(errors="ignore")), p
```
- [ ] **Step 2: Rodar e ver falhar:** `pytest tests/unit/test_docs.py -v` → Expected: FAIL (arquivos inexistentes).
- [ ] **Step 3: Escrever os documentos.** Conteúdo fixado:
  - **`docs/diagramas.md`** — (a) `flowchart LR`: Cliente/Colaborador → Interface Web → 4 Lambdas → DynamoDB (3 tabelas); `solicitar` e `cadastrar` → SNS → e-mail do cliente; Layer `sebo-common` tracejada para as 4 Lambdas. (b) `sequenceDiagram` com participantes Cliente, Colaborador, Interface, Lambda solicitar, Lambda cadastrar, Lambda efetivar, DynamoDB, SNS e três fluxos: **A/B** pedido (`alt` reserva atômica OK → RESERVADO + Publish + e-mail; senão → PENDENTE), **chegada** (ADD quantidade → consulta pendentes → `loop` FIFO: reservar, RESERVADO, Publish, e-mail), **C** venda (RESERVADO→VENDIDO condicional + put Vendas). Indicar renderização em mermaid.live.
  - **`docs/instalacao.md`** — pré-requisitos → exportar credenciais → editar `config.env` → `bash deploy.sh` (publica layer e Lambdas) → confirmar e-mails SNS → `bash seed.sh` → servir o frontend → `RUN_E2E=1 pytest -m e2e`; tabela de recursos reais (incl. layer e versão).
  - **`docs/operacao.md`** — (1) cliente pede livro disponível; (2) pede indisponível; (3) colaborador registra chegada; (4) efetiva venda; (5) `bash reset_dados.sh` antes da demo; (6) `aws logs tail /aws/lambda/<função> --since 15m`.
  - **`docs/relatorio.md`** — seções: Introdução; Arquitetura + **Diagrama em blocos**; Modelo de dados; Lambdas e **Layer `sebo-common`** (funções, `python/` na raiz, versionamento por hash, benefícios); Fluxo de e-mail (SNS + filter policy); Concorrência; **Diagrama de sequência**; **O que funcionou** (extraído de `docs/resultados_testes.txt`, citando T1–T6); **O que não funcionou** (somente o que ocorreu **mais** as limitações abaixo); **Divisão de trabalho** (`[preencher]`); Conclusão. Limitações conhecidas (copiar): Function URLs com auth `NONE` e interface do colaborador sem login · sem cancelamento/expiração de reservas (exemplar reservado e não vendido fica preso) · o SNS só entrega a quem confirmou a assinatura (a Lambda não cria assinaturas) · `Scan` nas listagens · GSI eventualmente consistente · checagem de pedido duplicado não é atômica sob requisições simultâneas idênticas.
  - **`docs/prints_necessarios.md`** — tabelas com itens; 4 Lambdas com layer anexada; Lambda → Layers; tópico SNS com assinaturas *Confirmed*; os 2 e-mails recebidos; as duas abas da interface; saída do pytest e2e.
  - **`README.md`** — resumo, tabela de recursos, links, comandos (`deploy`, `seed`, `reset`, testes) e a conta (`aws sts get-caller-identity --query Account`).
- [ ] **Step 4: Rodar:** `pytest tests/unit -v` → Expected: todos passam.
- [ ] **Step 5: Commit**
```bash
git add README.md docs tests/unit/test_docs.py
git commit -m "docs: instalação, operação, relatório e diagramas"
```

---

### Task 12: Estado final de entrega

**Files:**
- Modify: `docs/relatorio.md` (resultado final dos e-mails H4)

**Interfaces:**
- Consumes: tudo acima.
- Produces: ambiente limpo para a apresentação e a mensagem final ao humano.

- [ ] **Step 1: Verificação final:** `pytest tests/unit -q` e `node --test frontend/` → Expected: tudo verde; `RUN_E2E=1 pytest -m e2e tests/e2e/test_infra.py -q` → Expected: passam.
- [ ] **Step 2: Deixar limpo:** `bash reset_dados.sh` → Expected: `Dados resetados.`; `aws sns list-subscriptions-by-topic` → contar `Confirmed` vs. `PendingConfirmation`.
- [ ] **Step 3: Atualizar o relatório** com o status real de H4 (e-mails confirmados ou não).
- [ ] **Step 4: Commit**
```bash
git add docs/relatorio.md
git commit -m "docs: estado final e status dos e-mails"
```
- [ ] **Step 5: Enviar ao humano a mensagem final** neste formato:

```
✅ CONCLUÍDO
- Conta AWS: <id> · us-east-1
- Recursos: 4 Lambdas + Layer sebo-common v<N>, 3 tabelas DynamoDB, tópico SNS <arn>
- URLs das funções: (4 URLs)
- Testes: unit X passed · e2e Y passed (docs/resultados_testes.txt)
⏳ PENDENTE (humano)
- H3/H4: assinaturas SNS / e-mails recebidos [status]
- H5: prints (docs/prints_necessarios.md), divisão de trabalho, conta no EaD, apresentação
- Antes de apresentar: Start Lab e `bash reset_dados.sh`
⚠️ PROBLEMAS / DECISÕES: (lista honesta de docs/problemas.md)
```
