@echo off
chcp 65001 >nul
title FreeTV Brasil - Gerar lista M3U
cd /d "%~dp0"

echo ============================================================
echo   FreeTV Brasil - Gerador de lista M3U para SS IPTV
 echo ============================================================
echo.

REM --- Verifica se o Python esta instalado ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo.
    echo Instale o Python em https://www.python.org/downloads/
    echo IMPORTANTE: marque a opcao "Add python.exe to PATH" na instalacao.
    echo.
    echo ATENCAO: se o comando "python" abrir a Loja da Microsoft, e porque
    echo o Windows esta usando o atalho falso do Python. Instale do site acima.
    echo.
    pause
    exit /b 1
)

echo Rodando com este Python:
python --version
echo.

REM --- Teste completo, recomendado quando se roda do Brasil ---
REM Aqui a conexao e brasileira, entao os canais que respondem
REM normalmente vao aparecer como "tocando" de verdade.
echo Iniciando coleta e teste de reproducao dos canais...
echo Isso pode levar de 2 a 5 minutos. Aguarde.
echo.

python freetv_br.py --testar-tudo

if errorlevel 1 (
    echo.
    echo [ERRO] A execucao terminou com falha. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   PRONTO!
 echo ============================================================
echo.
echo   Arquivo gerado: freetv_br.m3u
 echo   Estado salvo em: estado_canais.json
 echo   Relatorio em: relatorio.json
 echo.
echo   Para publicar no GitHub, rode: publicar.bat
 echo.
pause
