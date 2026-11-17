# Automação AWS Academy

Entrypoint: `scripts/sebo_deploy.py`. Execute com `.venv/Scripts/python.exe` no Windows ou `.venv/bin/python` no Linux/macOS. Os wrappers bash detectam ambos. Dependências vêm de `requirements.txt` na raiz; AWS CLI não é necessária.

```bash
bash scripts/run.sh --help
bash scripts/check_env.sh
bash scripts/run.sh package        # somente ZIPs locais, sem sessão AWS
bash deploy.sh                    # escreve AWS, somente quando autorizado
bash scripts/run.sh status        # somente readback AWS, sem corrigir recursos
bash seed.sh --confirm             # insere os quatro SEED-* somente se ausentes
bash reset_dados.sh --confirm      # APAGA TODOS OS ITENS das 3 tabelas
```

Não há comandos separados `dados`/`lambdas`: deploy reconcilia a sequência inteira e pode ser reexecutado após falha parcial. Nenhum rollback/teardown automático. Não executar AWS writes nesta sessão sem autorização nova e credenciais Lab verificadas.

## Configuração e contrato

- Copiar `config.env.example` para `config.env`; somente `REGION`, `TEST_EMAIL`, `EMAILS_ASSINANTES`. NÃO colocar credenciais nesse arquivo. Valores do ambiente sobrepõem os públicos do arquivo.
- Credenciais temporárias são fornecidas pelo usuário via cadeia padrão boto3. O script não instala, persiste, imprime nem configura credenciais.
- `check` verifica credenciais, STS em us-east-1 e `iam:GetRole` da `LabRole` da mesma conta. Não cria nem altera IAM. Se `GetRole` estiver bloqueado no Lab, falha explicitamente; não presume um ARN como se tivesse sido validado.
- Infraestrutura: três `infra/tabela_*.json` com `TableName`, `KeySchema`, `AttributeDefinitions`, `BillingMode=PAY_PER_REQUEST`; GSI de interesses conforme AGENTS.md. Schema existente incompatível falha sem remover tabela.
- Funções: `lambdas/sebo-listar-livros/app.py`, `sebo-solicitar-livro/app.py`, `sebo-cadastrar-livro/app.py`, `sebo-efetivar-venda/app.py`. A árvore alternativa `backend/` e nomes underscore sem prefixo também são reconhecidos. Uma única correspondência por função.
- Layer: um único `layers/**/sebo_common/__init__.py` (ou `backend/**/sebo_common/__init__.py`). ZIP final `python/sebo_common/...`, sem boto3/botocore, pycache ou tests. Somente fontes `.py`; dependências nativas não são empacotadas.
- Lambda Python 3.12, handler `app.lambda_handler`, LabRole existente, layer hash SHA256 reutilizado. Artefatos determinísticos e update de código só quando hash difere.
- `frontend/config.js` e `build/deployment.json` só são escritos após readbacks bem-sucedidos. Esses arquivos gerados devem estar ignorados pelo Git. O manifesto não contém credenciais; conta, ARNs e URLs são metadados públicos.

## SNS / Function URLs

- E-mails vazios significam **nenhuma assinatura**, nunca fallback fictício. Emails válidos são normalizados para minúsculas. Assinaturas recebem filtro exato `emailCliente`, escopo `MessageAttributes`.
- `subscribe(ReturnSubscriptionArn=True)` retorna ARN utilizável mesmo pendente; não se passa `PendingConfirmation` a `set_subscription_attributes`. A confirmação acontece manualmente na caixa do destinatário, nunca é forjada pela automação. Novo `subscribe` de pendentes pode reenviar convite; assinaturas confirmadas não são recriadas. Filtros inalterados não são regravados.
- SNS pode levar até 15 minutos para propagar filtros. Readback de atributos não prova propagação nem entrega. SNS Publish aceito não prova recebimento de e-mail.
- Function URLs `NONE` + CORS são públicas, **inclusive cadastro e venda**, e expõem listas com dados de clientes. Somente laboratório/demonstração, não produção.
- Duas permissões são reconciliadas: `lambda:InvokeFunctionUrl` com `FunctionUrlAuthType=NONE` e `lambda:InvokeFunction` restrito por `InvokedViaFunctionUrl=true`. Só SIDs próprios são substituídos; permissões preexistentes desconhecidas ficam preservadas e aparecem em `status` para auditoria.
- Se o Lab negar Function URLs, o script retorna a falha real. Não cria API Gateway, não modifica IAM, não esconde `AccessDenied` como recurso inexistente.
- SDK efetua retries próprios para falhas transitórias; deploy concorrente não é garantido. Execute uma instância por vez. Não há exclusão de layers antigas nem assinaturas antigas removidas da configuração.

## Segurança dos dados e limites

`seed` e `reset` exigem `--confirm` antes mesmo de criar sessão boto3. Reset é global nas três tabelas `sebo-`, usa paginação e verifica contagem consistente em todas as páginas; requer aplicação ociosa, sem escritores concorrentes. Sem lock global, escritores podem recriar dados depois do readback. Não existe cleanup automático de testes ou infraestrutura. Seed preserva itens existentes e insere condicionalmente os quatro livros de infra/livros_seed.json; reset não executa seed automaticamente.

Falhas parciais deixam recursos anteriores intactos e são reportadas; reexecutar deploy reconcilia o que falta. Não há transação entre serviços AWS. Nenhuma alegação de deploy, confirmação SNS ou entrega real é feita a partir dos doubles/moto.

## Testes

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_deploy*.py tests/e2e -q
```

Unitários usam somente arquivos temporários, moto, doubles ou Stubber com credenciais de teste explícitas, nunca AWS real. Cobrem packaging determinístico, prefixo, configuração sem segredos, confirmação antes de sessão, ausência de credenciais, propagação de AccessDenied, idempotência de dados/SNS/layer/Lambda e readbacks das duas permissões.

E2E fica **skipped** sem `RUN_E2E=1`. Precisa de manifesto gerado por deploy real. Só GET/listagens por padrão. Para fluxo que cria estoque/interesse/venda e pode enviar SNS, exigir também `RUN_E2E_WRITES=1` e `TEST_EMAIL` real controlado pelo usuário. Registros E2E permanecem para auditoria; não há reset automático. Testes de entrega de e-mail/propagação de filtros não são automatizados.

Referências oficiais consultadas: AWS Lambda Developer Guide, `urls-auth.html`; SNS API, `API_Subscribe.html`; SNS Developer Guide, políticas de filtro e consistência eventual.
