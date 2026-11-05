from __future__ import annotations

import unittest

from sitcp_host.core.conversions import (
    adc_code_to_millivolts,
    xadc_temperature_celsius,
)


class ConversionTests(unittest.TestCase):
    def test_xadc_temperature_conversion(self) -> None:
        self.assertAlmostEqual(xadc_temperature_celsius(0x0AB5), 64.10, places=2)
        self.assertAlmostEqual(xadc_temperature_celsius(0x0), -273.15, places=2)
        self.assertAlmostEqual(xadc_temperature_celsius(0x0FFF), 230.70, places=2)

    def test_adc_code_to_millivolts(self) -> None:
        self.assertEqual(adc_code_to_millivolts(0), 0.0)
        self.assertAlmostEqual(adc_code_to_millivolts(8192), 900.0, places=6)
        self.assertAlmostEqual(adc_code_to_millivolts(-8192), -900.0, places=6)


if __name__ == "__main__":
    unittest.main()
