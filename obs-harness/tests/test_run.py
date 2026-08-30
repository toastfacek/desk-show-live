from run import main


def test_live_mode_refused():
    assert main(["--mode", "live"]) == 2
