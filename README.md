# Sebo na Nuvem

Trabalho 2 de Distribuição e Concorrência — 2026/2.

**Enzo Abate — 2312936 · Lucca Sznaider — 2220504**

Aplicação de sebo com catálogo, interesse por livro, reserva, fila de espera, entrada de exemplares e registro de venda. A versão AWS usa quatro Lambdas Python 3.12, uma layer compartilhada, três tabelas DynamoDB e um tópico SNS com filtros por e-mail.

> **Situação da AWS:** não validado. Não há credenciais do Learner Lab disponíveis nesta sessão. A versão local usa os handlers reais com serviços emulados em memória; não envia e-mail. Testes locais não substituem implantação no AWS Academy.

## Executar localmente

Python 3.12 ou superior e Node.js com `node:test` para testes do frontend. No Windows, em Git Bash:

```bash
python3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe tools/dev_server.py --port 8080
```

No Linux/macOS/CloudShell, use `.venv/bin/python` no lugar de `.venv/Scripts/python.exe`.

Abra `http://127.0.0.1:8080`. O servidor local cria dados de demonstração em memória, executa as Lambdas reais e emula DynamoDB/SNS com Moto. Ctrl+C encerra e descarta os dados. Nenhum e-mail real é enviado.

## Testar

```bash
.venv/Scripts/python.exe -m pytest tests/unit tests/local -q
node --test frontend/util.test.js
```

Evidências e limitações: [relatório](docs/relatorio.md), [resultados](docs/resultados_testes.txt) e [problemas](docs/problemas.md).

Para repetir toda a verificação local, sem habilitar testes AWS: `.venv/Scripts/python.exe tools/verify.py`.

O [relatório completo em PDF](docs/relatorio-completo.pdf) reúne relatório, diagramas renderizados, instalação e operação. Para regenerar: instale `requirements-docs.txt` e execute `tools/render_docs.py`. É necessário Chrome ou Chromium do Playwright; a primeira geração baixa o renderizador Mermaid.

## Publicar na AWS Academy

1. Inicie o Learner Lab e disponibilize as credenciais temporárias **apenas no seu ambiente local**, nunca no chat, Git ou `config.env`.
2. Copie `config.env.example` para `config.env`; preencha os e-mails e mantenha `us-east-1`.
3. Rode os comandos abaixo no Bash. A automação usa boto3; AWS CLI não é obrigatório.

```bash
bash scripts/check_env.sh
bash deploy.sh
bash seed.sh --confirm
```

Confirme a assinatura SNS clicando no e-mail enviado pelo serviço. Aguarde a propagação do filtro antes de testar. Para a interface usar AWS, sirva somente `frontend/` com um servidor estático; o `config.js` gerado pelo deploy contém as URLs reais.

```bash
.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

`tools/dev_server.py` é **sempre local emulado**, mesmo após um deploy. Não o use para validar AWS.

## Recursos previstos

| Tipo | Nome |
|---|---|
| Lambda | sebo-listar-livros |
| Lambda | sebo-solicitar-livro |
| Lambda | sebo-cadastrar-livro |
| Lambda | sebo-efetivar-venda |
| Layer | sebo-common |
| DynamoDB | sebo-Livros, sebo-Interesses, sebo-Vendas |
| SNS | sebo-notificacoes |
| Região / role existente | us-east-1 / LabRole |

A automação não cria roles, não altera IAM e não remove recursos ao terminar. URLs `NONE` são públicas: esta versão acadêmica não deve receber dados sensíveis nem ser usada como aplicação de produção.

## Documentação

- [Instalação](docs/instalacao.md)
- [Operação e apresentação](docs/operacao.md)
- [Relatório](docs/relatorio.md)
- [Diagramas em blocos e sequência](docs/diagramas.md)
- [Evidências necessárias](docs/prints_necessarios.md)
- [Fontes](docs/fontes.md)
- [Enunciado original](docs/Trab2_2026_2.pdf)

A conta da AWS Academy deve ser informada no EaD **depois da implantação real**. A divisão de trabalho dos integrantes precisa ser preenchida pela dupla; não foi inventada.
