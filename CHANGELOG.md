# Changelog

## 0.1.0 — em desenvolvimento

- Estrutura inicial instalável do J3M Connect para QGIS 3.
- Ícone do pacote, menu e barra de ferramentas baseado no logotipo utilizado pelo frontend J3M.
- Interface de configuração, seleção de sessões e indicadores dinâmicos.
- Credenciais no cofre QGIS e comunicação HTTP assíncrona.
- Carregamento de GeoJSON e tratamento de erros.
- Pontos de adaptação para o contrato da API ainda em desenvolvimento.
- Adaptação aos exemplos da API de 14/09/2026: sessões em data por UUID/nome, indicadores dinâmicos em data e prefixo /v1.
- Campos aninhados de coletas expostos como colunas pelo OGR, incluindo métricas opcionais entre registros.
- Distinção entre 404 sem dados e recurso inacessível, com mensagens para HTTP 422/429.
- Configurações globais em `config.json`, distribuído no pacote, com URL personalizável pela interface e sem endereço fixo no código Python.
