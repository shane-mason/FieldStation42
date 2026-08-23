import gpiod
from gpiod.line import Direction, Value, Bias

CHIP = "/dev/gpiochip0"

COLS = [70, 228, 72]
ROWS = [226, 232, 71, 69]

print("Testing columns as INPUT + PULL_UP")

for line in COLS:
    try:
        with gpiod.request_lines(
            CHIP,
            consumer="keypad-test",
            config={
                line: gpiod.LineSettings(
                    direction=Direction.INPUT,
                    bias=Bias.PULL_UP,
                )
            },
        ):
            print(f"  line {line}: OK")
    except OSError as e:
        print(f"  line {line}: FAIL -> {e}")

print("\nTesting rows as OUTPUT HIGH")

for line in ROWS:
    try:
        with gpiod.request_lines(
            CHIP,
            consumer="keypad-test",
            config={
                line: gpiod.LineSettings(
                    direction=Direction.OUTPUT,
                    output_value=Value.ACTIVE,
                )
            },
        ):
            print(f"  line {line}: OK")
    except OSError as e:
        print(f"  line {line}: FAIL -> {e}")
