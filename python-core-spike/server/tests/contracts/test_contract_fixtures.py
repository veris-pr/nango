from scripts.check_contract_fixtures import check_fixtures


def test_contract_fixtures_match_python_dtos() -> None:
    assert check_fixtures() == []
