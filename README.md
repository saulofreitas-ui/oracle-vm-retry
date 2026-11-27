# oracle-vm-retry

Tenta criar uma VM **Ampere A1 Always Free** (Ubuntu 24.04, São Paulo) na Oracle Cloud até conseguir,
rodando no GitHub Actions — funciona com o computador desligado.

- Alterna entre **1 OCPU/6 GB**, **2 OCPU/12 GB** e **4 OCPU/24 GB**, uma tentativa por minuto.
- Se já existir uma VM A1 na conta, não cria outra.
- Quando conseguir: abre uma *issue* "✅ VM Oracle criada" (chega no seu e-mail; o IP não aparece no GitHub por ser público — veja no console da Oracle ou no aviso do ntfy),
  manda aviso no app **ntfy** (se o secret `NTFY_TOPIC` existir) e **desliga o próprio workflow**.

## Secrets (Settings → Secrets and variables → Actions)

| Secret | Conteúdo |
|---|---|
| `OCI_SETTINGS` | JSON com dados da chave de API, compartment, AD, subnet, imagem e chave SSH pública |
| `OCI_KEY` | **conteúdo inteiro** do arquivo `.pem` da chave de API (você cadastra) |
| `NTFY_TOPIC` | opcional – tópico do app ntfy para aviso no celular |

Nenhum dado da conta fica no código.

## Acompanhar

Aba **Actions** → "Tentar criar VM Oracle" → abra a execução mais recente → passo "Tentar criar a VM".
Para rodar na hora: **Run workflow**.
