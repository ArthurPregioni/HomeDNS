# Pedido à operadora

Modelo de pedido para liberar a configuração necessária:

> Quero usar meu próprio servidor DNS filtrado na rede doméstica. No Nokia G-1425G-A, os campos de DNS IPv4 da LAN/WAN e de DNS IPv6 estão desabilitados no acesso fornecido. Podem disponibilizar essas configurações ou fornecer um acesso autorizado que permita ajustá-las? Preciso também saber se o firmware permite configurar o upstream do proxy DNS com uma porta personalizada, como 1053, para UDP e TCP. Se não permitir, quais opções oficiais existem para usar um roteador próprio na LAN, mantendo a conexão da operadora?

Liberar apenas o endereço DNS não basta para o Android sem root: o encaminhamento para a porta 1053 continua necessário. Bridge não é uma mudança equivalente à troca de DNS e pode afetar telefonia, TV ou a autenticação da conexão. Não solicite nem aplique bridge sem definir antes o roteador que assumirá essa função e as orientações da operadora.

O painel do AdGuard Home é administrativo e não precisa ser publicado na internet. Não é necessário abrir a porta 53 na WAN.
