# RTX 2070 (`msi`) availability — V10 Wave C retry, 2026-08-16

Create-only companion to [2070-availability-20260816.md](2070-availability-20260816.md)
(the 048 offline observation). Collected from CT103 (`agentcontrol`,
`192.168.4.62`) and CT104 (`agentworker`, `192.168.4.63`) over WSL SSH after
the human confirmed the GPU host was back.

The human localhost curl was on `benol@buttholecentral` (`127.0.0.1:11434`).
That host is the **3080** (`100.107.20.28`), not the configured 2070. Live
tags below are from the **ACP hosts** against the configured
`MODEL_2070_BASE_URL`. Handoff 048 is not rewritten.

## Tailnet status (CT103)

```text
100.107.20.28   buttholecentral  olsenben@  linux    active; direct 192.168.4.28:63519
100.125.235.54  msi              olsenben@  windows  active; direct 192.168.6.90:41641
```

`msi` is no longer `offline, last seen 12h ago`. ICMP ping from the `deploy`
user is not permitted (`cap_net_raw` missing); HTTP is the liveness signal.

## HTTP reachability from ACP hosts

| From | Target | Result |
|---|---|---|
| CT103 host | `http://100.125.235.54:11434/api/tags` | HTTP 200, 9.7 ms |
| CT104 host | `http://100.125.235.54:11434/api/tags` | HTTP 200, 30.6 ms |
| CT103 `control-plane` container | same URL | HTTP 200, one model |
| CT103 `/readyz` `model_2070` | `http://100.125.235.54:11434/api/version` | `ok` (status `ready`) |

## Live tags on the configured 2070 URL (`msi`, `100.125.235.54:11434`)

Exactly one model, identical from both ACP hosts:

| name | digest | size | quant | params |
|---|---|---|---|---|
| `qwen2.5-coder:7b` | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` | 4683087561 | Q4_K_M | 7.6B |

`qwen2.5-coder:3b` is absent. `qwen2.5-coder:14b` and `llama3:latest` are
**not** on this endpoint.

## Human localhost tags were the 3080

`http://100.107.20.28:11434/api/tags` (`buttholecentral`, configured
`MODEL_3080_BASE_URL`) serves the three names the human saw on localhost:

| name | digest | quant | params |
|---|---|---|---|
| `qwen2.5-coder:14b` | `9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849` | Q4_K_M | 14.8B |
| `qwen2.5-coder:7b` | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` | Q4_K_M | 7.6B |
| `llama3:latest` | `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1` | Q4_0 | 8.0B |

C1 does not use this URL. The 3080 `:14b` remains the Qwen patch-author
identity (`MODEL_3080_NAME`), unchanged.

## Host alignment (env-only)

| Host | Before (container + `.env`) | After |
|---|---|---|
| CT103 | `MODEL_2070_NAME=qwen2.5-coder:3b` (`.env` dated 2026-08-03) | `qwen2.5-coder:7b` after host `.env` edit + `docker compose up -d --force-recreate --no-deps control-plane` |
| CT104 | `MODEL_2070_NAME=qwen2.5-coder:7b` (`.env` dated 2026-07-21) | unchanged |

Both hosts now request `qwen2.5-coder:7b` from `http://100.125.235.54:11434`.
No ACP image rebuild. Deployed tip remains `027ad9f06328f9b55f217b042d14c2fcb2beb25d`.

## Conclusion

The real 2070 endpoint is reachable from both ACP hosts and serves the frozen
C1 identity `qwen2.5-coder:7b` (digest `dae161e2…`). The 048 offline
observation stands as a historical FAIL; this file is the retry liveness
record.
