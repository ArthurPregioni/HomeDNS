# HomeDNS

AdGuard Home em um celular Android com Termux, para bloquear domínios de anúncios e rastreadores. Este repositório contém instalação, operação e diagnóstico; o mecanismo de DNS é o projeto [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome).

**Um serviço instalado no celular ainda precisa ser conectado ao DNS do roteador.** Android sem root normalmente impede escutar na porta 53. Por isso, esta instalação usa a porta **1053, UDP e TCP**. O roteador precisa aceitar um servidor DNS com porta personalizada ou encaminhar suas consultas para essa porta na LAN. Apenas colocar o IP do celular no campo DNS do DHCP **não funciona** neste cenário.

## Como a rede vai funcionar

```text
Dispositivos → DNS do roteador:53 → celular:1053 → resolvedor externo por HTTPS
                                    ↓
                         domínios bloqueados localmente
```

O celular fica ligado e conectado ao Wi-Fi. O computador só é necessário para instalação/administração por USB. O serviço tem diretórios, usuário do painel, logs e inicialização próprios; não depende do RockShowBot.

## Requisitos

- Android ARM64, Termux com Python, `termux-services` e `termux-wake-lock` disponíveis.
- Autoinicialização do Termux configurada e restrições de bateria removidas. No Termux do Google Play e no Termux:Boot existem mecanismos diferentes; valide a inicialização real no aparelho.
- Reserva DHCP para o celular e acesso ao painel do roteador.
- Para ativar na rede sem root: roteador com suporte a porta de upstream DNS personalizada/encaminhamento DNS na LAN. Port forwarding **da internet para a LAN não é essa função**.

O instalador não faz root, não desbloqueia bootloader, não altera DHCP e não abre portas no roteador.

## Instalação

### Termux do Google Play

O executável Linux oficial estático pode falhar com `unexpected e_type: 2`. Para essa distribuição, compile o código upstream para Android/ARM64 em modo PIE. O script verifica o commit fixado, usa os lockfiles upstream e registra o SHA-256 do artefato. Inclui somente uma adaptação de argumentos em `config/android-argv.go`, pois o lançador dessa distribuição duplica o nome do executável. O mecanismo de filtragem não é alterado.

No computador, com Git, **Go 1.27.3**, Node.js 24 LTS e npm:

```bash
cd HomeDNS
python3 scripts/build-android.py
```

O resultado está em `.cache/android-arm64/`. Copie o repositório e o conteúdo dessa pasta (incluindo `hash-password`, `provenance.json` e a licença) para o celular. Pelo Termux/SSH, execute:

```bash
python ~/apps/homedns/source/scripts/install.py \
  --lan 192.168.1.0/24 \
  --bind-address 192.168.1.10 \
  --binary ~/apps/homedns/artifact/AdGuardHome
```

Substitua a sub-rede e o IP pelos seus. O arquivo `provenance.json` precisa estar ao lado do binário. Não use os endereços do exemplo sem conferir a rede real. O DNS escuta em localhost e nesse IP específico: isso evita publicar na interface celular e evita uma enumeração de interfaces que o Android restringe. Reserve esse IP no roteador.

O instalador gera a configuração diretamente, usando bcrypt para a senha; o assistente upstream exige permissão para a porta 53 antes de começar. O utilitário `hash-password` recebe a senha somente por stdin e serve apenas para gerar o hash na configuração. Não concede permissões adicionais.

O instalador recusa portas ocupadas. Para executar novamente, primeiro pare **somente** o serviço `homedns`. Ele preserva o usuário existente; reaplicar a instalação restaura os padrões de rede, proteção e privacidade descritos aqui. Para ajustes cotidianos, use o painel.

## Painel e operação

O painel escuta apenas em `127.0.0.1:13000` no celular, com uma senha aleatória própria. Para acessar pelo computador com depuração USB já autorizada:

```bash
adb forward tcp:13000 tcp:13000
```

Abra **http://127.0.0.1:13000**. O login está em `~/.config/homedns/login.json` **no celular**, com permissão 600. Não envie esse arquivo, nem credenciais ou backups para Git.

Dentro do Termux/SSH:

```bash
python ~/apps/homedns/source/scripts/control.py status
python ~/apps/homedns/source/scripts/control.py refresh
python ~/apps/homedns/source/scripts/control.py logs
python ~/apps/homedns/source/scripts/control.py restart
python ~/apps/homedns/source/scripts/control.py backup
```

`stop` desativa também a partida após reboot; `start` a reativa. `backup` pausa brevemente só o HomeDNS para copiar configuração e dados consistentes, restaurando o estado de execução. O backup contém credenciais e fica fora do repositório.

Padrões iniciais: filtros padrão do AdGuard Home, atualização de listas a cada 24h, upstreams Quad9/Cloudflare por HTTPS, consultas aceitas somente de localhost e da sub-rede indicada, painel restrito a localhost, histórico detalhado de consultas desativado. Estatísticas agregadas podem conter nomes de domínios; são dados privados. Nenhum painel nem DNS é publicado por túnel na internet.

## Antes de trocar o DNS do Wi-Fi

Siga [a ativação e reversão no roteador](docs/router.md). Se os controles estiverem bloqueados pela operadora, use [este pedido de liberação](docs/operator-request.md). Teste pelo computador na mesma rede:

```bash
python3 scripts/check.py IP_DO_CELULAR --port 1053
```

Isso verifica UDP/TCP, resolução de um site comum e bloqueio de um domínio de publicidade para A e AAAA. Não altera o DNS do computador. Depois da mudança no roteador, repita contra **o IP do roteador na porta 53** e confira um segundo aparelho.

## Limites

- DNS não remove todos os anúncios: os que usam o mesmo domínio do conteúdo, como muitos anúncios do YouTube, não são separáveis dessa forma. [Limitações do AdGuard Home](https://adguard-dns.io/kb/adguard-home/faq/).
- VPN, DNS privado/DoH próprio e redes de convidados podem não usar o DNS distribuído pelo roteador. O DNS IPv6 também precisa ser configurado; não basta alterar só o IPv4.
- Se o celular cair e for o único upstream funcional do roteador, a resolução para a rede para. Um DNS público comum como secundário permite escapar do bloqueio também durante o uso normal. Escolha disponibilidade/bloqueio conscientemente.
- Instalar PRoot ou rodar uma distribuição Linux dentro do Termux não concede permissão real para a porta 53. Root exige avaliação separada, inclusive risco de perda de dados em desbloqueio de bootloader.

## Organização e QA

```text
config/   versões e checksums públicos
docs/     ativação, limitações e reversão
scripts/  instalação, compilação, operação e diagnóstico
tests/    validação dos controles e do diagnóstico DNS
```

Binários, dependências de compilação, senhas, configuração real, consultas e backups não são versionados. Não há dependências Python externas para operar os scripts.

```bash
python3 -m unittest discover -s tests -v
```

Os scripts deste repositório estão sob MIT. AdGuard Home e suas dependências mantêm suas próprias licenças; preserve a GPL do AdGuard Home e os termos de distribuição ao redistribuir binários.
