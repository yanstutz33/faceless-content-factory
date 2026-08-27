# Conexões oficiais — etapa manual

O Studio 1.4 já prepara OAuth, cofre criptografado, callbacks, auditoria e pré-validação. Esta etapa exige ação humana porque cada plataforma precisa confirmar a identidade e o canal/conta corretos. O modo de publicação continua bloqueado por padrão.

## Antes de conectar

1. Execute `./scripts/setup.ps1` e `./scripts/start.ps1`.
2. Mantenha `ALLOW_PLATFORM_PUBLISH=false`.
3. Não envie o arquivo `.env`, arquivos de cliente OAuth ou `data/private/` ao GitHub.
4. Abra **Conexões** e confirme que o backup e o cofre estão prontos.

## YouTube

1. Crie um projeto no Google Cloud, habilite YouTube Data API v3 e configure a tela de consentimento.
2. Crie um cliente OAuth para aplicativo web e registre exatamente `http://127.0.0.1:8787/api/oauth/callback/youtube`.
3. Baixe o JSON do cliente para fora do repositório e defina `YOUTUBE_CLIENT_SECRETS_FILE` no `.env`.
4. Reinicie o Studio e clique em **Conectar**. O escopo pedido é apenas `youtube.upload`.

Documentação oficial: https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps

## TikTok

1. Registre o aplicativo no TikTok for Developers e solicite acesso ao Content Posting API.
2. Cadastre `http://127.0.0.1:8787/api/oauth/callback/tiktok` como URL de retorno.
3. Preencha `TIKTOK_CLIENT_KEY` e `TIKTOK_CLIENT_SECRET` no `.env`.
4. Reinicie e conecte a conta. O Studio apenas guarda a autorização; envio continua manual.

Documentação oficial: https://developers.tiktok.com/docs/en/content-posting-api-get-started

## Instagram Reels

1. Registre um app Meta compatível com Instagram profissional e configure a URL de retorno `http://127.0.0.1:8787/api/oauth/callback/reels`.
2. Preencha `META_APP_ID` e `META_APP_SECRET` no `.env`.
3. Reinicie e escolha a conta profissional durante o login.

## Shopee

1. Preencha `SHOPEE_PARTNER_ID` e `SHOPEE_PARTNER_KEY` somente quando possuir credenciais oficiais.
2. Use o validador comercial e forneça mídia própria, licenciada ou oficialmente disponibilizada.
3. Pinterest pode servir como pesquisa visual, nunca como prova de licença ou fonte automática do vídeo.
4. Confirme manualmente o produto exato, preço, disponibilidade e divulgação `#publicidade` antes de publicar.

## Verificação local

```powershell
.\.venv\Scripts\python.exe app.py integrations
.\.venv\Scripts\python.exe app.py preflight youtube
.\.venv\Scripts\python.exe app.py backup
```

O pré-envio registra o diagnóstico em `data/integration-audit.jsonl` e `data/deliveries.json`, sem fazer upload ou contato com a plataforma.
