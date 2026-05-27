"""Validate that every ending's trigger conditions are achievable.

Walks all possible choice paths through the game, tracking variable state,
and checks each ending against the resulting terminal states.

Usage:
  python validate_endings.py <project_root>
  python validate_endings.py c:/SelfCreated/MyProject/libai

Output:
  - Prints a report of reachable/unreachable endings
  - For unreachable endings, shows the max possible values and which
    conditions can't be met
  - Exits 0 if all endings reachable, 1 if any unreachable

The script reads:
  - shared/state/branch_map.json   (choice points + option effects)
  - shared/state/scene_graph.json  (scene flow + conditional transitions)
  - shared/state/ending_matrix.json (ending trigger conditions)
  - shared/state/variables.json    (initial values for all variables)
"""

import json
import sys
import os
from collections import defaultdict
from itertools import product


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_condition(cond_str):
    """Parse a condition string like 'ball_attended==1' into (var, op, value)."""
    for op in (">=", "<=", "!=", "==", ">", "<"):
        if op in cond_str:
            var, _, val = cond_str.partition(op)
            return var.strip(), op, int(val.strip())
    return None


def eval_condition(variables, var, op, value):
    """Evaluate a single condition against current variable state."""
    current = variables.get(var, 0)
    if op == "==":
        return current == value
    elif op == ">=":
        return current >= value
    elif op == "<=":
        return current <= value
    elif op == ">":
        return current > value
    elif op == "<":
        return current < value
    elif op == "!=":
        return current != value
    return False


def build_initial_state(variables_path):
    """Build initial variable state from variables.json defaults."""
    state = {}
    var_data = load_json(variables_path)
    for v in var_data.get("attitude_variables", []):
        state[v["id"]] = v.get("default", 0)
    for v in var_data.get("event_flags", []):
        state[v["id"]] = v.get("default", 0)
    return state


def walk_paths(branches, initial_state, scene_graph):
    """Walk all possible choice paths and return list of terminal (state, path_info).

    Returns: [(variables_dict, [(scene, option_label, adds, sets), ...]), ...]
    """
    # Index choices by scene
    scene_choices = defaultdict(list)
    for b in branches:
        scene_choices[b["scene"]].append(b)

    # Build scene transition map from scene_graph
    # Maps scene_id -> [(next_scene_id, condition_string or None), ...]
    transitions = defaultdict(list)
    for conn in scene_graph.get("connections", []):
        transitions[conn["from"]].append((conn["to"], conn.get("condition")))

    # Find entry point — the scene marked is_entry, or the first non-ending scene
    scenes = {s["id"]: s for s in scene_graph.get("scenes", [])}
    entry_scene = None
    for s in scene_graph.get("scenes", []):
        if s.get("is_entry"):
            entry_scene = s["id"]
            break
    if not entry_scene and scene_graph.get("scenes"):
        for s in scene_graph["scenes"]:
            if not s.get("is_ending") and s.get("act", 999) > 0:
                entry_scene = s["id"]
                break

    terminal_states = []

    def walk(scene_id, variables, path):
        """Recursively walk scenes, branching at choices."""
        # If this scene has choices, branch here
        if scene_id in scene_choices:
            for branch in scene_choices[scene_id]:
                for option in branch["options"]:
                    new_vars = dict(variables)
                    # Apply sets first (absolute assignments)
                    for k, v in option.get("sets", {}).items():
                        new_vars[k] = v
                    # Apply adds (increments)
                    for k, v in option.get("adds", {}).items():
                        new_vars[k] = new_vars.get(k, 0) + v

                    new_path = path + [{
                        "scene": scene_id,
                        "choice_id": branch["id"],
                        "option": option["label"],
                        "sets": option.get("sets", {}),
                        "adds": option.get("adds", {}),
                    }]

                    next_scene = option.get("next_scene", scene_id)

                    if next_scene == scene_id:
                        # Choice stays in same scene (e.g., final choice in act5_climax)
                        # This is terminal — stop here
                        terminal_states.append((new_vars, new_path))
                    else:
                        walk(next_scene, new_vars, new_path)
        else:
            # No choices in this scene — follow unconditional transitions
            outgoing = transitions.get(scene_id, [])
            if not outgoing:
                # Terminal — no more scenes
                terminal_states.append((variables, path))
                return

            for next_scene, condition in outgoing:
                if condition:
                    parsed = parse_condition(condition)
                    if parsed and not eval_condition(variables, *parsed):
                        continue  # Skip — condition not met
                walk(next_scene, variables, path)

    if entry_scene:
        walk(entry_scene, dict(initial_state), [])
    else:
        print("ERROR: Could not find entry scene in scene_graph.json")
        sys.exit(2)

    return terminal_states


def check_ending(ending, terminal_states):
    """Check if an ending is reachable from any terminal state.

    Returns: (reachable: bool, best_state: dict, best_path: list,
              failing_conditions: list, summary: str)
    """
    trigger = ending.get("trigger", {})
    trigger_type = trigger.get("type", "fallback")

    if trigger_type == "fallback":
        return True, {}, [], [], "Fallback ending — always reachable."

    conditions = trigger.get("conditions", [])
    required_count = trigger.get("required_count", len(conditions))

    best_match_count = -1
    best_state = None
    best_path = None
    best_match_detail = None

    for variables, path in terminal_states:
        matched = 0
        match_detail = []
        for cond in conditions:
            var_name = cond["variable"]
            op = cond["operator"]
            value = cond["value"]
            current = variables.get(var_name, 0)
            ok = eval_condition(variables, var_name, op, value)
            if ok:
                matched += 1
            match_detail.append({
                "condition": f"{var_name}{op}{value}",
                "actual": current,
                "satisfied": ok,
            })

        if matched > best_match_count:
            best_match_count = matched
            best_state = dict(variables)
            best_path = path
            best_match_detail = match_detail

        if matched >= required_count:
            return True, variables, path, [], "All conditions met."

    # Not reachable — build failure report
    failing = []
    for detail in (best_match_detail or []):
        if not detail["satisfied"]:
            failing.append({
                "condition": detail["condition"],
                "required": detail["condition"],
                "max_achievable": detail["actual"],
                "gap": "Cannot be satisfied with any choice path",
            })

    summary = (
        f"Best match: {best_match_count}/{required_count} conditions met. "
        f"Need {required_count - best_match_count} more."
    )
    return False, best_state, best_path, failing, summary


def summarize_by_ending(terminal_states, endings):
    """Compute max achievable value per variable for each ending's variables."""
    # Collect all variables referenced by any ending
    all_vars = set()
    for ending in endings:
        for cond in ending.get("trigger", {}).get("conditions", []):
            all_vars.add(cond["variable"])

    # Per-ending, compute max values across terminal states
    result = {}
    for ending in endings:
        eid = ending["id"]
        triggering_vars = set()
        for cond in ending.get("trigger", {}).get("conditions", []):
            triggering_vars.add(cond["variable"])

        max_vals = {}
        for variables, _ in terminal_states:
            for var in triggering_vars:
                if var not in max_vals or variables.get(var, 0) > max_vals[var]:
                    max_vals[var] = variables.get(var, 0)

        result[eid] = max_vals

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_endings.py <project_root>")
        print("Example: python validate_endings.py c:/SelfCreated/MyProject/libai")
        sys.exit(2)

    project_root = sys.argv[1]
    state_dir = os.path.join(project_root, "shared", "state")

    # Load planning data
    branch_map = load_json(os.path.join(state_dir, "branch_map.json"))
    scene_graph = load_json(os.path.join(state_dir, "scene_graph.json"))
    ending_matrix = load_json(os.path.join(state_dir, "ending_matrix.json"))
    initial_state = build_initial_state(
        os.path.join(state_dir, "variables.json")
    )

    print("=" * 60)
    print("Ending Reachability Validator")
    print("=" * 60)

    # Walk all paths
    terminal_states = walk_paths(
        branch_map.get("branches", []),
        initial_state,
        scene_graph,
    )

    print(f"\nTotal choice paths explored: {len(terminal_states)}")

    # Compute per-variable maxima across all terminal states
    all_vars_used = set()
    for v in initial_state:
        all_vars_used.add(v)
    global_max = {}
    for variables, _ in terminal_states:
        for var in all_vars_used:
            if var not in global_max or variables.get(var, 0) > global_max[var]:
                global_max[var] = variables.get(var, 0)

    print("\nMaximum achievable values (across all paths):")
    for var in sorted(global_max):
        print(f"  {var}: {global_max[var]} (initial: {initial_state.get(var, '?')})")

    # Per-ending max values
    per_ending_max = summarize_by_ending(terminal_states, ending_matrix.get("endings", []))

    # Check each ending
    print("\n" + "=" * 60)
    print("Ending Checks (in priority order)")
    print("=" * 60)

    all_reachable = True
    for ending in ending_matrix.get("endings", []):
        eid = ending["id"]
        category = ending.get("category", "?")
        priority = ending.get("priority", "?")

        reachable, best_state, best_path, failing, summary = check_ending(
            ending, terminal_states
        )

        status = "REACHABLE" if reachable else "UNREACHABLE"
        marker = "PASS" if reachable else "FAIL"

        print(f"\n[{priority}] {marker} {eid} ({category}) — {status}")
        if not reachable:
            all_reachable = False
            print(f"  {summary}")
            print(f"  Max values for this ending's variables:")
            for var, val in per_ending_max.get(eid, {}).items():
                print(f"    {var}: {val}")
            if failing:
                print(f"  Failing conditions:")
                for f in failing:
                    print(
                        f"    {f['condition']} — max achievable: {f['max_achievable']}"
                    )

    print("\n" + "=" * 60)
    if all_reachable:
        print("ALL ENDINGS REACHABLE — game is balanced.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("SOME ENDINGS UNREACHABLE — adjust choice effects or ending thresholds.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
