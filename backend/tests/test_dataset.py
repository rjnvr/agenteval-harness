from backend.app.dataset import load_seed_data


def test_seed_dataset_has_20_cases() -> None:
    seed = load_seed_data()

    assert len(seed["documents"]) == 20
    assert len(seed["cases"]) == 20
    assert all(case["expected_facts"] for case in seed["cases"])

