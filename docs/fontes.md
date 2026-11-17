# Fontes e critérios

## Fonte primária do trabalho

`Trab2_2026_2.pdf`, fornecido pelo professor e incluído nesta pasta. O enunciado é a autoridade para os critérios acadêmicos. O plano recebido foi preservado como `plano-original.md`; ele não substitui o enunciado e contém expectativas de testes, não resultados executados.

## Documentação oficial consultada

- AWS Lambda — Control access to Lambda function URLs: `https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html`. As duas permissões de invocação são configuradas explicitamente para URLs públicas.
- Amazon DynamoDB — Transaction APIs: `https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html`. Transações e condições sustentam as operações relacionadas; uma varredura não equivale a snapshot serializável de toda a tabela.
- Amazon SNS — Subscription filter policies: `https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html`. O atributo emailCliente precisa casar com o filtro; alterações de filtro podem levar até 15 minutos para propagar.

A consulta não comprova permissões do Learner Lab específico. Essa compatibilidade só fica validada após execução na conta correta.
