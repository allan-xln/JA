# Checklist de Apresentação - Eletrofrio JA

Use este roteiro antes da apresentação para deixar a demo previsível, profissional e com plano B.

## Antes de Apresentar

- [ ] Estar na pasta correta: `/home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA`.
- [ ] Confirmar `.env` preenchido com `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
- [ ] Confirmar se `OPENAI_API_KEY` está ativa ou assumir fallback local por regras.
- [ ] Para demonstração segura, usar `WHATSAPP_DRY_RUN=true` se não quiser envio real.
- [ ] Se for enviar mensagem real, preencher `WHATSAPP_ALLOWED_RECIPIENTS`.
- [ ] Garantir que Docker está ativo.
- [ ] Abrir Supabase em uma aba como evidência de dados reais.

## Subir a Plataforma

```bash
cd /home/allan/Documentos/Projetcs/LanChat/ELETROFRIO/JA
make demo-up
```

Containers esperados:

- `ja-api-1`: backend FastAPI.
- `ja-frontend-1`: frontend Next.js.
- `ja-scheduler-1`: rotina de coleta.
- `ja-whatsapp-1`: canal WhatsApp Baileys.

## Validações Essenciais

```bash
make demo-check
```

Abrir frontend:

```text
http://localhost:3000
```

## Perguntas Prontas

Use pelo backend ou diretamente no WhatsApp conectado:

- `Me dá um resumo da operação agora`
- `Como está a loja Sítio Cercado?`
- `Quais equipamentos estão offline?`
- `Qual equipamento exige atenção imediata?`
- `Teve alguma anomalia hoje?`
- `Quais lojas estão mais críticas?`

Teste via curl:

```bash
curl -X POST http://127.0.0.1:8000/api/eletrofrio/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Me dá um resumo da operação agora"}'
```

## Roteiro de Demo

1. Abrir **Visão** e mostrar totais de lojas, ativos, ocorrências e telemetria.
2. Abrir **Ocorrências** e explicar que a fila já vem priorizada.
3. Abrir **Operação** e mostrar coleta, último snapshot, resumo pós-coleta e envio para WhatsApp.
4. Abrir **Regras** e explicar que a decisão é auditável por regra, evidência e ação recomendada.
5. Abrir **WhatsApp** e mostrar status do canal ou QR Code.
6. Fechar com uma pergunta no diagnóstico: `Me dá um resumo da operação agora`.

## Plano B

- Se OpenAI falhar: o backend usa fallback local por regras e continua respondendo.
- Para as perguntas de apresentação, o diagnóstico responde primeiro por dados/regras locais para evitar travas de rede.
- Se a tabela de regras ainda não existir: execute `sql/003_operational_rules.sql` no Supabase SQL Editor e depois `docker compose up -d --build`.
- Se WhatsApp estiver em `dry-run`: mostrar a validação sem envio real e explicar que isso evita disparo durante a demonstração.
- Se um endpoint oficial oscilar: usar o último snapshot salvo no Supabase para manter a apresentação.
- Se QR não aparecer: usar `/status` para mostrar sessão conectada ou rodar `docker compose logs -f whatsapp`.
- Se Docker precisar reiniciar:

```bash
docker compose down
docker compose up -d --build
```

## Frase de Fechamento

“O valor do projeto está em sair de dados espalhados para uma operação priorizada: coleta real, regras técnicas auditáveis, evidências, diagnóstico controlado e comunicação direta pelo WhatsApp.”
