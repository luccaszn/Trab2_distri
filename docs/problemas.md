# Problemas, decisões e pendências

## Bloqueio externo verificado

- A descoberta local de credenciais por `boto3.Session().get_credentials()` retornou **nenhum provedor** nesta sessão. Nenhum valor secreto foi lido ou impresso. Sem Learner Lab autenticado, não foi executado deploy nem envio de e-mail AWS.
- AWS CLI não estava no PATH. A automação usa boto3 com wrappers Bash; não precisa de AWS CLI para o deploy.
- Conta AWS, ARNs, URLs públicas e versão publicada da layer só podem ser informados depois do deploy real. Não há identificadores inventados neste relatório.

## Ajustes em relação ao plano recebido

- Operações relacionadas de estoque/interesse e interesse/venda foram implementadas com transações, não escritas independentes, e validadas localmente por testes de rollback e disputa.
- Deduplicação precisa de condição atômica, não consulta eventual em GSI seguida de escrita.
- Reset de dados deve exigir confirmação; testes AWS destrutivos devem ser opt-in separado.
- Publicação SNS aceita é diferente de e-mail recebido. Falha de publicação mantém a reserva; recebimento depende de validação na caixa postal.
- O ambiente local executa os handlers reais com Moto em memória. Não representa um deploy, não envia e-mails e perde dados ao parar o processo.
- A revisão independente do código não apontou falha concreta de lógica ou segurança nos arquivos revisados. Isso não comprova permissões ou execução no Learner Lab.
- Uma instalação opcional de biblioteca de PDF esbarrou em disco C quase cheio. As dependências opcionais recém-instaladas foram removidas e a geração usou Chromium e bibliotecas leves. O ambiente principal continuou funcionando e a suíte passou depois da limpeza.

## Não fazer automaticamente

Não alterar IAM, trocar LabRole, criar infraestrutura fora do prefixo sebo-, remover recursos, expor credenciais, criar EC2/RDS/NAT/OpenSearch nem declarar o trabalho entregue no EaD.
