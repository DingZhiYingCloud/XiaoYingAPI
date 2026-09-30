@echo off
rem ============================================================
rem Hongguo offline sign service (unidbg) - keep running alongside the API server
rem
rem It simulates libmetasec_ml.so on a desktop JVM to generate the fqnovel
rem security headers (X-Argus / X-Gorgon / X-Khronos / X-Ladon / ...).
rem The API server calls it at settings.HONGGUO_SIGN_URL (default
rem http://127.0.0.1:9099/sign).
rem
rem Layout (the jar resolves its resources via ../capture/...):
rem   hongguo_sign/sign/unidbg-sign.jar
rem   hongguo_sign/capture/fq_oversea/{libmetasec_ml.so, libc++_shared.so, ms_16777218.bin}
rem   hongguo_sign/jre/  (bundled trimmed JRE; used when present)
rem
rem Uses the bundled JRE (jre/) when present, otherwise JDK 17+ on PATH.
rem Press Ctrl-C to stop.
rem
rem To (re)build the bundled trimmed JRE with JDK 17+ installed:
rem   jlink --add-modules java.base,java.logging,java.management,java.naming,java.xml,java.sql,jdk.httpserver,jdk.unsupported ^
rem         --strip-debug --no-header-files --no-man-pages --compress=2 --output "%~dp0jre"
rem ============================================================
cd /d "%~dp0sign"
set "JAVA_BIN=java"
if exist "..\jre\bin\java.exe" set "JAVA_BIN=..\jre\bin\java.exe"
"%JAVA_BIN%" --add-opens java.base/java.lang=ALL-UNNAMED -cp unidbg-sign.jar com.hongguo.sign.FqTrace serve 9099
