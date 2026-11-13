# Como colocar este projeto no GitHub

Passo a passo, do zero.

---

## 1. Criar o repositório

1. Entre em [github.com](https://github.com) e faça login.
2. Clique no **+** no canto superior direito → **New repository**.
3. Nome sugerido: `freetv-br-m3u`
4. Marque **Public** (precisa ser público para o SS IPTV conseguir ler o link).
5. **Não** marque para criar README, .gitignore ou licença.
6. Clique em **Create repository**.

---

## 2. Enviar os arquivos

### Jeito mais fácil (pelo navegador)

1. Na página do repositório recém-criado, clique em **uploading an existing file**.
2. Arraste **todos** os arquivos da pasta do projeto, **mantendo a estrutura de pastas**.
3. Escreva uma mensagem qualquer e clique em **Commit changes**.

> A pasta `.github` costuma ficar oculta no Windows. Para vê-la: no Explorador de Arquivos, aba **Exibir** → marque **Itens ocultos**.
> Se não conseguir enviar a pasta `.github` pelo navegador, crie o arquivo manualmente: **Add file → Create new file**, digite `.github/workflows/atualizar.yml` como nome (as barras criam as pastas) e cole o conteúdo do arquivo.

### Pelo Git (se já usa)

```bash
cd freetv-br-m3u
git init
git add .
git commit -m "Projeto inicial"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/freetv-br-m3u.git
git push -u origin main
```

---

## 3. Liberar a atualização automática

1. No repositório, vá em **Settings** → **Actions** → **General**.
2. Em **Workflow permissions**, marque **Read and write permissions**.
3. Clique em **Save**.

Sem isso, o robô consegue gerar a lista, mas não consegue publicá-la.

---

## 4. Rodar a primeira vez

1. Aba **Actions**.
2. Se aparecer aviso pedindo para habilitar, clique em **I understand my workflows, go ahead and enable them**.
3. Clique em **Atualizar lista M3U (FreeTV Brasil)** na lista da esquerda.
4. Clique em **Run workflow** → **Run workflow**.
5. Aguarde de 3 a 6 minutos. Ao terminar, o arquivo `freetv_br.m3u` aparece no repositório.

---

## 5. Pegar o link para o SS IPTV

O link é assim:

```
https://raw.githubusercontent.com/SEU_USUARIO/freetv-br-m3u/main/freetv_br.m3u
```

Troque `SEU_USUARIO` pelo seu nome de usuário no GitHub.

Dica: abra esse link no navegador. Se aparecer o texto começando com `#EXTM3U`, está tudo certo.

---

## 6. (Opcional) Rodar no Brasil e publicar

Para o teste ficar mais fiel, rode no seu PC:

1. Instale o Python ([python.org](https://www.python.org/downloads/)), marcando **Add python.exe to PATH**.
2. Clique com o botão direito na pasta do projeto → **Git Bash Here** (ou abra o Prompt de Comando na pasta).
3. Execute `rodar_no_brasil.bat` para gerar e conferir.
4. Execute `publicar.bat` para enviar ao GitHub.

Se o `publicar.bat` reclamar que o Git não está configurado, rode uma vez:

```
git config --global user.name "Seu Nome"
git config --global user.email "seu@email.com"
```

---

## Problemas comuns

**O Actions falhou com "Resource not accessible by integration"**
→ Faltou o passo 3 (permissões de escrita).

**O Actions falhou com "rejected ... fetch first"**
→ Normal quando duas execuções se cruzam. O próprio workflow tenta de novo 5 vezes. Se persistir, rode manualmente outra vez.

**A lista tem poucos canais**
→ Provavelmente a primeira execução rodou sem testar. Veja o `relatorio.json` e confira a linha "Inconclusivos". Canais inconclusivos **entram** na lista normalmente; só não entram os com link realmente quebrado.

**O SS IPTV não mostra os canais novos**
→ Ele guarda cache. Remova a playlist e adicione o link de novo.

**O comando `python` abre a Loja da Microsoft**
→ É o atalho falso do Windows. Instale o Python do site oficial marcando "Add python.exe to PATH".
