# tests/test_message_parser.py
# ATTITUDE mesaj kontrolü
import pytest
from types import SimpleNamespace
from PyQt5.QtTest import QSignalSpy

from adapters.mavlink.helpers.message_parser import MessageParser

# ----------------------------------------------------------------------
def create_fake_attitude_message(yaw_rad: float, pitch_rad: float, roll_rad: float):
    """Parser'ın kullandığı alanlara sahip basit stub mesaj."""
    return SimpleNamespace(
        get_type=lambda: "ATTITUDE",
        yaw=yaw_rad,
        pitch=pitch_rad,
        roll=roll_rad,
    )


# ----------------------------------------------------------------------
def test_attitude_parsing(qtbot):
    """
    ATTITUDE mesajı pozitif/yayılmış derecelere çevrilmeli
    ve telemetry sinyali tam 1 kez yayılmalı.
    """
    fake_msg = create_fake_attitude_message(0.5, 0.2, 0.1)  # rad
    parser   = MessageParser()

    spy = QSignalSpy(parser.telemetry)      # <-- QtTest versiyonu

    parser.parse(fake_msg)

    assert len(spy) == 1, "telemetry sinyali tam 1 kez emit edilmeli"

    data = spy[0][0]   # yayımlanan sözlük
    deg  = 57.2958

    assert data["yaw"]   == pytest.approx((0.5 * deg) % 360)
    assert data["pitch"] == pytest.approx(abs(0.2 * deg))
    assert data["roll"]  == pytest.approx(abs(0.1 * deg))
