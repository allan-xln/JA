# Usuários de demonstração

## Admin

Usuário:

```text
admin
```

Senha inicial de demo:

```text
admin
```

O admin vê todos os dados: lojas, sensores, dispositivos, alarmes, telemetria, anomalias, regras, logs, WhatsApp e RAG.

## Clientes

Os clientes são gerados pelo seed:

```bash
python -m api.scripts.seed_tenants
```

No Docker/VPS:

```bash
docker compose exec api python -m api.scripts.seed_tenants
```

O arquivo local não versionado `data/demo_users_generated.txt` lista os usuários criados no formato:

```text
usuario / senha
```

Para demonstração, a senha inicial do cliente é igual ao usuário.

Exemplo:

```text
carnesdofulano / carnesdofulano
```

## Regra de isolamento

Cliente vê apenas:

- lojas vinculadas ao seu tenant;
- dispositivos dessas lojas;
- alarmes, telemetria, insights e anomalias vinculados;
- conversas e histórico RAG vinculados ao seu ambiente.

Cliente não vê dados de outros clientes.

## Produção

As senhas iguais ao usuário são apenas para demonstração. Em produção, exigir troca de senha e política de credenciais própria.
