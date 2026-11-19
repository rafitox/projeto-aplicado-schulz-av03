# Deploy — Publicação via Cloudflare Tunnel

**Projeto Aplicado I — Entrega 03 (AV03) — Schulz S.A.**

Este documento descreve como publicar a aplicação Flask em um **Cloudflare
Tunnel**, e o que precisa ser conferido antes de expor um sistema que recebe
planilhas da empresa.

---

## 1. Como a publicação funciona

```
   Internet
      │
      ▼
┌─────────────────────────┐
│  Cloudflare (edge)      │   HTTPS público, TLS gerenciado pela Cloudflare
└───────────┬─────────────┘
            │  túnel (QUIC ou HTTP/2 sobre a 7844)
            ▼
┌─────────────────────────┐
│  cloudflared (local)    │   processo na sua máquina
└───────────┬─────────────┘
            │  HTTP em 127.0.0.1:5000
            ▼
┌─────────────────────────┐
│  Flask (127.0.0.1)      │   **nunca** exposto na rede local
└─────────────────────────┘
```

O ponto central: a aplicação Flask **continua ouvindo apenas em
`127.0.0.1`**. Quem aceita conexões da internet é o `cloudflared`, e ele
entrega ao Flask apenas o tráfego do túnel. Não é preciso abrir porta no
roteador, configurar NAT ou expor a máquina.

---

## 2. Pré-requisitos

```bash
# Instalar o cloudflared (sem sudo, no home do usuário)
mkdir -p ~/.local/bin
curl -L -o ~/.local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x ~/.local/bin/cloudflared
~/.local/bin/cloudflared --version
```

Nenhuma conta Cloudflare é necessária para o túnel de teste.

---

## 3. Túnel de teste (quick tunnel)

O `quick tunnel` gera uma URL aleatória em `trycloudflare.com`. Serve para
**demonstrar** a publicação; a URL muda a cada execução e o serviço não
tem garantia de disponibilidade.

### Passo a passo

**1. Subir a aplicação, com o token de acesso definido.**

```bash
cd ~/projeto_aplicado_schulz/projeto_aplicado_3

export SCHULZ_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
echo "token: $SCHULZ_ACCESS_TOKEN"          # anote: vai precisar dele

.venv/bin/python 07_webapp.py --port 5000
```

**2. Em outro terminal, subir o túnel.**

```bash
~/.local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5000
```

O `cloudflared` imprime a URL pública:

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://exemplo-aleatorio.trycloudflare.com                                             |
+--------------------------------------------------------------------------------------------+
```

**3. Testar.**

```bash
URL="https://exemplo-aleatorio.trycloudflare.com"
TOKEN="$SCHULZ_ACCESS_TOKEN"

curl -s -o /dev/null -w "sem token: %{http_code}\n" "$URL/"                    # 401
curl -s -o /dev/null -w "com token: %{http_code}\n" "$URL/?token=$TOKEN"       # 200
curl -s -H "X-Access-Token: $TOKEN" "$URL/api/estatisticas"                    # JSON
```

**4. Encerrar.** `Ctrl+C` nos dois terminais. A URL morre junto.

---

## 4. Túnel nomeado (produção)

Diferente do quick tunnel, o túnel nomeado tem URL fixa, é gerenciado por
conta e continua funcionando quando o processo local é reiniciado.

**1. Criar o túnel.**

```bash
~/.local/bin/cloudflared tunnel login          # abre o navegador para autenticar
~/.local/bin/cloudflared tunnel create schulz-av03
```

**2. Apontar o hostname para o túnel.**

```bash
~/.local/bin/cloudflared tunnel route dns schulz-av03 calibracao.seudominio.com
```

**3. Criar a configuração** (`~/.cloudflared/config.yml`):

```yaml
tunnel: <ID-DO-TUNEL>
credentials-file: /home/rafael/.cloudflared/<ID-DO-TUNEL>.json

ingress:
  - hostname: calibracao.seudominio.com
    service: http://127.0.0.1:5000
  - service: http_status:404
```

A última regra (`http_status:404`) é **obrigatória**: o `cloudflared` se
recusa a subir sem uma regra que capture o que sobrar.

**4. Rodar.**

```bash
SCHULZ_ACCESS_TOKEN="..." ~/.local/bin/cloudflared tunnel run schulz-av03
```

---

## 5. Configuração por variável de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `SCHULZ_ACCESS_TOKEN` | *(vazio)* | Token exigido em todas as rotas. **Defina antes de publicar.** |
| `SCHULZ_SECRET_KEY` | aleatória, por processo | Chave que assina o cookie de sessão. Fixe-a se precisar que a sessão sobreviva a reinícios. |
| `SCHULZ_BANCO` | `calibracao.db` | Caminho do banco SQLite (também por `--banco`). |

### Por que a chave secreta não pode ser fixa

O `SECRET_KEY` assina o cookie de sessão. Com a chave em mãos, qualquer
pessoa forja um cookie — e a sessão guarda o **caminho do arquivo
temporário** que será importado. Uma sessão forjada apontando para um
caminho arbitrário seria uma leitura de arquivo arbitrário.

A chave, portanto, é gerada aleatoriamente a cada execução
(`secrets.token_hex(32)`), e nunca fica escrita no código — o repositório é
público.

### Por que o token de acesso é necessário

O requisito **RNF01 (controle de acesso)** está fora do escopo desta
entrega. Sem token, a URL pública permitiria a qualquer pessoa enviar
arquivos para a aplicação e ler o acervo de calibração. O token é uma
proteção mínima e suficiente para a demonstração; não substitui
autenticação com usuário e senha.

O token pode ser enviado de três formas:

| Forma | Uso |
|---|---|
| Formulário `/acesso` | navegador — o cookie é gravado por 8 horas |
| `?token=...` | link direto — o servidor redireciona e grava o cookie |
| `X-Access-Token: ...` | API e scripts (`curl`, automação) |

---

## 6. Checklist antes de publicar

- [ ] `SCHULZ_ACCESS_TOKEN` definido e anotado
- [ ] `SCHULZ_SECRET_KEY` definida (se a sessão precisar sobreviver a reinícios)
- [ ] A aplicação escuta em `127.0.0.1` (`--host 127.0.0.1`, o padrão)
- [ ] O banco de teste não é o banco de produção
- [ ] O `cloudflared` está na versão mais recente
- [ ] O túnel nomeado (não quick) está em uso, se a publicação for para ficar no ar

---

## 7. Limitações conhecidas

**Servidor de desenvolvimento.** O Flask vem com um servidor de
desenvolvimento, que não é para produção. Para a publicação final, use um
WSGI:

```bash
pip install gunicorn
gunicorn --bind 127.0.0.1:5000 --workers 2 "schulz_mvp.webapp:criar_aplicacao()"
```

O `cloudflared` continua apontando para `127.0.0.1:5000` — nenhuma mudança
na arquitetura.

**Quick tunnel.** A URL é aleatória, muda a cada execução e não tem
garantia de disponibilidade. É para demonstração.

**Limite de requisição.** O Cloudflare impõe limite de corpo de requisição
(100 MB no plano gratuito). A aplicação já limita o upload a 20 MB
(`MAX_CONTENT_LENGTH`), o que fica bem dentro.

**SQLite.** O banco é um arquivo local. Um túnel expõe a aplicação, não o
banco: ninguém acessa o arquivo diretamente. Ainda assim, o SQLite serializa
as escritas — não há concorrência de leitura relevante no escopo atual.

---

## 8. Diagnóstico

O `cloudflared` faz uma verificação de conectividade ao subir e mostra o
resultado:

```
|  COMPONENT         TARGET                     STATUS  DETAILS                            |
|  UDP Connectivity  region1.v2.argotunnel.com  PASS    QUIC connection successful         |
|  UDP Connectivity  region2.v2.argotunnel.com  FAIL    QUIC connection failed              |
|  TCP Connectivity  region1.v2.argotunnel.com  PASS    HTTP/2 connection successful         |
|  TCP Connectivity  region2.v2.argotunnel.com  FAIL    HTTP/2 connection is blocked         |
```

**Uma das duas regiões falhar é normal** em conexões residenciais: o túnel
registra quantas conexões conseguir e usa as que funcionarem. O túnel só
para de funcionar se **todas** falharem.

**Se todas falharem** (empresa ou rede que bloqueia as portas 7844):

```bash
~/.local/bin/cloudflared tunnel --protocol http2 --url http://127.0.0.1:5000
```

O HTTP/2 usa a porta 443, que quase nunca é bloqueada.

**Verificar se a URL responde:**

```bash
curl -sv "$URL/" 2>&1 | grep -E "^< HTTP|SSL connection|Server:"
```

**Verificar o log do túnel:** o `cloudflared` em primeiro plano mostra cada
requisição recebida. Rodando com `--logfile`, o histórico fica gravado.

---

## 9. Encerrar

```bash
# Parar o túnel e a aplicação
pkill -f "cloudflared tunnel"
pkill -f "07_webapp.py"
```

O túnel nomeado pode continuar registrado no painel da Cloudflare mesmo
com o processo parado — ele apenas volta a funcionar quando o `cloudflared`
sobe de novo.

Para removê-lo de vez (apaga o registro na Cloudflare):

```bash
~/.local/bin/cloudflared tunnel delete schulz-av03
```
