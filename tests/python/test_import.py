import memoir


def test_ping():
    result = memoir.ping()
    print(result)
    assert result == "Memoir 0.1.0 loaded OK"


def test_version():
    assert memoir.__version__ == "0.1.0"


if __name__ == "__main__":
    test_ping()
    test_version()
    print("All Phase 1 tests passed.")
