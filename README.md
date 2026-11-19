# Vinheria Agnello — Infraestrutura, Pipeline Jenkins & DevSecOps

Simulação executável da infraestrutura distribuída, automação CI/CD (Jenkins) e comunicação segura (TLS 1.3 + JWT RS256 + Wireshark) para a arquitetura de microsserviços da **Vinheria Agnello** (FIAP — Turma Online — Felipe Castro Lima, RM554976 — Grupo 55).

## 1. Arquitetura Implementada

Microsserviços selecionados da modelagem da Fase 6 (`FelipeCastroLima_rm554976_TurmaOnline_fase6_atividade.docx`) integrados à camada IoT do Grupo 55 (`Entrega_FIAP_Vinheria_Agnello_Grupo55.zip`):

| Componente | FQDN (`vinheria.local`) | IP na Rede `vinheria-net` | Função |
| :--- | :--- | :--- | :--- |
| **DNS + DHCP (`dnsmasq`)** | `dns.vinheria.local` | `172.28.0.53` | Zona DNS autoritativa `vinheria.local` + servidor DHCP (`172.28.0.100–150`) com registro dinâmico |
| **API Gateway (`nginx`)** | `gateway.vinheria.local` | `172.28.0.10` | Proxy reverso L7: HTTP `:8081` (demo insegura) e HTTPS TLS 1.3 `:8443` (produção segura) |
| **Quality & IoT Service** | `quality.vinheria.local` | `172.28.0.20` | Ingestão ESP32 (DHT22/LDR), regras bioquímicas (Arrhenius, rolha, *Goût de Lumière*), emissor JWT RS256 + JWKS, SQLite próprio |
| **Notification Service** | `notification.vinheria.local` | `172.28.0.30` | Recebe eventos `AlertaQualidadeTermicaDisparado`, valida assinatura JWT RS256 + RBAC, deduplicação, SQLite próprio |
| **ESP32 Sensor Simulator** | `esp32-sensor-01.vinheria.local` | Dinâmico via DHCP (`172.28.0.100–150`) | Executa handshake DHCP DORA real (`udhcpc`) e publica leituras de adega via DNS |
| **Jenkins CI/CD** | `jenkins.vinheria.local` | `172.28.0.40` (Host `:8080`) | Job `vinheria-agnello-deploy`: Checkout Git → Build (`Deploy da Vinheria`) → Testes/DevSecOps → Publicação |
| **Site de Publicação (Simulação IIS)** | `prod-site.vinheria.local` | `172.28.0.50` (Host `:8088`) | Serve `/var/www/vinheria-agnello` (`deploy/wwwroot`), simulando `C:\inetpub\wwwroot\vinheria-agnello` |

## 2. Pré-requisitos

- Docker Engine + Docker Compose v2
- `openssl`, `curl`, `jq`, `git`
- `wireshark` / `tshark` (para abrir e inspecionar os arquivos `.pcap` gerados em `captures/`)

## 3. Execução Rápida

```bash
# 1. Gerar CA interna, certificados X.509 (SAN) e par RSA-2048 para JWT
./scripts/generate_certs_and_keys.sh

# 2. Subir toda a infraestrutura (DNS/DHCP, Microsserviços, Gateway, Jenkins, Site IIS-simulado)
docker compose up -d --build

# 3. Executar validação completa (DNS/DHCP + JWT/RBAC + Jenkins Build + Capturas Wireshark)
./scripts/verify_all.sh
```

## 4. Acessos Locais

- **Jenkins CI/CD:** `http://localhost:8080` (usuário: `admin` / senha: `vinheria2026`, job: `vinheria-agnello-deploy`)
- **Pasta de Publicação (Simulação IIS):** `http://localhost:8088` (arquivos locais em `./deploy/wwwroot`)
- **API Gateway Seguro (HTTPS TLS 1.3):** `https://localhost:8443/health` (CA em `./certs/ca.crt`)
- **API Gateway Inseguro (HTTP Texto Claro — Demo Wireshark):** `http://localhost:8081/health`

## 5. Inspeção no Wireshark

As capturas geradas automaticamente por `./scripts/run_security_demo.sh` ficam em `captures/`:

- `captures/01_inseguro_http_plaintext.pcap` — Filtro sugerido: `http` (expõe senha de login, header `Authorization: Bearer eyJ...` e payload JSON do alerta em texto claro)
- `captures/02_seguro_https_tls_jwt.pcap` — Filtro sugerido: `tls` (apenas handshake TLS 1.3 e `Application Data` cifrado — zero vazamento em texto claro)
- `captures/03_dns_dhcp_infra.pcap` — Filtro sugerido: `dhcp || dns` (handshake DORA completo e resolução `*.vinheria.local`)

Para captura ao vivo no Wireshark GUI, selecione a interface de rede **`br-vinheria`**.
