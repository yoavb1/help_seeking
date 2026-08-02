import json
import os
import random
import sys

# 1. Setup Django Environment
try:
    import django

    # Replace 'myproject.settings' with your actual settings path (e.g., 'config.settings')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HelpSeeking.settings")

    # Add project root directory to Python path if needed
    sys.path.append(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    django.setup()

    from django.conf import settings

    PRACTICE_COUNT = getattr(settings, "EXPERIMENT_PRACTICE_TRIALS", 3)
    LIVE_COUNT = getattr(settings, "EXPERIMENT_LIVE_TRIALS", 10)
    print(
        f"Loaded settings from Django: PRACTICE={PRACTICE_COUNT}, LIVE={LIVE_COUNT}"
    )

except Exception as e:
    print(f"Could not load Django settings ({e}). Using default numbers.")
    PRACTICE_COUNT = 5
    LIVE_COUNT = 80

ROUTES = ["Air", "Ocean", "Rail"]
TARGET_UNITS = 15


def generate_easy_rules(correct_route):
    """
    EASY RULES: All values are explicitly stated integers.
    """
    for _ in range(1000):
        air = random.randint(2, 8)
        ocean = random.randint(2, 7)
        rail = TARGET_UNITS - (air + ocean)

        if rail > 1 and len({air, ocean, rail}) == 3:
            vals = {"Air": air, "Ocean": ocean, "Rail": rail}
            if max(vals, key=vals.get) == correct_route:
                return {
                    "rules": {
                        "air_rule": f"Must equal exactly {air} containers.",
                        "sea_rule": f"Must equal exactly {ocean} containers.",
                        "rail_rule": f"Must equal exactly {rail} containers."
                    },
                    "evaluated_values": {"air": air, "ocean": ocean, "rail": rail}
                }

    # Fallback
    return {
        "rules": {
            "air_rule": "Must equal exactly 8 containers.",
            "sea_rule": "Must equal exactly 4 containers.",
            "rail_rule": "Must equal exactly 3 containers."
        },
        "evaluated_values": {"air": 8, "ocean": 4, "rail": 3}
    }


def generate_moderate_rules(correct_route):
    """
    MODERATE RULES (Slightly Harder):
    - 1 Explicit Integer
    - 1 Relational rule with a difference/offset or exact integer multiplier
    - 1 Remaining Cargo rule to sum up to TARGET_UNITS
    """
    for _ in range(1000):
        air = random.randint(2, 8)
        ocean = random.randint(2, 7)
        rail = TARGET_UNITS - (air + ocean)

        if rail > 1 and len({air, ocean, rail}) == 3:
            vals = {"Air": air, "Ocean": ocean, "Rail": rail}
            if max(vals, key=vals.get) == correct_route:

                rem_mode = random.choice(["Air", "Ocean", "Rail"])
                other_modes = [m for m in ROUTES if m != rem_mode]
                explicit_mode = random.choice(other_modes)
                relational_mode = [m for m in other_modes if m != explicit_mode][0]

                mode_values = {"Air": air, "Ocean": ocean, "Rail": rail}

                explicit_val = mode_values[explicit_mode]
                explicit_text = f"Must equal exactly {explicit_val} containers."

                rel_val = mode_values[relational_mode]

                # Force cleaner, moderately challenging relationships
                if rel_val % explicit_val == 0 and rel_val > explicit_val:
                    mult = rel_val // explicit_val
                    rel_text = f"Must equal {mult} times the {explicit_mode} capacity."
                else:
                    diff = rel_val - explicit_val
                    if diff > 0:
                        rel_text = f"Must carry {diff} container{'s' if diff > 1 else ''} more than {explicit_mode}."
                    else:
                        rel_text = f"Must carry {abs(diff)} container{'s' if abs(diff) > 1 else ''} less than {explicit_mode}."

                rem_text = f"Must equal remaining cargo needed to reach {TARGET_UNITS}."

                rules_map = {
                    rem_mode: rem_text,
                    explicit_mode: explicit_text,
                    relational_mode: rel_text
                }

                return {
                    "rules": {
                        "air_rule": rules_map["Air"],
                        "sea_rule": rules_map["Ocean"],
                        "rail_rule": rules_map["Rail"]
                    },
                    "evaluated_values": {"air": air, "ocean": ocean, "rail": rail}
                }

    # Fallback
    return {
        "rules": {
            "air_rule": "Must equal remaining cargo needed to reach 15.",
            "sea_rule": "Must equal exactly 4 containers.",
            "rail_rule": "Must carry 1 container less than Ocean."
        },
        "evaluated_values": {"air": 8, "ocean": 4, "rail": 3}
    }


def generate_hard_rules(correct_route):
    """
    HARD RULES: Pure system of relational equations with STRICT INTEGER VALUES ONLY.
    - 1 Remaining cargo rule (summing to 15)
    - 2 Pure relational rules (using integer multipliers or integer offsets, NO decimals)
    """
    for _ in range(1000):
        air = random.randint(2, 8)
        ocean = random.randint(2, 7)
        rail = TARGET_UNITS - (air + ocean)

        if rail > 1 and len({air, ocean, rail}) == 3:
            vals = {"Air": air, "Ocean": ocean, "Rail": rail}
            if max(vals, key=vals.get) == correct_route:

                rem_mode = random.choice(["Air", "Ocean", "Rail"])
                rel_modes = [m for m in ROUTES if m != rem_mode]

                m1, m2 = rel_modes[0], rel_modes[1]
                mode_values = {"Air": air, "Ocean": ocean, "Rail": rail}

                v1, v2 = mode_values[m1], mode_values[m2]

                # Rule 1: Integer Multiplier if divisible, otherwise clean integer offset
                if v1 % v2 == 0 and v1 > v2:
                    mult1 = v1 // v2
                    rule1_text = f"Must equal {mult1} times the {m2} capacity."
                else:
                    diff1 = v1 - v2
                    if diff1 > 0:
                        rule1_text = f"Must carry {diff1} container{'s' if diff1 > 1 else ''} more than {m2}."
                    else:
                        rule1_text = f"Must carry {abs(diff1)} container{'s' if abs(diff1) > 1 else ''} less than {m2}."

                # Rule 2: Integer Offset connecting m2 to m1
                diff2 = v2 - v1
                if diff2 > 0:
                    rule2_text = f"Must carry {diff2} container{'s' if diff2 > 1 else ''} more than {m1}."
                else:
                    rule2_text = f"Must carry {abs(diff2)} container{'s' if abs(diff2) > 1 else ''} less than {m1}."

                rem_text = f"Must equal remaining capacity after other routes are filled."

                rules_map = {
                    rem_mode: rem_text,
                    m1: rule1_text,
                    m2: rule2_text
                }

                return {
                    "rules": {
                        "air_rule": rules_map["Air"],
                        "sea_rule": rules_map["Ocean"],
                        "rail_rule": rules_map["Rail"]
                    },
                    "evaluated_values": {"air": air, "ocean": ocean, "rail": rail}
                }

    # Fallback
    return {
        "rules": {
            "air_rule": "Must equal remaining capacity after other routes are filled.",
            "sea_rule": "Must carry 1 container more than Rail.",
            "rail_rule": "Must carry 5 containers less than Ocean."
        },
        "evaluated_values": {"air": 8, "ocean": 4, "rail": 3}
    }


def create_incorrect_advisor_values(evaluated_values):
    """
    Generates an incorrect cargo breakdown recommendation while preserving total = 15.
    """
    air = evaluated_values["air"]
    ocean = evaluated_values["ocean"]
    rail = evaluated_values["rail"]

    all_vals = [air, ocean, rail]
    for _ in range(20):
        shuffled = all_vals.copy()
        random.shuffle(shuffled)
        if shuffled != all_vals:
            return {"air": shuffled[0], "ocean": shuffled[1], "rail": shuffled[2]}

    return {"air": air + 1, "ocean": ocean - 1, "rail": rail}


def generate_dataset(total_count, output_filename, diff_distribution, target_accuracy=0.85):
    """
    Generates dataset enforcing target_accuracy (85%) STRATIFIED per difficulty level.
    The advisor recommends cargo quantities (`evaluated_values`).
    """
    counts = {}
    for diff, ratio in diff_distribution.items():
        counts[diff] = round(total_count * ratio)

    # Adjust rounding differences to match exact total_count
    diff_sum = sum(counts.values())
    if diff_sum < total_count:
        counts["M"] += total_count - diff_sum
    elif diff_sum > total_count:
        counts["M"] -= diff_sum - total_count

    trials_pool = []
    stats = {}

    for diff, count in counts.items():
        num_correct = round(count * target_accuracy)
        num_wrong = count - num_correct

        advice_pool = [True] * num_correct + [False] * num_wrong
        random.shuffle(advice_pool)

        stats[diff] = {"total": count, "correct": num_correct, "wrong": num_wrong}

        for is_correct in advice_pool:
            trials_pool.append((diff, is_correct))

    random.shuffle(trials_pool)

    questions = []

    for i, (difficulty, is_advisor_correct) in enumerate(trials_pool):
        correct_route = random.choice(ROUTES)

        if difficulty == "E":
            generated = generate_easy_rules(correct_route)
        elif difficulty == "M":
            generated = generate_moderate_rules(correct_route)
        else:
            generated = generate_hard_rules(correct_route)

        true_values = generated["evaluated_values"]

        if is_advisor_correct:
            advisor_rec_values = true_values.copy()
        else:
            advisor_rec_values = create_incorrect_advisor_values(true_values)

        q = {
            "id": i + 1,
            "title": f"Logistics Routing Log #{i + 1}",
            "difficulty": difficulty,
            "correct_answer": correct_route,
            "constraints": {
                "target_units": TARGET_UNITS,
                "rules": generated["rules"],
                "evaluated_values": true_values
            },
            "advisor_recommendation": {
                "cargo_values": advisor_rec_values
            }
        }
        questions.append(q)

    # Save output file directly in experiment/data/
    data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, output_filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2)

    print(f"\n================ Saved: {filepath} ({total_count} Questions) ================")
    for diff in ["E", "M", "H"]:
        if diff in stats and stats[diff]['total'] > 0:
            d_stat = stats[diff]
            acc_pct = (d_stat['correct'] / d_stat['total'] * 100)
            print(
                f" Difficulty [{diff}]: {d_stat['total']} items | Advisor Correct: {d_stat['correct']}/{d_stat['total']} ({acc_pct:.1f}%)")
    print("==========================================================================")


if __name__ == "__main__":
    # Practice Set: 5 questions
    generate_dataset(PRACTICE_COUNT, "questions_practice.json", {"E": 0, "M": 1, "H": 0}, target_accuracy=0.85)

    # Live Set: 80 questions
    generate_dataset(LIVE_COUNT, "questions_live.json", {"E": 0, "M": 0.5, "H": 0.5}, target_accuracy=0.85)