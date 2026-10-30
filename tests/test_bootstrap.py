"""Exercise first-install framework restoration without installing packages."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('pwsh') or shutil.which('powershell')
pytestmark = pytest.mark.skipif(not POWERSHELL or not shutil.which('git'), reason='PowerShell and Git required')


def git(directory, *args):
    result = subprocess.run(['git', '-C', str(directory), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def framework(tmp_path):
    source = tmp_path / 'framework-source'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    (source / 'ok').mkdir()
    (source / 'ok/__init__.py').write_text('# test framework\n', encoding='utf-8')
    (source / 'pyproject.toml').write_text('[project]\nname="test-framework"\n', encoding='utf-8')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Bootstrap Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Test framework')
    return source, git(source, 'rev-parse', 'HEAD')


def run_bootstrap(project, framework):
    source, revision = framework
    script = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
    script = script.replace('https://github.com/ok-oldking/ok-script.git', source.as_posix())
    script = script.replace('2424dc7da0c4a16e716fade8377b69871229c479', revision)
    (project / 'bootstrap.ps1').write_text(script, encoding='utf-8-sig')
    # Stop at virtualenv creation: no package installation or game input.
    command = "function global:py { throw 'FRAMEWORK_READY' }; try { & './bootstrap.ps1' } catch { Write-Output $_.Exception.Message }"
    result = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
                            cwd=project, env={**os.environ, 'GIT_ALLOW_PROTOCOL': 'file', 'GIT_TERMINAL_PROMPT': '0'},
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
    assert result.returncode == 0, result.stderr
    assert 'FRAMEWORK_READY' in result.stdout, result.stdout + result.stderr


def test_archive_install_restores_exact_framework_revision(tmp_path, framework):
    project = tmp_path / 'archive'
    project.mkdir()
    run_bootstrap(project, framework)
    assert (project / 'ok-script/ok/__init__.py').is_file()
    assert git(project / 'ok-script', 'rev-parse', 'HEAD') == framework[1]


def test_plain_git_clone_initializes_framework_submodule(tmp_path, framework):
    project = tmp_path / 'clone'
    project.mkdir()
    git(project, 'init', '-b', 'main')
    git(project, 'config', '-f', '.gitmodules', 'submodule.ok-script.path', 'ok-script')
    git(project, 'config', '-f', '.gitmodules', 'submodule.ok-script.url', framework[0].as_posix())
    git(project, 'update-index', '--add', '--cacheinfo', f'160000,{framework[1]},ok-script')
    run_bootstrap(project, framework)
    assert (project / 'ok-script/ok/__init__.py').is_file()
    assert git(project / 'ok-script', 'rev-parse', 'HEAD') == framework[1]


def test_existing_framework_is_preserved(tmp_path, framework):
    project = tmp_path / 'existing'
    project.mkdir()
    git(project, 'clone', str(framework[0]), 'ok-script')
    marker = project / 'ok-script/local-work.txt'
    marker.write_text('preserve local work', encoding='utf-8')
    run_bootstrap(project, framework)
    assert marker.read_text(encoding='utf-8') == 'preserve local work'
    assert git(project / 'ok-script', 'rev-parse', 'HEAD') == framework[1]
