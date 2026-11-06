# Ativar na rede e desfazer a mudança

## 1. Confirme as capacidades reais

No painel do roteador, procure LAN/DHCP e DNS. Anote a configuração anterior antes de alterar. Não altere WAN, PPPoE, credenciais da operadora ou o servidor DHCP por tentativa.

No Android sem root, o HomeDNS está na porta **1053**, não na 53. Há duas configurações diferentes:

- **DNS proxy do roteador com upstream e porta configuráveis:** mantenha o IP do roteador como DNS distribuído por DHCP. Configure o upstream do proxy para `IP_DO_CELULAR:1053`, usando a sintaxe exigida pelo firmware.
- **Encaminhamento de DNS da LAN:** se o firmware oferece regra específica para redirecionar consultas DNS locais, ela deve contemplar **UDP e TCP** para `IP_DO_CELULAR:1053`, sem criar loop no próprio resolvedor. A regra exata depende do roteador; não aplique regras genéricas de WAN.

Se a interface só permite um endereço IP como DNS, **isso não resolve a porta diferente**. Não salve `IP_DO_CELULAR:1053` em um campo que aceita somente IP e não configure o IP sozinho: os dispositivos tentarão a porta 53 e poderão perder resolução.

Se não houver suporte, os caminhos são um roteador que faça o encaminhamento, um servidor capaz de atender na porta 53 ou uma avaliação separada de root no celular. Usar o DNS público filtrado do AdGuard no roteador pode fornecer bloqueio sem o celular, mas é outra arquitetura, sem suas listas e painel locais.

## 2. Reserve o endereço do celular

Crie uma reserva DHCP para o endereço MAC usado pelo aparelho **nesse Wi-Fi**. Android pode usar MAC aleatório por rede. Confirme a reserva com o endereço exibido no aparelho/roteador; não confunda com o MAC físico informado na caixa. Faça isso antes de depender do IP como DNS.

## 3. Verifique o servidor sem alterar a rede

```bash
python3 scripts/check.py IP_DO_CELULAR --port 1053
```

Só prossiga com UDP e TCP funcionando. Wi-Fi com isolamento de clientes pode impedir acesso entre os aparelhos.

## 4. Configure o roteador e valide

Configure o upstream/encaminhamento suportado pelo firmware. Confira também DNS anunciado por IPv6 (RA/RDNSS/DHCPv6); um DNS IPv6 externo pode contornar o filtro IPv4. Não desative IPv6 de toda a rede como primeira tentativa.

Renove a conexão Wi-Fi em um aparelho de teste, limpe caches se necessário e confira:

```bash
python3 scripts/check.py IP_DO_ROTEADOR --port 53
```

Valide navegação normal, um segundo aparelho e a retomada do serviço após reiniciar o celular. Uma consulta explícita ao servidor demonstra que ele funciona; sozinha, não demonstra que todos os aparelhos o adotaram. DNS privado, VPN ou DoH no navegador podem seguir outro caminho.

## Reversão

Restaure o upstream DNS/encaminhamento anterior no roteador, renove a conexão dos aparelhos e confirme navegação. Só depois pare o serviço:

```bash
python ~/apps/homedns/source/scripts/control.py stop
```

Não desative o DNS do celular enquanto o roteador ainda depende dele. O projeto não abre portas de internet e não instala um segundo DHCP na rede.
