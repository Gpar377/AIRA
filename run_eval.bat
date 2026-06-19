@echo off
echo ==============================================================
echo   AIRA Model Evaluation Launcher
echo ==============================================================
echo.

:: 1. Set environment variable for Ollama models cache
set OLLAMA_MODELS=d:\SRM KTR\projects\AIRA\bin\ollama\models
echo [1/3] Configured OLLAMA_MODELS cache directory.

:: 2. Check if Ollama port is open, if not, attempt to start it
echo [2/3] Building aira-model from Modelfile...
d:\SRM KTR\projects\AIRA\bin\ollama\ollama.exe create aira-model -f training/Modelfile
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [-] ERROR: Failed to create aira-model.
    echo     Please make sure the Ollama application is running!
    echo     Launch the Ollama desktop app or run "ollama serve" in another window.
    echo.
    pause
    exit /b %ERRORLEVEL%
)

:: 3. Run the evaluation script
echo.
echo [3/3] Running Base vs. Fine-Tuned evaluation pipeline...
python training/eval_base_vs_finetuned.py --samples 50 --base-backend gemini --base-model gemini-2.5-flash --ft-backend ollama --ft-model aira-model
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [-] ERROR: Evaluation script failed.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] Evaluation complete! Report saved to docs/eval_report_base_vs_finetuned.md
echo.
pause
