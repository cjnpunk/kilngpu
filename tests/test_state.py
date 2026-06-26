from kilngpu.state import zone_for


def test_zones_are_relative_to_the_limit():
    crit = 87.0
    assert zone_for(50, crit) == "cool"      # 37 below
    assert zone_for(70, crit) == "steady"    # 17 below
    assert zone_for(78, crit) == "warm"      # 9 below
    assert zone_for(84, crit) == "hot"       # 3 below


def test_zones_track_a_different_card():
    # The same temperature is hotter on a card that throttles sooner.
    assert zone_for(74, 78) == "hot"     # 4 below a low limit
    assert zone_for(74, 110) == "cool"   # 36 below a high limit
