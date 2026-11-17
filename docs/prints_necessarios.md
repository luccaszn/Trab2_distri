# Evidências para a entrega

Autores: Enzo Abate — 2312936; Lucca Sznaider — 2220504.

Os prints locais não substituem os da AWS. Não capture a tela de credenciais do Learner Lab nem tokens de sessão.

| Evidência | Origem | Situação |
|---|---|---|
| Catálogo e pedido de cliente | Interface | Capturar após teste integrado |
| Cadastro de chegada, estoque, interesses e venda | Interface colaborador | Capturar após teste integrado |
| Três tabelas e itens persistidos | Console DynamoDB | Pendente de deploy AWS |
| Quatro Lambdas com layer anexada | Console Lambda | Pendente de deploy AWS |
| Conteúdo/versionamento da layer sebo-common | Console Lambda → Layers | Pendente de deploy AWS |
| Tópico SNS e assinaturas confirmadas com filtro emailCliente | Console SNS | Pendente de confirmação humana |
| E-mail de livro disponível | Caixa postal real | Não validado |
| E-mail de chegada de livro indisponível | Caixa postal real | Não validado |
| Testes locais e e2e | Terminal + docs/resultados_testes.txt | Registrar saídas reais |
| Conta da AWS Academy | STS/console | Informar no EaD após deploy |

## Antes de apresentar

1. Iniciar o Learner Lab e renovar credenciais temporárias pelo ambiente local, nunca por chat.
2. Conferir a conta e a região us-east-1.
3. Confirmar assinaturas e aguardar propagação dos filtros SNS.
4. Resetar dados somente com confirmação explícita; o reset apaga interesses e vendas de demonstração.
5. Fazer os fluxos disponível → reserva → venda e indisponível → chegada → reserva.
6. Os dois integrantes devem saber explicar qualquer Lambda, as transações, a layer e o SNS.
