@echo off
chcp 65001 >nul
title Publicar lista no GitHub
cd /d "%~dp0"

echo ============================================================
echo   Publicar lista M3U no GitHub
 echo ============================================================
echo.

REM Gera a lista primeiro
python freetv_br.py --testar-tudo
if errorlevel 1 (
    echo [ERRO] Falha ao gerar a lista.
    pause
    exit /b 1
)

git add freetv_br.m3u estado_canais.json relatorio.json
if errorlevel 1 (
    echo [AVISO] Nada novo para enviar, ou o git nao esta configurado.
)

git commit -m "Atualiza lista M3U (execucao local no Brasil)"

git pull --rebase --autostash origin main
git push origin main

if errorlevel 1 (
    echo.
    echo [AVISO] O envio falhou. Tente novamente em alguns segundos.
) else (
    echo.
    echo Lista publicada com sucesso!
)

pause
