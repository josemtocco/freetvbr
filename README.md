# FreeTV Brasil → M3U para SS IPTV

Projeto que gera automaticamente uma lista **M3U** com os canais de TV brasileiros do site [freetv.studio](https://freetv.studio/pt/country/BR), organizada nas categorias originais do site, e a mantém atualizada **a cada 6 horas** no GitHub.

O arquivo gerado é o **`freetv_br.m3u`**. Basta colar o link dele no SS IPTV.

---

## O que ele faz

1. **Coleta todos os canais** do Brasil:
   - percorre a página "todos os canais";
   - percorre **cada categoria** do site, exatamente como ela aparece no site;
   - lê também o `sitemap.xml`, que revelou **100 canais que não aparecem na vitrine** (ficam escondidos, mas tocam normalmente).
2. **Lê a página de cada canal** para pegar nome, logo, categoria e o link de transmissão.
3. **Testa se o link está tocando de verdade**: baixa o manifesto HLS e um pedaço real do vídeo (segmento `.ts`). Não é só verificar se o endereço responde — é confirmar que existe vídeo saindo.
4. **Reconcilia com a atualização anterior**:
   - mantém os canais que estão funcionando;
   - **remove um canal só depois de 6 atualizações seguidas com falha**;
   - adiciona automaticamente os canais novos que aparecerem;
   - reativa um canal caso ele volte a funcionar antes de ser removido.
5. **Gera o M3U** agrupado por categoria, com nome e logo de cada canal.

---

## Categorias

As categorias vêm do próprio site e são mantidas como estão:

Geral · Notícias · Religioso · Entretenimento · Educação · Filmes · Cultura · Esportes · Música · Ao Ar Livre · Infantil · Clássicos · Legislativo · Séries · Viagem · Comédia · Documentário · Público · Compras · Animação · Estilo de Vida · Outros

> Canais sem categoria no site recebem uma categoria estimada pelo nome (ex.: TV Senado → Legislativo). O que não for possível identificar fica em **Outros**.

---

## Como usar no SS IPTV

1. Abra o SS IPTV e vá em **Configurações → Playlist / Conteúdo**.
2. Escolha **Adicionar playlist por link (URL)**.
3. Cole o endereço abaixo, trocando `SEU_USUARIO` e `SEU_REPOSITORIO`:

```
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/freetv_br.m3u
```

4. Confirme e atualize a lista.

**Importante:** o SS IPTV guarda a lista em cache. Quando a lista for atualizada com novos canais, remova a playlist e adicione de novo, para ele recarregar.

---

## Como funciona a atualização automática

O arquivo `.github/workflows/atualizar.yml` roda **de 6 em 6 horas** (00:00, 06:00, 12:00 e 18:00 UTC — no horário de Brasília, 21:00, 03:00, 09:00 e 15:00).

A cada execução ele:
- gera a lista de novo;
- testa os canais;
- publica o `freetv_br.m3u` e o `estado_canais.json` no repositório.

Você também pode disparar na mão: aba **Actions → Atualizar lista M3U → Run workflow**.

---

## Sobre os canais que não tocam fora do Brasil

Este é o ponto mais importante do projeto e ele foi tratado de propósito.

O GitHub Actions roda em servidores **fora do Brasil**. Muitos servidores de TV brasileiros **bloqueiam conexões de fora do país**. Se o script tratasse isso como "canal quebrado", a lista se esvaziaria sozinha: em 6 execuções (36 horas) metade dos canais sumiria, mesmo estando perfeitos.

Por isso o teste separa três situações:

| Resultado | O que significa | Conta como falha? |
|---|---|---|
| **Tocando** | Baixou um pedaço real de vídeo | — |
| **Link quebrado** | Erro 404/410, endereço não é HLS, segmento vazio | **Sim** |
| **Inconclusivo** | Sem conexão, timeout, erro 403/5xx (bloqueio de região) | **Não** |

Ou seja: falha de rede ou bloqueio geográfico **nunca** remove um canal. Só some da lista quem realmente está com o link rompido, e ainda assim depois de 6 atualizações seguidas.

---

## Rodar no seu PC (recomendado de vez em quando)

Rodando do Brasil, o teste fica muito mais fiel: os canais bloqueados para estrangeiros vão aparecer como **tocando**.

1. Instale o Python em [python.org](https://www.python.org/downloads/) marcando **"Add python.exe to PATH"**.
2. Dê dois cliques em **`rodar_no_brasil.bat`**.
3. Para publicar o resultado no GitHub, use **`publicar.bat`**.

O `.bat` já roda com teste completo de todos os canais.

---

## Opções avançadas

```bash
python freetv_br.py                      # uso normal
python freetv_br.py --testar-tudo         # testa todos, mesmo os já aprovados
python freetv_br.py --sem-teste           # só coleta e monta a lista
python freetv_br.py --sem-reconciliar     # não mexe no estado nem remove nada
python freetv_br.py --incluir-instaveis   # inclui também canais que falharam no teste
python freetv_br.py --limite-falhas 10    # muda o limite (padrão: 6)
python freetv_br.py --debug               # log detalhado
```

---

## Arquivos do projeto

| Arquivo | Para que serve |
|---|---|
| `freetv_br.m3u` | **A lista pronta para o SS IPTV** (gerada) |
| `freetv_br.py` | O programa que faz tudo |
| `estado_canais.json` | Memória entre atualizações (contador de falhas, links aprovados) |
| `relatorio.json` | Resumo da última execução |
| `resumo.py` | Monta o resumo mostrado no GitHub Actions |
| `rodar_no_brasil.bat` | Roda tudo no seu PC com teste completo |
| `publicar.bat` | Gera e envia a lista para o GitHub |
| `.github/workflows/atualizar.yml` | Automação das 6 horas |

---

## Requisitos

- Python 3.8 ou superior.
- Nenhuma biblioteca extra: usa só o que já vem no Python.

---

## Observações

- Todos os links apontam para transmissões públicas que o próprio freetv.studio divulga. O projeto não hospeda nem redistribui conteúdo: apenas organiza em formato M3U o que já está publicado naquele site.
- Se o site mudar o formato das páginas, o script avisa no log (`[aviso]`) e continua usando os dados da execução anterior, sem zerar a lista.
