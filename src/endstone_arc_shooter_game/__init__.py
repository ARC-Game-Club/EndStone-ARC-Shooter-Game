try:
    from endstone_arc_shooter_game.arc_shooter_game_plugin import ARCShooterGamePlugin
except ModuleNotFoundError as e:
    if "endstone" not in str(e):
        raise
    ARCShooterGamePlugin = None  # 无 Endstone 环境时仍可单测 config / session

__all__ = ["ARCShooterGamePlugin"]
