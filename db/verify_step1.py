from pathlib import Path

root = Path(__file__).resolve().parent
learning = (root / "routes" / "learning.py").read_text(encoding="utf-8")
gamification = (root / "routes" / "gamification.py").read_text(encoding="utf-8")

checks = {
    "checkpoint +10": "CHECKPOINT_XP = 10" in learning,
    "quiz +40": "QUIZ_XP = 40" in learning,
    "lab +50": "LAB_XP = 50" in learning and "LAB_XP = 50" in gamification,
    "module bonus removed": "MODULE_COMPLETION_XP = 50" not in learning,
    "manual XP disabled": "manual_xp_disabled" in gamification,
    "checkpoint one-time guard": "was_completed = bool(" in learning,
    "quiz pass 75": "passed = score >= 75" in gamification,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("GAGAL: " + ", ".join(failed))

print("OK — aturan XP Step 1 terpasang.")
