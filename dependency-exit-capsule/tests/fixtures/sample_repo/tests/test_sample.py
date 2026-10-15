from sample_app.core import compute_total, load_data

def test_compute():
    assert compute_total(2, 3) == 5

def test_load():
    res = load_data("hello")
    assert res["len"] == 5

def test_toml_presence():
    import sample_app.config
    assert hasattr(sample_app.config, "parse_config")
