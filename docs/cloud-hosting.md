# FFactory sempre ligado

O endereço `trycloudflare.com` é apenas um túnel para o computador local. Para o FFactory continuar disponível com o computador desligado, o aplicativo completo precisa rodar em um servidor com CPU, FFmpeg e disco persistente.

## Tamanho atual e configuração mínima

- Dados atuais: aproximadamente 12,2 GB.
- Disco inicial recomendado: 25 GB; 50 GB se os vídeos prontos permanecerem no servidor.
- Processamento inicial recomendado: 2 vCPU e 4 GB de RAM.
- Uma única instância deve acessar o banco SQLite e o disco por vez.

## Caminho mais simples: Render

O arquivo `render.yaml` deixa o projeto pronto para um Web Service Docker com HTTPS, reinício automático, 2 vCPU, 4 GB de RAM e disco persistente de 25 GB. A criação do serviço é paga e só deve ser confirmada depois de revisar o preço exibido pela Render.

Durante a criação, configure:

1. `FACTORY_REMOTE_USERNAME` com um usuário exclusivo.
2. `FACTORY_REMOTE_PASSWORD` com uma senha exclusiva de pelo menos 24 caracteres.
3. Mantenha `ALLOW_PLATFORM_PUBLISH=false` até concluir os logins e as revisões humanas.

Depois da primeira implantação, transfira `factory.db`, `jobs/` e `library/` para `/app/data`. Não copie o cofre `private/` do Windows: ele é vinculado ao sistema local. Chaves e logins devem ser conectados novamente dentro do servidor.

## Caminho de menor custo: VPS

`deploy/vps/compose.yaml` executa o FFactory em um contêiner sem privilégios e usa Caddy para HTTPS automático. Ele exige um domínio apontado para o IP do servidor e Docker instalado.

1. Copie `deploy/vps/.env.cloud.example` para `.env` dentro dessa pasta.
2. Defina domínio, usuário e uma senha forte.
3. Suba os serviços com Docker Compose.
4. Transfira os dados para o volume `ffactory_data`.

## Segurança e continuidade

- O painel exige autenticação também na nuvem.
- A rota pública `/healthz` informa apenas que o processo está vivo; não expõe diagnósticos nem dados.
- O contêiner reinicia automaticamente depois de falhas ou reinicializações do servidor.
- Banco, músicas e vídeos ficam exclusivamente no volume persistente.
- Backups devem ser copiados periodicamente para outro provedor; um disco persistente não substitui backup.
- A publicação automática nas plataformas permanece desligada.

