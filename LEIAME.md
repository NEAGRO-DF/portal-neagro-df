# Portal NEAGRO-DF

Portal do Núcleo de Estudos sobre o Agronegócio do Distrito Federal (NEAGRO-DF), FAV/UnB. Site estático (HTML, CSS e JavaScript sem dependências), com os boletins em destaque e dados públicos do agronegócio do DF, da RIDE, do Brasil e do mundo atualizados por um robô.

## Estrutura

| Caminho | Função |
|---|---|
| `index.html` | Página pronta para publicar. Gerada a partir de `src/index.template.html`; não editar à mão. |
| `src/index.template.html` | Modelo da página (layout, estilos e código). |
| `data/boletins.json` | Catálogo de boletins. **É o arquivo que a equipe edita a cada edição.** |
| `data/manual.json` | Indicadores Cepea/Esalq lançados pela coordenação (o Cepea não oferece API pública). |
| `data/dados.json` | Dados do portal, regravados pelo robô. Cada item traz fonte, link, endpoint e data de extração. |
| `data/contato.json` | Canais do Fale conosco (e-mail, telefone, endereço, Instagram). Para o formulário enviar mensagens diretamente, informe em `formulario_endpoint` o endereço de um serviço de formulários; vazio, ele prepara a mensagem para o visitante enviar pelo próprio e-mail. |
| `data/painel.json` | Retrato dos indicadores do mês (relações de troca, séries de 13 meses para os gráficos, preços do DF, índices, GTA e alertas de conferência), gravado pelo robô. Não traz o endereço do painel. |
| `src/painel-calc.js` | Cálculo do semáforo, igual à aba Metodologia do painel. Usado pela página e pelo robô. Ajustar aqui se o painel mudar nomes de campos ou praças. |
| `scripts/painel.js` | Robô de integração com o painel (Node 18+, sem dependências): lê as coleções meses, lancamentos e indices e o quadro GTA_DF. |
| `data/fontes_noticias.json` | Feeds RSS de notícias lidos pelo robô. |
| `scripts/atualizar_dados.py` | Robô: Banco Central (SGS), IBGE (SIDRA), FAO e RSS. Só biblioteca padrão do Python. |
| `scripts/montar_site.py` | Insere o retrato dos dados no `index.html`, para a página funcionar mesmo off-line. |
| `.github/workflows/atualizar.yml` | Agenda o robô duas vezes por dia útil no GitHub Actions. |
| `img/` | Logotipos do NEAGRO-DF e da UnB (PNG com fundo transparente), extraídos do boletim de suinocultura. |
| `img/fotos/` e `data/fotos.json` | Fotografias reais das cadeias, com licença livre (Wikimedia Commons). O crédito de autor e licença aparece em cada foto e na seção de fontes. Para usar fotos próprias da equipe, troque o arquivo e atualize o crédito em `data/fotos.json`. |

## Integração com o painel (uso interno)

O Painel de Relações de Troca (https://neagrodf.netlify.app/) é de uso interno da equipe e não tem link no portal. Os grupos continuam lançando os dados no painel; a seção **Indicadores** do portal mostra apenas resultados selecionados e gráficos: cinco relações de troca em destaque, a evolução de 13 meses com média e faixa normal, o resumo de variações, a contagem do semáforo, quatro preços do DF e a movimentação de animais (GTA). A regra é a mesma do painel (IRT = insumo ÷ produto; favorável abaixo de 95% da média dos meses registrados, desfavorável acima de 105%).

Base lida: `https://firestore.googleapis.com/v1/projects/neagro---df/databases/(default)/documents/{meses,lancamentos,indices}` e o quadro `GTA_DF` no código do painel.

### Conferência automática

`src/painel-calc.js` confere a base a cada leitura e grava os alertas em `data/painel.json`:

- **Estrutura** (campo usado pelo portal que não existe mais ou sumiu no mês, semáforo com menos de 19 relações, quadro GTA_DF ilegível). A etapa "Conferir a integração com o painel" do GitHub Actions falha e o GitHub avisa por e-mail. Corrija os nomes em `src/painel-calc.js` (listas `RELACOES`, `RESUMO`, `PRECOS_DF` e `PRACAS`).
- **Valor atípico** (praça com menos da metade ou mais de 1,5 vez a mediana das demais praças do mesmo produto, ou variação acima de 40% sobre o mês anterior). Aparece como aviso no resumo da execução; se o campo entra num destaque do portal, o cartão mostra "Valor em conferência pela equipe".

Para conferir manualmente: `node scripts/painel.js --verificar`.

## Demandas do Fale conosco

O formulário funciona como canal de demandas. Para recebê-las na base do painel, publique no Firebase a regra da coleção `demandas` (ver o guia de implantação, seção 6) e troque `firestore_demandas` para `true` em `data/contato.json`. Enquanto isso, o formulário prepara a mensagem para o visitante enviar a secgeagro@unb.br.

## Fluxo mensal do boletim

1. Depois da revisão final, salve o PDF na pasta do ano no Google Drive e copie o link direto do arquivo (Compartilhar, qualquer pessoa com o link).
2. Em `data/boletins.json`, acrescente a nova edição **no início** da lista `edicoes`, com `numero`, `data`, `titulo`, `cadeias`, `resumo`, até três `destaques` e o link em `pdf`. Remova o campo `pdf_e_pasta` quando o link for de um arquivo.
3. Grave a alteração no repositório. O GitHub Actions remonta a página e o boletim passa a aparecer em destaque.

## Indicadores Cepea (semanal)

Atualize valor, data de referência e variação de boi gordo, soja e milho em `data/manual.json`, conferindo no site do Cepea. Para incluir outro indicador (suíno, frango, ovos, leite, bezerro), copie um bloco existente com novo `id`, `nome`, `unidade` e `casas`.

## Implantação no domínio da UnB

O passo a passo completo, com as normas, os modelos de e-mail à Secom e de chamado à STI e a rotina de manutenção, está no documento **Guia de implantação do Portal NEAGRO-DF** (Word), entregue junto com este pacote. Resumo:

1. **GitHub:** criar o repositório com estes arquivos, permitir gravação para o Actions (Settings > Actions > General > Workflow permissions > Read and write) e ativar o GitHub Pages (Settings > Pages > Deploy from a branch > main / root). O portal fica disponível em um endereço do tipo `https://USUARIO.github.io/REPOSITORIO`.
2. **WordPress de neagrodf.unb.br (caminho recomendado):** colar o conteúdo de `wordpress/bloco-html-elementor.html` num widget HTML do Elementor na página inicial, trocando `ENDERECO_DO_PORTAL` pelo endereço do GitHub Pages. O tema da UnB continua responsável pela barra do Governo Federal, pelo VLibras e pelo rodapé; o portal entra em modo incorporado (`?modo=wp`), sem cabeçalho e rodapé próprios, e ajusta a própria altura.
3. **Endereço próprio (alternativa):** pedir à STI, pelo servicostic.unb.br, um registro CNAME apontando para `USUARIO.github.io` e informar o domínio em Settings > Pages > Custom domain. Nesse caso a página exibe sozinha a barra do Governo Federal, o VLibras e o rodapé institucional.

Mesmo sem o robô, o navegador do visitante tenta consultar o Banco Central na abertura da página e atualiza câmbio, Selic e IPCA; se a consulta falhar, vale o último retrato salvo.

## Fontes automáticas

| Dado | Endpoint |
|---|---|
| Dólar comercial (compra) | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados/ultimos/20?formato=json` |
| Selic meta | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json` |
| IPCA 12 meses | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/12?formato=json` |
| PAM, DF | `https://apisidra.ibge.gov.br/values/t/5457/n3/53/v/215/p/last%201/c782/allxt` |
| PAM, RIDE (34 unidades) | `https://apisidra.ibge.gov.br/values/t/5457/n6/{códigos}/v/215/p/last%201/c782/0` |
| PPM, DF | `https://apisidra.ibge.gov.br/values/t/3939/n3/53/v/all/p/last%201/c79/allxt` |
| Índice FAO | CSV localizado em `https://www.fao.org/worldfoodsituation/FoodPricesIndex/en` |

PIB trimestral (IBGE), PIB do agronegócio (Cepea/CNA) e subíndices da FAO estão em `data/dados.json` com o link da fonte e podem ser atualizados por `data/manual.json`. Os feeds de notícias são configuráveis; os que falharem são apenas registrados no log.

## Próximas etapas sugeridas

- Ler a planilha de coleta semanal (Broadcast) e publicar no portal os preços do DF e Entorno de cada cadeia, como faz o painel.
- Módulo do PIB do agronegócio do DF e da RIDE, pela metodologia Cepea/Esalq.
- Páginas por cadeia com série histórica, no padrão das páginas de produto do Cepea.
