# J3M Connect

Plugin Python/PyQGIS para consultar a API de integrações do J3M e carregar coletas no mapa. Versão **0.1.0**, experimental, em desenvolvimento. O backend mantém autenticação, autorização e regras de negócio; o plugin cuida da configuração, comunicação, apresentação e camadas.

## Requisitos

- QGIS 3.28 a 3.99, com Python e provedor OGR (incluídos no QGIS).
- Nenhuma dependência Python externa. QGIS 4 ainda não é suportado.
- Para acesso remoto, URL da API e credenciais fornecidas pelo J3M.

## Instalação local

O pacote pronto está em `dist/j3m_connect-0.1.0.zip`. No QGIS, abra **Complementos → Gerenciar e instalar complementos → Instalar a partir do ZIP**, selecione o pacote e habilite **J3M Connect**. O plugin aparece no menu Complementos e na barra de ferramentas.

Para gerar novamente o ZIP, execute na raiz com Python 3:

```powershell
python scripts/package.py
```

Alternativamente, em **Configurações → Perfis de usuário → Abrir pasta do perfil ativo**, copie a pasta `j3m_connect` para `python/plugins` (crie essas subpastas se necessário), reinicie o QGIS e habilite o complemento. No Windows, o perfil padrão normalmente fica em `%APPDATA%/QGIS/QGIS3/profiles/default`.

## Configuração

As configurações globais ficam em `j3m_connect/config.json`, incluído no ZIP publicado:

```json
{
  "api_url": "https://j3m-public-api-47f36ac58e86.herokuapp.com"
}
```

Para alterar o backend da distribuição, edite `api_url` nesse arquivo e gere novamente o pacote com `python scripts/package.py`. O arquivo é destinado ao versionamento e contém somente configurações públicas; não coloque credenciais nele. O empacotamento verifica se existe uma URL preenchida e aceita somente a chave `api_url` nesta versão.

Após instalar, o usuário abre o plugin com **API URL** preenchida pela configuração distribuída e informa **Client ID** e **Client Secret**. Não é necessário criar arquivos locais. Não há leitura de `.env` nem de variáveis de ambiente para configurar o backend, nem URL fixa no código Python.

Uma URL personalizada e salva pela interface tem prioridade sobre `config.json`. Atualizar o pacote não substitui essa preferência já salva; nesse caso, altere a URL pela interface. Reinicie o QGIS após atualizar os arquivos do plugin. Se não houver URL salva e o arquivo estiver ausente, inválido ou sem `api_url`, o campo fica vazio e o plugin exige uma URL antes de consultar.

A URL é a base da API, podendo incluir um prefixo de caminho; não inclua `/sessions`, parâmetros, fragmentos ou credenciais na URL. HTTPS é obrigatório, exceto HTTP em `localhost`, `127.0.0.1` ou `::1`, para desenvolvimento local.

Clique em **Salvar configuração**. O QGIS poderá solicitar a criação/desbloqueio da senha mestra. Client ID e Client Secret ficam no banco de autenticação criptografado do QGIS, em uma configuração Basic usada apenas como armazenamento. As chamadas usam os cabeçalhos `X-Client-Id` e `X-Client-Secret`, não HTTP Basic. Somente a URL e o identificador da configuração de autenticação ficam em QgsSettings. Deixe o campo de segredo vazio para manter o segredo já salvo; ele nunca é repopulado na interface. **Remover configuração** apaga essa entrada do cofre e as preferências do plugin.

## Utilização

1. Salve a configuração e clique em **Atualizar sessões**.
2. Selecione uma sessão para consultar seus indicadores.
3. Clique em **Adicionar ao mapa** para buscar e carregar GeoJSON.

Indicadores são exibidos como JSON formatado, dinamicamente, sem cálculos nem nomes fixos. Respostas vazias, falhas de rede e erros de formato são informados na janela. Fechar a janela cancela a requisição pendente. Redirecionamentos são recusados para evitar encaminhar credenciais; configure a URL final.

## Contrato e pontos de adaptação

Somente estas rotas são conhecidas:

- `GET /sessions`
- `GET /sessions/{session}/indicators`
- `GET /sessions/{session}/collections?format=geojson`

**Os payloads ainda não são definitivos.** `adapters.py:session_choices` é o ponto de adaptação entre a resposta de sessões e pares internos `(identificador, texto)`. Para ensaio inicial, aceita exclusivamente uma lista JSON de identificadores textuais ou inteiros, usando o próprio identificador como texto. Objetos/envelopes são recusados com orientação explícita para adaptar a função quando o contrato real estiver disponível; não são presumidos campos `id`, `name` ou similares. `indicator_text` apresenta qualquer JSON sem definir um esquema de indicadores. O carregamento aceita GeoJSON direto (`FeatureCollection` ou `Feature`), sem presumir envelopes da API.

## Desenvolvimento e validação manual

- `j3m_connect.py`: lifecycle, menu e barra de ferramentas.
- `dialog.ui` / `dialog.py`: formulário Qt Designer e fluxo da interface.
- `settings.py`: URL e cofre de autenticação QGIS.
- `api.py`: HTTP assíncrono via QgsNetworkAccessManager, timeout de 30 segundos e limite de resposta de 20 MiB.
- `adapters.py`: adaptação simples das respostas em desenvolvimento.
- `layers.py`: validação e carregamento de GeoJSON via OGR.
- `scripts/package.py`: empacotamento local, sem dependências.

Use o Python fornecido pelo QGIS para executar código que importe `qgis`. Edite o `.ui` no Qt Designer ou diretamente; ele é carregado em runtime e não exige compilação. Após alterações, desabilite/habilite o plugin e reinicie o QGIS para recarregar todos os módulos com segurança.

Para validar GeoJSON sem API, no console Python do QGIS:

```python
from j3m_connect.layers import add_geojson_layer
sample = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"exemplo": "Validação local"},
     "geometry": {"type": "Point", "coordinates": [-46.63, -23.55]}}
]}
layer = add_geojson_layer(sample, "J3M — validação local")
iface.setActiveLayer(layer)
iface.zoomToActiveLayer()
```

Verifique também a abertura/fechamento da janela, desativação do complemento, configuração incompleta, URL inválida e respostas 401/403, 404, 500, JSON inválido e ausência de dados quando houver API de desenvolvimento disponível. Não há testes unitários nesta etapa.

## Estado e limitações

Estrutura instalável e fluxos implementados; integração com a API real depende do contrato de sessões e de credenciais válidas. Não inclui edição, envio de coletas, criação de sessões, processamento espacial, filtros avançados, cache ou sincronização offline.

As camadas são cópias locais estáticas em GeoJSON, armazenadas em `j3m_connect/layers` dentro do perfil ativo do QGIS. Esses arquivos permanecem após fechar o plugin, permitindo reabrir projetos; não os apague enquanto houver projetos referenciando-os. Cada carregamento gera um arquivo novo. Para compartilhar um projeto, exporte/empacote também as camadas. Os dados locais não são criptografados pelo plugin. Respostas vazias não criam camadas. Coleções com geometrias mistas dependem do suporte do OGR/QGIS e não são divididas automaticamente.

Distribuição local pronta. Publicação no catálogo oficial ainda requer definir e preencher email de manutenção e URL real do repositório em `metadata.txt`; estes dados não foram inventados.

Validação inicial executada com PyQGIS **3.44.13** no Windows, em modo sem janela e perfil temporário: imports/sintaxe, formulário Qt, lifecycle com interface simulada, cofre de autenticação real, HTTP contra servidor local temporário e camada GeoJSON via OGR. A API J3M real e a interação visual no QGIS Desktop ainda precisam ser verificadas. As demais versões declaradas não foram executadas neste ambiente.

## Licença e referências

GPL-3.0-or-later, conforme `LICENSE`. Estrutura baseada na [documentação oficial de plugins QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/plugins/plugins.html), com credenciais no [sistema de autenticação QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/authentication.html).
