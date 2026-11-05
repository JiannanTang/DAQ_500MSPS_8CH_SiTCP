"""Numeric conversions for FPGA telemetry."""


XADC_TEMPERATURE_FULL_SCALE_C = 503.975
XADC_TEMPERATURE_ZERO_C = 273.15
XADC_TEMPERATURE_CODE_MAX = 4095
ADC_VOLTAGE_FULL_SCALE_MV = 1800.0
ADC_VOLTAGE_CODE_SPAN = 16384.0


def xadc_temperature_celsius(raw_code: int) -> float:
    """Convert a 12-bit Xilinx XADC temperature code to degrees Celsius."""

    code = raw_code & XADC_TEMPERATURE_CODE_MAX
    return (
        code * XADC_TEMPERATURE_FULL_SCALE_C / 4096
        - XADC_TEMPERATURE_ZERO_C
    )


def adc_code_to_millivolts(signed_code: float) -> float:
    """Convert a centered ADC code to millivolts."""

    return signed_code * ADC_VOLTAGE_FULL_SCALE_MV / ADC_VOLTAGE_CODE_SPAN

