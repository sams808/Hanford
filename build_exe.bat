@echo off
rem One-command portable-exe release: PyInstaller build with the exclusion
rem list Dataapp/PRISM proved out on this same shared Python environment
rem (which contains torch, PyQt5, jupyter and other heavyweights that
rem would otherwise be silently bundled), plus Ember-specific exclusions
rem found by inspecting the FIRST unfiltered build (1.2 GB):
rem   - glasspy (and its own hard torch/torchvision/torchaudio/lightning
rem     dependency, ~255 MB combined) is pulled in purely because
rem     glass_science.glassnet_predict() has a lazy `from glasspy.predict
rem     import GlassNet` -- PyInstaller's static analysis discovers that
rem     import statement from source even though it's never executed
rem     during a build. Excluding glasspy directly (not just torch) is
rem     the correct fix and matches the documented design: GlassNet is
rem     Python-run-only, disabled via glassnet_available() in the exe,
rem     same tradeoff already made for Larch in Dataapp/PRISM.
rem   - kaleido/scikit-image/imageio_ffmpeg (~255 MB combined) are
rem     plotly's optional static-image-export path (fig.write_image);
rem     Ember only ever calls fig.write_html(), so these are dead weight.
cd /d "%~dp0"

py -3.11 -m PyInstaller --noconfirm --clean --windowed --name Ember ^
  --icon assets\ember.ico --add-data "assets;assets" --add-data "NOTICE.md;." ^
  --exclude-module wx --exclude-module tkinter ^
  --exclude-module PyQt5 --exclude-module PyQt6 ^
  --exclude-module IPython --exclude-module jupyter --exclude-module nbformat ^
  --exclude-module notebook --exclude-module zmq ^
  --exclude-module torch --exclude-module transformers --exclude-module tokenizers ^
  --exclude-module llvmlite --exclude-module numba ^
  --exclude-module botocore --exclude-module boto3 ^
  --exclude-module h5py --exclude-module lxml ^
  --exclude-module cryptography --exclude-module paramiko ^
  --exclude-module glasspy --exclude-module torchvision --exclude-module torchaudio ^
  --exclude-module lightning --exclude-module pytorch_lightning ^
  --exclude-module kaleido --exclude-module skimage --exclude-module scikit-image ^
  --exclude-module imageio_ffmpeg --exclude-module sympy ^
  qt_main.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo Zipping dist\Ember ...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Ember' -DestinationPath 'dist\Ember-portable.zip' -Force"
echo Done: dist\Ember-portable.zip
pause
