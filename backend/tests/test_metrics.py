from datetime import date

from app.metrics.load import compute_pmc
from app.metrics.power import intensity_factor, mean_max_power, normalized_power, power_zones, tss


def test_constant_power_np_equals_power():
    watts = [200.0] * 3600
    assert abs(normalized_power(watts) - 200.0) < 1e-6


def test_one_hour_at_ftp_is_100_tss():
    watts = [250.0] * 3600
    np_ = normalized_power(watts)
    assert abs(tss(3600, np_, 250) - 100.0) < 1e-6
    assert abs(intensity_factor(np_, 250) - 1.0) < 1e-9


def test_variable_power_np_above_average():
    watts = ([100.0] * 60 + [300.0] * 60) * 30
    assert normalized_power(watts) > sum(watts) / len(watts)


def test_short_ride_np_is_zero():
    assert normalized_power([200.0] * 10) == 0.0


def test_mean_max_power():
    watts = [100.0] * 50 + [300.0] * 20 + [100.0] * 50
    assert mean_max_power(watts, [20])[20] == 300.0


def test_zones_scale_with_ftp():
    z = power_zones(200)
    assert z[3]["min"] == 180 and z[3]["max"] == 210


def test_pmc_converges_and_tsb_negative_under_load():
    daily = {date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + i): 100.0 for i in range(60)}
    rows = compute_pmc(daily)
    assert rows[-1]["ctl"] > 50
    assert rows[-1]["atl"] > rows[-1]["ctl"]
    assert rows[-1]["tsb"] < 0
