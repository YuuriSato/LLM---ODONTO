"""Fail CI if runtime images, evidence, history, or credentials are tracked."""
import subprocess

paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
forbidden = [path for path in paths if path == '.env' or path.startswith('runtime/')]
if forbidden:
    raise SystemExit('Arquivos privados rastreados: ' + ', '.join(forbidden))
print('Nenhum arquivo privado de runtime ou .env rastreado.')
