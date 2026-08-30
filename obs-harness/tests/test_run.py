from run import main


def test_live_mode_refused():
    assert main(["--mode", "live"]) == 2


def test_obs_without_server_exits_2():
    assert main(["--player", "obs"]) == 2
