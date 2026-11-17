# Instalação

## 1. Pré-requisitos

- Python 3.12+ para desenvolvimento; as Lambdas usam runtime Python 3.12.
- Git Bash no Windows ou Bash no Linux/macOS/CloudShell.
- Node.js com `node:test` para testes JS.
- AWS Academy Learner Lab ativo para deploy, LabRole existente e acesso aos serviços Lambda, DynamoDB e SNS na região us-east-1.
- Caixa postal acessível para confirmar assinatura SNS e conferir os dois fluxos de e-mail.

Não são necessários Docker, EC2, RDS, NAT Gateway ou instalação de boto3 na layer. `boto3` é fornecido pelo runtime Lambda e instalado localmente apenas para desenvolvimento/automação.

## 2. Preparar o projeto

```bash
python3 -m venv .venv
# Windows / Git Bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
# Linux / macOS / CloudShell: use .venv/bin/python
```

Para experiência local sem conta AWS:

```bash
.venv/Scripts/python.exe tools/dev_server.py --port 8080
```

Abra `http://127.0.0.1:8080`. Todos os serviços AWS são emulados, os dados são voláteis e nenhum e-mail é entregue. Esse caminho não é a implantação exigida pelo professor.

## 3. Preparar o Learner Lab

1. Inicie o lab na AWS Academy e confirme a conta correta.
2. Pelo painel do lab, disponibilize as três credenciais temporárias na sessão do terminal usando as instruções do próprio lab. Não cole credenciais no chat e não as salve em arquivos do projeto.
3. Copie `config.env.example` para `config.env` e informe somente região/e-mails. O arquivo é ignorado pelo Git.
4. Rode `bash scripts/check_env.sh`. Credenciais ausentes/expiradas devem causar falha, nunca substituição por conta inventada.

O projeto não cria nem altera IAM. Usa o ARN da LabRole da conta consultada pelo STS. Negação de consulta IAM interrompe esta automação (decisão mais conservadora que o plano). Não autoriza criar outra role: é necessário resolver a permissão de leitura no Learner Lab, sem alterar IAM por este projeto.

## 4. Publicar

```bash
bash scripts/check_env.sh
bash deploy.sh
bash seed.sh --confirm
```

O deploy cria/reutiliza schemas de `infra/`, tópico `sebo-notificacoes`, assinaturas por e-mail, layer versionada por hash, quatro funções e suas Function URLs. Configura CORS no serviço e as duas permissões de invocação pública. O `frontend/config.js` gerado não deve ser editado com credenciais; ele contém apenas endpoints.

Os nomes de todos os recursos começam por `sebo-`. Registre os identificadores reais depois da execução; não confunda os nomes previstos com recursos já implantados.

| Recurso | Nome previsto | Identificador real nesta entrega |
|---|---|---|
| Conta | obtida via STS | Não validado |
| Layer | sebo-common | Versão AWS não publicada nesta sessão |
| Funções | sebo-listar-livros / solicitar-livro / cadastrar-livro / efetivar-venda | URLs dependem de deploy |
| Tabelas | sebo-Livros / sebo-Interesses / sebo-Vendas | Dependem de deploy |
| Tópico | sebo-notificacoes | ARN depende de deploy |

## 5. Confirmar assinaturas e servir interface AWS

1. Confirme os links enviados pelo SNS a cada e-mail configurado; confira spam.
2. Confira o filtro `emailCliente`, com valor minúsculo e sem espaços. Alterações podem levar até 15 minutos para propagar.
3. Sirva o diretório estático após deploy:

```bash
.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

Não use o servidor Moto para comprovar AWS. O frontend estático usa o `config.js` real do deploy. A hospedagem S3 não é obrigatória nesta solução; assim não é preciso abrir um bucket público no lab.

## 6. Verificar e entregar

```bash
.venv/Scripts/python.exe -m pytest tests/unit tests/local -q
node --test frontend/util.test.js
```

Os testes AWS são opt-in. Leia `tests/e2e/test_live.py` antes da execução:

```bash
# Somente leitura pública; exige manifesto de deploy real.
RUN_E2E=1 .venv/Scripts/python.exe -m pytest -m e2e tests/e2e -v
# Cria dados e pode enviar os dois avisos; exige TEST_EMAIL real configurado.
RUN_E2E=1 RUN_E2E_WRITES=1 .venv/Scripts/python.exe -m pytest -m e2e tests/e2e -v
```

Os registros E2E permanecem para auditoria; não há reset automático. Não rode reset em dados que precisam ser preservados. Publicação aceita pelo SNS não é comprovação de recebimento: confira os dois e-mails reais e atualize o relatório.

Entrega final: fontes, relatório/documentação, diagramas, conta informada no EaD e aplicação presente no lab. As notas são individuais: ambos precisam saber explicar todas as partes.
