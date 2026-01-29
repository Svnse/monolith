@echo off
echo Creating virtual environment...
python -m venv venv

echo Activating venv...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install PySide6

echo.
echo Optional: Install LLM support?
set /p llm="Install llama-cpp-python? (y/n): "
if /i "%llm%"=="y" pip install llama-cpp-python

echo.
echo Optional: Install Audio generation?
set /p audio="Install audiocraft? (y/n): "
if /i "%audio%"=="y" pip install audiocraft torch torchaudio

echo.
echo Optional: Install Stable Diffusion?
set /p sd="Install diffusers? (y/n): "
if /i "%sd%"=="y" pip install diffusers torch transformers accelerate

echo.
echo Installation complete!
echo Run start.bat to launch Monolith
pause
