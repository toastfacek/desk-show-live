def test_public_imports():
    from obs_harness.director import decide
    from obs_harness.player_obs import ObsPlayer

    assert callable(decide)
    assert ObsPlayer
