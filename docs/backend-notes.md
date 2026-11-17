# Backend — contratos, verificação e limites

## Arquivos e integração

- Layer: `layers/sebo-common/python/sebo_common/__init__.py`. O ZIP deve conter **`python/sebo_common/__init__.py`**, sem `.venv`, `__pycache__`, boto3 ou outras dependências vendorizadas. O boto3 é fornecido pelo runtime Lambda.
- Entradas: `lambdas/sebo-listar-livros/app.py`, `lambdas/sebo-solicitar-livro/app.py`, `lambdas/sebo-cadastrar-livro/app.py`, `lambdas/sebo-efetivar-venda/app.py`. Cada ZIP tem `app.py` na raiz; handler `app.lambda_handler`, runtime **Python 3.12**.
- Env: `TABELA_LIVROS`, `TABELA_INTERESSES`, `TABELA_VENDAS`, `SNS_TOPIC_ARN`. Região esperada `us-east-1`. Somente a LabRole existente; nenhuma criação/alteração IAM.
- `infra/template.json` é CloudFormation opcional declarativo: tabelas on-demand, GSI ALL, tópico, layer, quatro funções, quatro URLs NONE com CORS na própria URL, permissões públicas restritas à invocação por URL e logs com retenção de 14 dias. Exige bucket de artefatos `sebo-*` já existente, ARN de LabRole e chaves S3 dos cinco ZIPs. Parâmetros: `LabRoleArn`, `ArtifactBucket`, `LayerKey`, `ListarKey`, `SolicitarKey`, `CadastrarKey`, `EfetivarKey`, `AllowedOrigins`. Outputs `ListarFunctionUrl`, `SolicitarFunctionUrl`, `CadastrarFunctionUrl`, `EfetivarFunctionUrl`, `SnsTopicArn`. Tabelas/tópico/logs usam Retain; não há teardown automático. Não aplicar o template sobre recursos homônimos criados por outro caminho sem importação/planejamento explícito.
- Nenhum recurso AWS foi criado, alterado ou implantado durante esta implementação.

## HTTP

O contrato do `AGENTS.md` está implementado. GET só em listar; POST nas outras três entradas. Método incorreto retorna **405**, header `Allow`; formato inválido retorna 400. Eventos HTTP API/Function URL e `httpMethod` são aceitos. Os handlers não devolvem headers CORS duplicados.

- `listar`: `?recurso=livros|interesses|vendas`; padrão livros. Resposta `{recurso,total,itens}`. Percorre **todas as páginas DynamoDB** via `LastEvaluatedKey`, agrega e ordena. Não implementa paginação HTTP/cursor de frontend: `total` é o tamanho da coleção agregada. Títulos case-insensitive crescentes; interesses/vendas por data e ID decrescentes. Esconde guards e `versao`.
- `solicitar`: normaliza trim/lowercase de email; interesse ativo repetido retorna 409. Retorna `disponivel`, `status`, `interesseId`, `emailEnviado`. Livro ausente retorna 404. Interesse sem estoque fica PENDENTE, sem aviso SNS. Nome é opcional.
- `cadastrar`: ID opcional `LIV-8HEX`; colisão de ID automático gera outro ID em vez de incrementar um livro distinto. ID explícito existente soma estoque e atualiza título/autor/preço; campos opcionais não enviados são preservados. Retorna estoque **após reservas**. `clientesNotificados` conta publicações SNS aceitas; `emailsNotificados` é a lista correspondente, não uma prova de entrega. Reservas cujo aviso falhou permanecem gravadas.
- `efetivar`: somente RESERVADO; 409 inclui `statusAtual`; inexistente/guard retorna 404. Venda salva o título e valor capturados **na reserva**, não o preço corrente de um cadastro posterior. Não abate estoque novamente. Após venda, o cliente pode abrir novo interesse.

Validação: JSON objeto, base64 estrito/UTF-8, corpo de até 100.000 caracteres antes da decodificação; bool não é número; quantidade inteira 1..1.000.000.000, estoque total até esse limite; preço finito não negativo até 999999999999.99 e representável no DynamoDB, sem arredondamento/truncamento silencioso (casas adicionais são preservadas). IDs ASCII alfanuméricos/`_`/`-`, até 80 caracteres; títulos/autores até 300; nome até 150; condição até 100; ano inteiro 1..9999. Textos vazios, controles ASCII e surrogates isolados são rejeitados. Email é validação sintática conservadora ASCII (não verifica existência/posse, não suporta endereço internacionalizado).

## Integridade

O backend usa **`boto3.client('dynamodb')` low-level** e `TypeSerializer`/`TypeDeserializer` explícitos. Não usar `boto3.resource(...).meta.client`: os hooks de resource podem remarshalar AttributeValues e invalidar transações.

1. **Solicitação:** uma transação grava livro com condição de versão (estoque e versão avançam juntos), interesse e guard determinístico `LOCK-SHA256(livroId + NUL + emailNormalizado)`. `attribute_not_exists` no guard torna o dedupe atômico. Guard não tem `livroId`/`status`, não entra no GSI e fica oculto no listar.
2. **Chegada:** lê livro/versão antes de scan fortemente consistente e paginado da tabela de interesses; escolhe PENDENTES por `(dataCriacao,interesseId)` crescente. Uma única transação atualiza estoque/versão e cada interesse selecionado com condição `status=PENDENTE`. Escritas concorrentes do backend no estoque/fila mudam a versão e forçam recálculo; não reutilizam exemplar.
3. **Venda:** uma transação muda interesse condicionado a RESERVADO, cria venda com condição de inexistência e remove guard condicionado ao dono. Falha de qualquer condição reverte as três ações.
4. Conflitos condicionais/de transação têm até **5 tentativas**, com pequeno backoff/jitter, sempre relendo estado. Outros erros AWS retornam 503 sem detalhes sensíveis. Token `ClientRequestToken` explícito por tentativa protege os retries internos daquela chamada do SDK.

### Limites que permanecem

- **FIFO não é garantia global de ordem de rede.** Scan consistente não é snapshot. A versão do livro valida a janela contra mutações feitas por este backend, e o FIFO é dos pendentes observados/confirmados, pela data gerada no servidor e desempate por ID. Uma invocação antiga ainda não confirmada pode entrar depois da chegada; relógios entre Lambdas também não estabelecem ordem linear global. Escritas manuais/externas que não avancem a versão podem quebrar essas premissas. Não editar diretamente tabelas em uso.
- Transação DynamoDB tem limite de 100 ações/4 MB. A chegada admite até **99 reservas** mais a gravação do livro. Se atenderia 100 ou mais pendentes, retorna **409 antes de qualquer gravação**, pedindo dividir a quantidade em lotes menores. Não faz commits parciais nem entrega sucesso parcial. Os schemas/limites de texto normais mantêm esses lotes pequenos, mas dados externos maiores ainda podem atingir 4 MB.
- Scans completos, agregação em memória e SNS sequencial são escolhas de laboratório, não desenho para grande escala; podem atingir custo, timeout e limite de resposta Function URL. O GSI exigido existe, mas é eventualmente consistente e não é usado como fonte de verdade para o FIFO. Listagens não são snapshot global.
- **Cadastro não tem chave de idempotência HTTP persistida** no contrato. Repetir POST após resposta perdida pode somar estoque novamente; consultar antes de repetir. Token transacional não resolve outra invocação HTTP. Solicitação duplicada responde 409; venda repetida responde 409/VENDIDO. Timeout/erro de transporte pode ter resultado ambíguo mesmo que o cliente receba 503; reconciliar via listagens.
- **DynamoDB + SNS não são uma transação distribuída.** Publicação acontece após commit. Falha/crash entre commit e publish pode deixar reserva sem aviso. Não há outbox, retry persistente, cancelamento nem expiração automática de reserva. Guard permanece enquanto PENDENTE/RESERVADO. Sucesso de publish significa aceitação, não entrega de email; falha de SNS não desfaz estoque/interesse.
- A assinatura email e confirmação do destinatário são externas a estes handlers. Configurar filtro exato por `emailCliente` minúsculo com `FilterPolicyScope=MessageAttributes`. Alterações de filtro podem levar até 15 minutos a propagar. Não há prova de assinatura, entrega ou recebimento nesta suíte moto.
- URLs **NONE** são públicas por exigência do laboratório: listagens incluem email/nome e operações administrativas não têm autenticação. CORS não é controle de acesso. **Não publicar como serviço de produção com dados pessoais.** Restringir origens no laboratório reduz exposição no navegador, mas não impede chamadas diretas. Logs do código registram ação/ID de interesse, sem email bruto, payload ou exceção AWS detalhada.
- Não há migração automática para interesses antigos sem guard/valor de reserva. Trabalhar com tabelas novas ou migrar de forma explícita; nunca resetar automaticamente.

## Verificação executada

Test-first observado antes da lógica de reserva/guard, FIFO/venda e correções de fronteira. Suíte real com pytest + moto, clientes boto3 e transações reais do emulador: reserva+interesse e venda+transição com rollback, falha condicional em chegada/venda, duplicatas e leituras concorrentes forçadas, estoque não negativo, duas chegadas/uma venda concorrentes, FIFO por data/desempate, SNS indisponível, valores inválidos/NaN/Infinity/bools/frações, base64, paginação de scan, colisão de ID, limites de lote, wrappers reais e contrato de infraestrutura.

Na corrida determinística, barreira força ambos os participantes a ler o mesmo estado e um mutex cerca somente `TransactWriteItems` no moto: isso evita atribuir ao emulador garantias de isolamento de produção que ele não simula. Não substitui teste de carga AWS.

Comandos na raiz, bash Windows:

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_backend*.py -q
# Resultado observado: 60 passed in 17.11s

# cfn-lint pode ser instalado em ambiente separado, sem integrar à layer:
C:/Users/Enzo/AppData/Local/hermes/cache/scratch/sebo-backend-venv/Scripts/cfn-lint.exe infra/template.json --regions us-east-1
# Resultado observado: exit 0, sem diagnósticos.
```

Os testes rodaram em Python **3.13** local. Parsing de todos os fontes do backend com gramática Python 3.12 foi validado; **execução no runtime AWS Python 3.12 ainda não foi realizada**. Template validado localmente com cfn-lint; nenhum `validate-template`/deploy/seed em conta AWS. Uma tentativa simultânea de instalação no `.venv` encontrou bloqueio de arquivo Windows; a suíte final usou o `.venv` coordenado já pronto. Ambiente scratch separado foi usado apenas para ferramentas locais.

Referências oficiais para revisão: DynamoDB transactions (`https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html`), Scan (`https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html`), Lambda URL permissões (`https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html`), filtros SNS (`https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html`).
