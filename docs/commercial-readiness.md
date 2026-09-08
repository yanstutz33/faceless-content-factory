# Preparação comercial do FFactory

Este documento define a passagem do Hub pessoal para um produto com usuários externos. O 3AM Shelter continua sendo o ambiente real de validação, mas seus dados, mídias e credenciais nunca poderão aparecer em espaços de clientes.

## Limite atual

- Operação de um único proprietário e um único banco SQLite.
- Credenciais protegidas localmente pelo Windows DPAPI.
- Publicação automática desligada e entregas externas sujeitas a revisão.
- Infraestrutura em nuvem preparada, mas implantação permanente adiada enquanto o orçamento for zero.
- O sistema ainda não deve receber clientes pagantes ou dados de terceiros.

## Etapa A — isolamento de espaços

1. Introduzir `workspace_id` em usuários, produções, agenda, ativos, músicas, métricas, campanhas e auditoria.
2. Migrar os dados atuais para um espaço exclusivo chamado `3am-shelter`.
3. Exigir o espaço em todas as consultas e alterações; nenhuma rota pode aceitar um identificador sem validar sua pertença.
4. Criar testes negativos que tentem acessar arquivos, métricas e produções de outro espaço.
5. Separar diretórios físicos e chaves do cofre por espaço.

Saída obrigatória: teste automatizado prova que dois espaços não conseguem ler, alterar ou publicar dados um do outro.

## Etapa B — usuários e responsabilidades

1. Implementar contas individuais; proibir compartilhamento da conta proprietária.
2. Criar papéis mínimos: proprietário, editor e revisor.
3. Exigir confirmação adicional para conectar contas, alterar visibilidade, publicar ou excluir.
4. Registrar usuário, espaço, horário, alvo e resultado de toda ação sensível.
5. Implementar recuperação de acesso e encerramento de sessões.

Saída obrigatória: matriz de permissões coberta por testes e trilha de auditoria legível.

## Etapa C — integrações como módulos

1. Cada plataforma deve poder ser ativada, testada, reautorizada e revogada separadamente.
2. A interface nunca mostra segredos; exibe apenas estado, escopos, conta conectada e vencimento.
3. Tokens são separados por espaço e plataforma.
4. Falhas usam tentativas limitadas e idempotência para impedir envio duplicado.
5. Publicação automática permanece desativada até três pilotos corretos naquela plataforma e naquele espaço.

Saída obrigatória: conectar ou remover uma plataforma não afeta as demais e não expõe credenciais.

## Etapa D — operação e suporte

1. Medir fila, tempo de renderização, armazenamento, falhas, custo por vídeo e credenciais próximas do vencimento.
2. Aplicar cotas por espaço para armazenamento, geração, duração e publicações.
3. Criar exportação e exclusão completa dos dados de um espaço.
4. Manter backup, restauração e plano de incidente testados.
5. Escrever onboarding curto com um projeto demonstrativo que possa ser apagado.

Saída obrigatória: um operador identifica e recupera uma falha sem consultar diretamente o banco.

## Etapa E — revisão profissional obrigatória

Antes de vender ou receber dados de clientes, obter revisão profissional sobre privacidade, termos, direitos autorais, licenças de música e imagem, obrigações fiscais, proteção do consumidor e tratamento de dados. O software deve implementar as decisões dessa revisão; este documento não substitui aconselhamento jurídico ou contábil.

## Piloto fechado

1. Convidar poucos usuários conhecidos, sem cobrança inicial.
2. Usar espaços isolados e limites baixos.
3. Proibir publicação automática durante todo o piloto.
4. Medir conclusão do onboarding, tempo economizado, erros, pedidos de suporte e intenção de continuar usando.
5. Corrigir qualquer falha de isolamento, perda de dados ou publicação duplicada antes de ampliar o acesso.

## Condição para comercialização

O FFactory só pode ser apresentado como produto pronto quando isolamento, permissões, recuperação, auditoria, documentação profissional, custos operacionais e um piloto fechado estiverem comprovados. Até lá, ele permanece um sistema pessoal em validação.
