from caderno_inteligente.auth import UserStore
from caderno_inteligente.dataset_store import Database, DatasetStore
from scripts.create_user import main as create_user
from scripts.import_workbook import main as import_workbook


def test_import_writes_every_sheet_once_and_requires_replace_afterwards(tmp_path, capsys):
    target = tmp_path / "dataset.db"
    assert import_workbook(["--sqlite", str(target)]) == 0
    assert "Importadas 13 abas" in capsys.readouterr().out
    assert import_workbook(["--sqlite", str(target)]) == 1
    assert "--replace" in capsys.readouterr().err
    assert import_workbook(["--sqlite", str(target), "--replace"]) == 0
    assert DatasetStore(Database(sqlite_path=target)).version() == 2


def test_import_refuses_a_missing_workbook(tmp_path, capsys):
    assert import_workbook(["--sqlite", str(tmp_path / "x.db"), "--source", str(tmp_path / "nao-existe.xlsm")]) == 1
    assert "Planilha não lida" in capsys.readouterr().err


def test_create_user_reads_the_password_from_the_environment(tmp_path, monkeypatch):
    target = tmp_path / "dataset.db"
    monkeypatch.setenv("CI_USER_PASSWORD", "senha-forte-123")
    assert create_user(["--email", "PCP@exemplo.com", "--name", "Ana", "--sqlite", str(target)]) == 0
    assert create_user(["--email", "pcp@exemplo.com", "--sqlite", str(target)]) == 1
    monkeypatch.setenv("CI_USER_PASSWORD", "outra-senha-456")
    assert create_user(["--email", "pcp@exemplo.com", "--reset-password", "--sqlite", str(target)]) == 0
    assert UserStore(Database(sqlite_path=target)).authenticate("pcp@exemplo.com", "outra-senha-456") is not None
    assert create_user(["--email", "ninguem@exemplo.com", "--reset-password", "--sqlite", str(target)]) == 1
