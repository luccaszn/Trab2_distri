# Operação e roteiro de apresentação

**Dupla:** Enzo Abate — 2312936 · Lucca Sznaider — 2220504.

## Qual ambiente está em uso?

- `tools/dev_server.py`: local emulado, sem entrega de e-mail; dados em memória.
- Servidor estático de `frontend/` após deploy: AWS real, URLs em `frontend/config.js`; exige Learner Lab e serviços ativos.

Não use resultados do primeiro como prova do segundo.

## Cliente: livro disponível

1. Na aba Cliente, selecione Dom Casmurro (`SEED-001`) no catálogo.
2. Informe nome e e-mail. Na AWS, use um e-mail já inscrito e confirmado no tópico SNS.
3. Envie o pedido. A reserva deve reduzir o estoque disponível em uma unidade e gerar um código de interesse.
4. O cliente recebe instrução para comparecer à livraria, não uma cobrança ou compra automática.
5. Um segundo pedido ativo do mesmo cliente/livro é conflito (409), não uma segunda reserva.

## Cliente: livro indisponível

1. Selecione O Alienista (`SEED-003`), inicialmente sem estoque.
2. Faça o pedido; ele fica PENDENTE, sem publicação de disponibilidade nesse momento.
3. Guarde o código e confira o registro na aba Colaborador.

## Colaborador: registrar chegada

1. Abra Colaborador e use o formulário de cadastro/entrada.
2. Para repor, informe **o mesmo livroId** do pedido pendente. Título igual com ID novo cria outro livro e não atende a fila anterior.
3. Informe quantidade inteira positiva, preço não negativo, título e autor.
4. Após registrar, confira os interesses reservados e o estoque restante. Chegada menor que a fila atende apenas os primeiros que couberem.
5. Compare o e-mail real de chegada, se estiver no ambiente AWS. No local não há e-mail real.

## Colaborador: efetivar venda

1. Localize um interesse RESERVADO e clique em Efetivar venda.
2. A aplicação registra a venda e altera o interesse para VENDIDO na mesma transação.
3. O estoque não é abatido novamente: já foi reservado anteriormente.
4. Tentar vender novamente retorna conflito, sem duplicar receita.

## Reiniciar demonstração

O servidor local pode ser encerrado e iniciado novamente; os dados locais são descartados. Na AWS, o reset é uma operação destrutiva explícita e exige `--confirm`:

```bash
bash reset_dados.sh --confirm
bash seed.sh --confirm
```

O reset esvazia todas as três tabelas, inclusive livros e guards; o seed posterior repõe os quatro títulos. Ele não é teardown da infraestrutura. Confira a conta antes de resetar e leia a política exata em `--help`. Nunca rode um reset só para 'limpar' registros que devem constar da entrega.

## Falhas esperadas

- Sem `frontend/config.js` no servidor estático: endpoints ainda não configurados; faça deploy ou use o servidor local.
- Rede/CORS: confira URL, permissões Function URL, origem e configuração CORS no serviço. Não tente resolver colocando credenciais no navegador.
- SNS falhou: a reserva permanece válida e a resposta informa que não publicou. Não envie outro pedido para tentar recuperar o e-mail; ele seria duplicado. Consulte logs e o registro.
- Publicou mas não recebeu: confira assinatura confirmada, filtro, propagação e spam. O campo `emailEnviado` significa publicação aceita, não recibo de entrega.
- Credencial expirada: reinicie/renove a sessão do Learner Lab e rode check_env novamente.

## Logs AWS (opcional, se AWS CLI estiver instalado)

```bash
aws logs tail /aws/lambda/sebo-solicitar-livro --since 15m --region us-east-1
aws logs tail /aws/lambda/sebo-cadastrar-livro --since 15m --region us-east-1
```

Não capture logs que contenham dados pessoais para exposição pública.

## Perguntas que ambos devem saber responder

- Por que quatro Lambdas e qual a responsabilidade de cada uma?
- O que está na layer e por que seu ZIP começa com `python/`?
- Qual a diferença entre PENDENTE, RESERVADO e VENDIDO?
- Como as transações evitam estoque negativo, deduplicação incorreta e venda sem registro?
- Por que SNS não entrega para qualquer e-mail digitado no formulário?
- Por que GSI eventualmente consistente exige cuidado com fila e duplicados?
- Quais limites impedem chamar esta versão de sistema pronto para produção?
