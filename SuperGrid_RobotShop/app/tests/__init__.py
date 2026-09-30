"""Unit tests for the flwr-free modules (protocol, pricing, catalog, llm).

Run from the repo root with a plain python3 (no flwr needed), either way:
    python3 -m unittest discover -s SuperGrid_RobotShop/app/tests -t SuperGrid_RobotShop/app -v
    python3 -m unittest discover SuperGrid_RobotShop/app/tests
Each test module puts the app folder on sys.path itself, so both forms import robot_shop.
"""
