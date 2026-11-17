# Relatório — Sebo na Nuvem

**Segundo Trabalho de Distribuição e Concorrência — 2026/2**

**Enzo Abate — 2312936**

**Lucca Sznaider — 2220504**

> **Estado desta versão:** implementação e validação local. **AWS: não validado**; não havia credenciais do Learner Lab disponíveis. A aplicação ainda precisa ser implantada na conta da dupla e os dois e-mails reais precisam ser conferidos. Este relatório não afirma uma entrega na AWS que não ocorreu.

## 1. Introdução

A aplicação atende uma livraria de livros usados. Um comprador consulta o catálogo e registra interesse. Havendo estoque, um exemplar é reservado e um aviso é publicado no SNS, orientando o cliente a comparecer à livraria para efetivar a compra. Sem estoque, o interesse fica pendente; uma chegada posterior atende a fila e publica os avisos. O colaborador registra entradas e conclui vendas presenciais.

## 2. Arquitetura e Diagrama em blocos

A interface estática HTML/CSS/JavaScript chama quatro Lambdas Python 3.12 por Function URLs. A layer `sebo-common` concentra validações, HTTP, persistência transacional e notificações. Os dados ficam em três tabelas DynamoDB; o SNS distribui avisos apenas às assinaturas confirmadas cujo filtro corresponde ao cliente.

O **Diagrama em blocos** está em `diagramas.md`, junto às fontes Mermaid. O ambiente não requer VPC, servidor EC2, RDS ou NAT Gateway. O deploy usa a LabRole preexistente, sem criação ou alteração de IAM. Região: us-east-1.

## 3. Modelo de dados

| Tabela | Chave | Dados e finalidade |
|---|---|---|
| sebo-Livros | livroId | título, autor, quantidade disponível, preço Decimal, ano/condição e versão otimista |
| sebo-Interesses | interesseId | livro, cliente, estado, datas, valor capturado na reserva e auditoria da publicação |
| sebo-Vendas | vendaId | interesse, livro, cliente, valor de reserva e data da venda |

Interesses seguem `PENDENTE → RESERVADO → VENDIDO`. Na mesma tabela de interesses há itens internos de deduplicação `LOCK-<hash>`, com dono do interesse. Eles não têm os atributos do GSI e não aparecem na API de listagem.

O GSI `livroId-status-index`, com projeção ALL, está definido nos schemas. Não é usado como fonte de verdade da fila, porque é eventualmente consistente. O backend usa leitura consistente da tabela base e valida a versão do livro na transação. A infraestrutura e os testes compartilham `infra/tabela_*.json`; os dados de demonstração ficam em `infra/livros_seed.json`.

## 4. Lambdas e Layer

| Função | Responsabilidade |
|---|---|
| sebo-listar-livros | GET de livros, interesses e vendas, paginação interna e ordenação |
| sebo-solicitar-livro | POST de pedido, deduplicação, reserva ou registro pendente e aviso de disponibilidade |
| sebo-cadastrar-livro | POST de cadastro/chegada, soma de estoque, atendimento FIFO e avisos de chegada |
| sebo-efetivar-venda | POST de conclusão da compra, transição condicional e registro da venda |

A **Layer `sebo-common`** está em `layers/sebo-common/python/sebo_common/__init__.py`. Seu ZIP contém `python/sebo_common/__init__.py` na raiz esperada pelo runtime. Não inclui boto3: o SDK é fornecido pelo Lambda. A automação calcula hash SHA-256 dos artefatos determinísticos e reutiliza a versão publicada de conteúdo idêntico. Os quatro ZIPs de função contêm `app.py` na raiz, com handler `app.lambda_handler`.

Essa separação evita duplicar regras e mantém respostas/validações uniformes. A versão publicada da layer e os ARNs reais permanecem **não validados**, pois não houve deploy AWS nesta sessão. O manifesto real será gravado em `build/deployment.json` após readback.

## 5. Concorrência e integridade

A reserva grava estoque, interesse e guard de deduplicação numa única transação DynamoDB. A condição sobre a versão do livro impede duas operações de confirmar a mesma visão do estoque. O guard com chave determinística impede pedidos ativos duplicados do mesmo e-mail/livro, inclusive sob leituras simultâneas.

A chegada lê a versão do livro, consulta pendentes, ordena por data de criação e ID, e confirma estoque e reservas juntos. Disputa muda a versão e obriga recálculo. A venda altera o interesse para VENDIDO, grava a venda e remove o guard na mesma transação; não desconta o estoque novamente. O preço e o título da reserva são preservados, mesmo que o catálogo mude antes da venda.

Há retries limitados para conflitos. Eles não tornam o cadastro idempotente entre duas chamadas HTTP independentes: após perda de resposta, é necessário consultar o estoque antes de repetir uma entrada. A fila não promete ordem global de chegada de pacotes ou relógios entre máquinas; é FIFO dos pendentes observados e confirmados pelas regras do backend. Escritas manuais fora dessas regras podem violar as premissas.

## 6. Fluxo de e-mail

E-mails são normalizados com trim/lowercase. As mensagens incluem atributo SNS `emailCliente` String; cada assinatura usa filtro exato nesse atributo e escopo MessageAttributes. A aplicação não inscreve automaticamente o comprador. O usuário precisa confirmar a assinatura solicitada pela configuração/deploy, como permite a simplificação do enunciado.

Após commit, a Lambda publica o aviso com código da reserva e orientação para comparecer à livraria. O assunto distingue disponibilidade imediata de chegada. Publicação aceita registra `dataNotificacao` e `mensagemSnsId` em atualização auxiliar; falha dessa auditoria é registrada sem negar uma publicação já aceita.

**`emailEnviado=true` significa publicação aceita pelo SNS, não entrega comprovada.** Uma falha de publicação mantém a reserva e retorna false; não há rollback do estoque. A atualização de filtro pode levar até 15 minutos para propagar. Os dois recebimentos reais continuam **não validados**.

## 7. Diagrama de sequência

O **Diagrama de sequência** UML está em `diagramas.md` e cobre: A/B, pedido disponível ou pendente; chegada com atendimento da fila; C, efetivação da venda. O diagrama distingue o commit do banco da publicação SNS: esses serviços não compartilham uma transação distribuída.

## 8. O que funcionou

A evidência de execução está em `resultados_testes.txt` e nos testes de navegador. Foram exercitados localmente:

**Resultado consolidado executado:** 102 testes Python passaram, incluindo integração HTTP e dois testes reais de navegador; 2 testes AWS ficaram ignorados por falta de opt-in/ambiente real. Outros 11 testes JavaScript passaram. Parsing Python 3.12, sintaxe JS/Bash e geração dos cinco ZIPs passaram. A revisão independente não apontou falha concreta no código examinado; não substitui o deploy AWS.

- **T1 — disponível:** pedido reserva um exemplar, registra interesse e publicação SNS emulada; normaliza e-mail.
- **T2 — indisponível:** pedido fica PENDENTE sem aviso de disponibilidade.
- **T3 — chegada:** fila é atendida em ordem, limitada ao estoque; reserva sobrevive a falha SNS.
- **T4 — concorrência:** leituras disputadas, deduplicação, chegadas e vendas concorrentes são exercitadas com transações Moto; não houve estoque negativo nos cenários testados.
- **T5 — erros:** inválidos, ausentes, duplicados, base64 e métodos incorretos são rejeitados; paginação e serialização são verificadas.
- **T6 — venda:** persistência e mudança de estado são atômicas nos cenários de sucesso/rollback; venda repetida não duplica receita.
- Interface real em Chromium: pedido, conflito duplicado, venda, pendência e chegada; estados de erro/configuração; escape de título com HTML; desktop e celular.
- Automação local: layout e hash de cinco ZIPs, schemas e controles de confirmação/prefixo, além de doubles/readbacks de recursos.

As capturas em `evidencias/` são do **ambiente local emulado**, nunca prints do console AWS. Os testes de concorrência Moto usam barreira de leituras e mutex apenas na aplicação da transação para não atribuir ao emulador isolamento que ele não reproduz. Não equivalem a teste de carga AWS.

## 9. O que não funcionou / não foi validado

- **Deploy AWS não executado:** credenciais ausentes. Conta, ARNs, URLs, compatibilidade de permissões LabRole e versão da layer publicada não foram confirmados.
- **Dois e-mails reais não validados:** SNS local é emulado; não entrega mensagens. Assinaturas/recebimento exigem validação humana no lab e na caixa postal.
- O runtime local é Python 3.13. A gramática 3.12 foi verificada, mas a execução no runtime AWS Python 3.12 ainda não ocorreu.
- Function URLs com auth NONE e interface do colaborador sem login expõem dados e operações administrativas; CORS não é autenticação. Usar apenas em laboratório, sem dados sensíveis.
- Não há cancelamento ou expiração de reservas. Exemplares reservados e não vendidos permanecem presos.
- Não há outbox ou retry persistente de notificações. Crash entre commit e publish pode deixar uma reserva sem aviso. Auditoria de publish também é best-effort.
- Listagens e fila usam scans completos; isso não escala e não produz snapshot global. O GSI existe, mas não elimina essas limitações.
- Uma chegada atende no máximo 99 pendentes por transação. Se precisaria atender mais, retorna 409 antes de escrever e orienta dividir o lote.
- Cadastro/entrada não tem idempotência HTTP persistida. Timeout pode produzir resultado ambíguo; consultar antes de reenviar.
- Surgiram inconsistências de integração entre caminhos/schemas e dados de seed dos componentes. Foram corrigidas e os fluxos integrados reexecutados. `node --test frontend/` não funcionou nesta versão do Node; o comando verificado é `node --test frontend/util.test.js`.

## 10. Instalação e operação

Os procedimentos completos estão em `instalacao.md` e `operacao.md`. Para uso local: instalar `requirements-dev.txt`, executar `tools/dev_server.py` e abrir o endereço local. Para AWS: iniciar lab, configurar credenciais somente na sessão, preencher os e-mails públicos, rodar check/deploy, confirmar assinaturas, executar seed com `--confirm` e servir `frontend/` estaticamente.

Reset é explícito e destrutivo nas três tabelas; não repõe os livros automaticamente. Para restaurar a demonstração: `reset_dados.sh --confirm` e depois `seed.sh --confirm`, com a aplicação ociosa. Não há teardown automático.

## 11. Divisão de trabalho

**A preencher pela dupla conforme a participação efetiva.** Enzo Abate e Lucca Sznaider precisam revisar o código e registrar suas contribuições reais; este relatório não atribui atividades que não foram informadas. A implementação contou com assistência de IA. Ambos devem ser capazes de explicar todas as partes, pois a avaliação é individual.

## 12. Conclusão e pendências de entrega

A solução foi implementada e exercitada localmente, com regras transacionais além das escritas independentes do plano inicial. A conclusão acadêmica depende ainda do deploy no Learner Lab, da comprovação dos dois e-mails, dos prints AWS, da revisão/divisão de trabalho e da conta informada no EaD. Não se declara concluída a parte de nuvem sem essas evidências.
