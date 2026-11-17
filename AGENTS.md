# Sebo na Nuvem — contrato de implementação

Dupla: Enzo Abate (2312936) e Lucca Sznaider (2220504). Enunciado: docs/Trab2_2026_2.pdf. Documentação em pt-BR. Implementação autorizada por Enzo.

## Escopo
AWS Academy Learner Lab, us-east-1, LabRole existente; nunca criar/alterar IAM. Recursos somente prefixo sebo-. Quatro Lambdas Python 3.12: sebo-listar-livros, sebo-solicitar-livro, sebo-cadastrar-livro, sebo-efetivar-venda. Handler app.lambda_handler. Layer sebo-common ZIP python/sebo_common/__init__.py sem boto3 vendorizado. Tabelas PAY_PER_REQUEST: sebo-Livros PK livroId, sebo-Interesses PK interesseId GSI livroId-status-index (livroId, status, ALL), sebo-Vendas PK vendaId. SNS sebo-notificacoes, atributo emailCliente minúsculo, assinatura email com filtro exato. Env: TABELA_LIVROS, TABELA_INTERESSES, TABELA_VENDAS, SNS_TOPIC_ARN. Function URLs NONE, CORS só na URL. Nenhum segredo em arquivos/log/chat. Nunca teardown automático. Sem claims de AWS ou e-mail validado sem evidência real.

## HTTP / interface
GET listar ?recurso=livros|interesses|vendas -> 200 {recurso,total,itens}; inválido 400. Ordenar títulos case-insensitive, demais datas decrescentes; paginar. Não expor itens internos de lock nas listagens.
POST solicitar {livroId,emailCliente,nomeCliente?} -> 200 {mensagem,disponivel,status:PENDENTE|RESERVADO,interesseId,emailEnviado}; inválido 400, livro ausente 404, ativo duplicado 409. Email normalizado. Falha SNS mantém reserva, emailEnviado=false; publicação aceita NÃO significa entregue.
POST cadastrar {livroId?,titulo,autor,quantidade:int>=1,preco:number>=0,ano?,condicao?} -> 200 {mensagem,livro,clientesNotificados,emailsNotificados}; inválido 400. Sem ID cria LIV-8HEX. Existente soma estoque; chegada atende pendentes FIFO (dataCriacao,interesseId), limitada ao estoque. Quantidade no resultado é final após reservas. Sem bool como número, sem NaN/Infinity, sem truncamento fracionário. Aviso SNS não impede persistência. UI desabilita envio em andamento.
POST efetivar {interesseId} -> 200 {mensagem,venda:{vendaId,interesseId,livroId,titulo,emailCliente,valor,dataVenda},status:VENDIDO}; inválido 400, ausente 404, estado diferente RESERVADO 409 {erro,statusAtual}. Transação atômica para interesse e venda; estoque já foi abatido na reserva.

Frontend sem framework: frontend/index.html, app.js, util.js, util.test.js, styles.css opcional, config.example.js. window.SEBO_CONFIG={URL_LISTAR,URL_SOLICITAR,URL_CADASTRAR,URL_EFETIVAR}, frontend/config.js gerado/ignorado. Cliente catálogo/form nome/email e resultado; colaborador entrada/estoque/interesses com venda de reservados/vendas. esc/moeda/dt exportados CommonJS e window.SeboUtil. textContent preferido; qualquer API em innerHTML deve esc(). Sem dados fictícios disfarçados de produção.

## Integridade e limites
Corrigir falhas do plano: reserva+interesse atômicos, dedupe simultâneo atômico (guard determinístico ou equivalente nas mesmas tabelas), venda+transição atômicos; chegada concorrente não deve gastar exemplar duas vezes. Usar transações DynamoDB com condições e retries limitados para conflitos. Documentar limites remanescentes sem alegar garantias impossíveis. Não misturar cliente resource marshalling com low-level TransactWriteItems. Backend deve exportar seus contratos/decisões em docs/backend-notes.md para integração.

## Ferramentas / colaboração
Raiz C:/Users/Enzo/Documents/Projects/SeboNaNuvem. Windows, bash MSYS. Para native tools usar C:/...; python3 3.13 disponível, node 26; runtime AWS continua 3.12. Venv .venv/Scripts/python.exe. Equipes trabalham em diretórios disjuntos. Não fazer commit até integração do coordenador. Testes críticos test-first e outputs reais. Não executar deploy/seed/reset AWS sem autorização/credenciais Lab verificadas. Scripts deploy podem usar boto3 Python (cross-platform) com wrappers bash para comandos do plano.
