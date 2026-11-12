"""Adversarial stress-test suite for end-to-end simulation dynamics, edge cases, and robustness.

Tests cover:
1. Full convoy lifecycle (start, traverse, damage, termination).
2. Convoy health exhaustion (mid-route destruction, HP <= 0, post-destruction stability).
3. Convoy destruction on the edge entering OUT (destroyed takes precedence over escaped).
4. Disconnected graph handling (no route to exit, graceful termination without infinite loop).
5. Blocked graph mid-route.
6. Complex maze topology with multiple cycles and decision points (anti-backtracking & trajectory).
7. Callejón sin salida (dead-end last-resort backtrack).
8. Dynamic defense deployment between steps.
9. Dynamic alpha risk parameter modulation.
10. Multi-machine front-to-back sequential damage allocation.
11. Trivial and boundary graph topologies.
"""

import pytest
from app.core.maze_graph import MazeGraph
from app.domain.enemy import EnemyMachine, EnemyType
from app.domain.soldier import DefenseUnit, SoldierType
from app.services.scenario_service import ScenarioService
from app.services.hazard_service import HazardService
from app.services.simulation_service import SimulationService


def build_scenario_service_with_graph(gm: MazeGraph, enemies=None) -> ScenarioService:
    """Helper to build an isolated ScenarioService with a custom MazeGraph."""
    scenario_srv = ScenarioService()
    scenario_srv.maze_graph = gm
    if enemies is not None:
        scenario_srv.simulation_state.enemies = enemies
    return scenario_srv


class TestAdversarialSimulationDynamics:

    def test_full_convoy_lifecycle_escape(self):
        """Lifecycle: IN -> M1 -> M2 -> OUT. Convoy escapes with partial damage."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("M1", 10.0, 0.0)
        gm.add_maze_node("M2", 20.0, 0.0)
        gm.add_maze_node("OUT", 30.0, 0.0, is_exit=True)

        gm.add_corridor("IN", "M1", length=10.0, speed=2.0)   # t = 5.0s
        gm.add_corridor("M1", "M2", length=10.0, speed=2.0)   # t = 5.0s
        gm.add_corridor("M2", "OUT", length=10.0, speed=2.0)  # t = 5.0s

        scenario_srv = build_scenario_service_with_graph(gm)
        hazard_srv = HazardService(scenario_srv)
        # Defense covering only M1-M2 with 1 Infantry (10 dmg/s)
        inf = DefenseUnit(SoldierType.INFANTRY, x=15.0, y=0.0, effective_range=8.0)
        hazard_srv.set_custom_defenses([inf])

        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)
        sim_srv.reset(alpha_danger=1.0)

        initial_hp = sim_srv.get_total_hp()
        assert initial_hp == 350.0  # Tank(200) + Truck(100) + Robot(50)

        # Run full simulation
        run_res = sim_srv.run(max_steps=10)

        assert run_res["is_finished"] is True
        assert run_res["escaped"] is True
        assert run_res["destroyed"] is False
        assert run_res["current_node"] == "OUT"
        assert run_res["path_taken"] == ["IN", "M1", "M2", "OUT"]
        assert run_res["total_steps"] == 3
        assert run_res["total_time_elapsed"] == pytest.approx(15.0)
        assert run_res["total_damage_taken"] > 0.0
        assert sim_srv.get_total_hp() == pytest.approx(initial_hp - run_res["total_damage_taken"], abs=0.1)

    def test_convoy_health_exhaustion_mid_route(self):
        """Convoy health exhaustion: massive hazard destroys convoy before reaching exit."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("M1", 10.0, 0.0)
        gm.add_maze_node("M2", 20.0, 0.0)
        gm.add_maze_node("OUT", 30.0, 0.0, is_exit=True)

        gm.add_corridor("IN", "M1", length=10.0, speed=2.0)
        gm.add_corridor("M1", "M2", length=10.0, speed=1.0)   # t = 10.0s
        gm.add_corridor("M2", "OUT", length=10.0, speed=2.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        hazard_srv = HazardService(scenario_srv)

        # Deadly sniper battery covering M1-M2 causing > 500 damage
        snipers = [
            DefenseUnit(SoldierType.SNIPER, x=15.0, y=0.0, effective_range=4.0, unit_id=f"s_{i}")
            for i in range(5)  # 5 * 25 = 125 dmg/s * 10s = 1250 damage!
        ]
        hazard_srv.set_custom_defenses(snipers)

        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)
        sim_srv.reset(alpha_danger=0.0)  # alpha=0 so it doesn't try to avoid due to high weight

        # Step 1: IN -> M1 (safe)
        step1 = sim_srv.step()
        assert step1["current_node"] == "M1"
        assert step1["is_finished"] is False

        # Step 2: M1 -> M2 (lethal)
        step2 = sim_srv.step()
        assert step2["current_node"] == "M2"
        assert step2["is_finished"] is True
        assert step2["destroyed"] is True
        assert step2["escaped"] is False
        assert step2["hp"] == 0.0
        assert sim_srv.scenario_service.simulation_state.is_game_over is True
        assert sim_srv.scenario_service.simulation_state.game_result == "Convoy destruido"

        # Step 3: further step when already finished should not mutate or crash
        step3 = sim_srv.step()
        assert step3["decision"]["type"] == "ALREADY_FINISHED"
        assert step3["is_finished"] is True
        assert step3["destroyed"] is True

    def test_convoy_destruction_on_final_edge_entering_out(self):
        """If convoy takes lethal damage on the final corridor entering OUT,
        it must be marked DESTROYED, NOT ESCAPED!
        """
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("OUT", 10.0, 0.0, is_exit=True)
        gm.add_corridor("IN", "OUT", length=10.0, speed=1.0)  # t = 10s

        # Fragile convoy: 1 Robot with 50 HP
        fragile_convoy = [EnemyMachine(EnemyType.ROBOT, custom_hp=50.0)]
        scenario_srv = build_scenario_service_with_graph(gm, enemies=fragile_convoy)
        hazard_srv = HazardService(scenario_srv)

        # Sniper causing 25 dmg/s * 10s = 250 damage
        snip = DefenseUnit(SoldierType.SNIPER, x=5.0, y=0.0, effective_range=10.0)
        hazard_srv.set_custom_defenses([snip])

        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)
        sim_srv.reset()

        step1 = sim_srv.step()
        assert step1["current_node"] == "OUT"
        assert step1["is_finished"] is True
        assert step1["destroyed"] is True, "Must be destroyed even though it entered OUT!"
        assert step1["escaped"] is False, "Must NOT be marked escaped if destroyed!"
        assert step1["hp"] == 0.0

    def test_disconnected_graph_no_route(self):
        """Graph where target OUT is completely unreachable from IN."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("ISLAND_1", 10.0, 0.0)
        gm.add_corridor("IN", "ISLAND_1", length=10.0, speed=1.0)

        gm.add_maze_node("ISLAND_2", 100.0, 100.0)
        gm.add_maze_node("OUT", 110.0, 100.0, is_exit=True)
        gm.add_corridor("ISLAND_2", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        step_res = sim_srv.step()
        assert step_res["decision"]["type"] == "NO_ROUTE"
        assert step_res["is_finished"] is True
        assert step_res["escaped"] is False
        assert step_res["destroyed"] is False
        assert sim_srv.scenario_service.simulation_state.game_result == "Convoy sin ruta"

        # Run test: must terminate in 1 step without infinite loop
        sim_srv.reset()
        run_res = sim_srv.run(max_steps=50)
        assert run_res["total_steps"] == 1
        assert run_res["is_finished"] is True
        assert run_res["escaped"] is False

    def test_blocked_graph_mid_route_no_route(self):
        """Convoy moves from IN to M1, and then all forward paths from M1 to OUT are severed.
        Since no path to OUT exists anywhere, convoy terminates with NO_ROUTE without infinite loop.
        """
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("M1", 10.0, 0.0)
        gm.add_maze_node("OUT", 20.0, 0.0, is_exit=True)

        gm.add_corridor("IN", "M1", length=10.0, speed=1.0)
        corr_m1_out = gm.add_corridor("M1", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: IN -> M1
        step1 = sim_srv.step()
        assert step1["current_node"] == "M1"
        assert step1["is_finished"] is False

        # Mid-route catastrophe: corridor M1-OUT is blocked / destroyed!
        del gm.adj["M1"]["OUT"]
        del gm.adj["OUT"]["M1"]
        key = (min("M1", "OUT"), max("M1", "OUT"))
        if key in gm.maze_edges:
            del gm.maze_edges[key]

        # Step 2: at M1, target OUT is completely unreachable.
        # Dijkstra returns None, so decision is NO_ROUTE and simulation terminates cleanly.
        step2 = sim_srv.step()
        assert step2["current_node"] == "M1"
        assert step2["decision"]["type"] == "NO_ROUTE"
        assert step2["is_finished"] is True
        assert step2["escaped"] is False
        assert step2["destroyed"] is False
        assert sim_srv.scenario_service.simulation_state.game_result == "Convoy sin ruta"

    def test_blocked_corridor_recovers_via_dead_end_backtrack_and_alternate_branch(self):
        """Convoy moves IN -> M1. Forward corridor M1-OUT collapses.
        However, IN has an alternate branch IN -> ALT -> OUT.
        At M1, the ONLY way to reach OUT is to backtrack through IN!
        Anti-backtracking detects dead-end at M1, permits backtrack to IN as last resort,
        and then navigates IN -> ALT -> OUT to escape!
        """
        gm = MazeGraph()
        gm.add_maze_node("IN", 0.0, 0.0, is_entry=True)
        gm.add_maze_node("M1", 10.0, 0.0)
        gm.add_maze_node("ALT", 0.0, 10.0)
        gm.add_maze_node("OUT", 20.0, 0.0, is_exit=True)

        # Primary route: IN -> M1 -> OUT (cost 5 + 5 = 10)
        gm.add_corridor("IN", "M1", length=5.0, speed=1.0)
        gm.add_corridor("M1", "OUT", length=5.0, speed=1.0)
        # Alternate branch: IN -> ALT -> OUT (cost 8 + 8 = 16)
        gm.add_corridor("IN", "ALT", length=8.0, speed=1.0)
        gm.add_corridor("ALT", "OUT", length=8.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: IN -> M1
        step1 = sim_srv.step()
        assert step1["current_node"] == "M1"
        assert step1["previous_node"] == "IN"

        # Corridor M1-OUT collapses!
        del gm.adj["M1"]["OUT"]
        del gm.adj["OUT"]["M1"]
        key = (min("M1", "OUT"), max("M1", "OUT"))
        if key in gm.maze_edges:
            del gm.maze_edges[key]

        # Step 2: At M1, Dijkstra unconstrained route is M1 -> IN -> ALT -> OUT.
        # next_candidate == 'IN', which equals previous_node!
        # M1 has no other neighbors besides IN, so this is a dead-end cul-de-sac.
        # Backtracking to IN is permitted as last resort!
        step2 = sim_srv.step()
        assert step2["current_node"] == "IN"
        assert step2["previous_node"] == "M1"
        assert step2["decision"]["type"] == "FORCED_DEAD_END_BACKTRACK"
        assert step2["is_finished"] is False

        # Step 3: From IN, previous_node is M1. Optimal path is IN -> ALT -> OUT.
        # next_candidate is ALT != M1, so it takes ALT!
        step3 = sim_srv.step()
        assert step3["current_node"] == "ALT"
        assert step3["previous_node"] == "IN"

        # Step 4: From ALT to OUT!
        step4 = sim_srv.step()
        assert step4["current_node"] == "OUT"
        assert step4["is_finished"] is True
        assert step4["escaped"] is True

    def test_complex_maze_topology_with_multiple_cycles(self):
        """Maze with multiple alternative cycles and decision points:
        IN --(5)--> M1 --(5)--> M2 --(5)--> OUT
         |           |           |
        (2)         (10)        (2)
         v           v           v
        B1 --(3)--> B2 --(3)--> B3
        """
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("M2", 20, 0)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        gm.add_maze_node("B1", 0, 10)
        gm.add_maze_node("B2", 10, 10)
        gm.add_maze_node("B3", 20, 10)

        # Corridors
        gm.add_corridor("IN", "M1", length=5.0, speed=1.0)
        gm.add_corridor("M1", "M2", length=5.0, speed=1.0)
        gm.add_corridor("M2", "OUT", length=5.0, speed=1.0)

        gm.add_corridor("IN", "B1", length=2.0, speed=1.0)
        gm.add_corridor("B1", "B2", length=3.0, speed=1.0)
        gm.add_corridor("B2", "B3", length=3.0, speed=1.0)
        gm.add_corridor("B3", "M2", length=2.0, speed=1.0)
        gm.add_corridor("M1", "B2", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        run_res = sim_srv.run(max_steps=20)
        assert run_res["is_finished"] is True
        assert run_res["escaped"] is True
        assert run_res["current_node"] == "OUT"
        assert len(run_res["path_taken"]) >= 4
        assert run_res["path_taken"][0] == "IN"
        assert run_res["path_taken"][-1] == "OUT"

    def test_callejon_sin_salida_dead_end_resolution(self):
        """Convoy enters a cul-de-sac (dead-end leaf), backtracks safely, and reaches OUT."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("JUNCTION", 10, 0)
        gm.add_maze_node("DEAD_END", 10, 10)
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        # JUNCTION -> DEAD_END is initially made cheap, but dead end has no exit
        gm.add_corridor("IN", "JUNCTION", length=5.0, speed=1.0)
        gm.add_corridor("JUNCTION", "DEAD_END", length=2.0, speed=1.0)
        gm.add_corridor("JUNCTION", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: IN -> JUNCTION
        step1 = sim_srv.step()
        assert step1["current_node"] == "JUNCTION"

        # Manually move convoy into DEAD_END to test backtrack recovery
        sim_srv.current_node = "DEAD_END"
        sim_srv.previous_node = "JUNCTION"
        sim_srv.visited_nodes.append("DEAD_END")

        # Step at DEAD_END: MUST detect dead end and backtrack to JUNCTION
        step_dead = sim_srv.step()
        assert step_dead["current_node"] == "JUNCTION"
        assert step_dead["previous_node"] == "DEAD_END"
        assert step_dead["decision"]["type"] == "FORCED_DEAD_END_BACKTRACK"
        assert step_dead["backtrack_prevented"] is False

        # Next step at JUNCTION: previous_node is DEAD_END, forward to OUT!
        step_out = sim_srv.step()
        assert step_out["current_node"] == "OUT"
        assert step_out["is_finished"] is True
        assert step_out["escaped"] is True

    def test_dynamic_defense_recomputation_between_steps(self):
        """Dynamic defenses: placing a defense mid-simulation updates corridor hazard immediately."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("FORK", 10, 0)
        gm.add_maze_node("PATH_A", 20, -5)
        gm.add_maze_node("PATH_B", 20, 5)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        # Both paths initially identical length (10 each -> total 20 from FORK)
        gm.add_corridor("IN", "FORK", length=5.0, speed=1.0)
        gm.add_corridor("FORK", "PATH_A", length=10.0, speed=1.0)
        gm.add_corridor("PATH_A", "OUT", length=10.0, speed=1.0)
        gm.add_corridor("FORK", "PATH_B", length=10.0, speed=1.0)
        gm.add_corridor("PATH_B", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        hazard_srv = HazardService(scenario_srv)
        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)
        sim_srv.reset(alpha_danger=1.0)

        # Step 1: IN -> FORK (tie-break prefers PATH_A because 'P' == 'P', but 'PATH_A' < 'PATH_B')
        step1 = sim_srv.step()
        assert step1["current_node"] == "FORK"
        assert "PATH_A" in step1["projected_path"]

        # DYNAMIC DEFENSE: Deploy deadly sniper on PATH_A
        # PATH_A midpoint is at (15, -2.5)
        snip = DefenseUnit(SoldierType.SNIPER, x=15.0, y=-2.5, effective_range=10.0)
        hazard_srv.set_custom_defenses([snip])

        # Step 2 from FORK: should immediately detect hazard on PATH_A and divert to PATH_B!
        step2 = sim_srv.step()
        assert step2["current_node"] == "PATH_B", f"Expected diversion to PATH_B due to sniper on PATH_A, got {step2['current_node']}"
        assert step2["previous_node"] == "FORK"

    def test_dynamic_alpha_modulation_risk_inversion(self):
        """Modulating alpha flips route choice between fast-hazardous and slow-safe paths."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("OUT", 50, 0, is_exit=True)

        # Fast corridor: length 10, speed 1 -> base_time = 10s
        c_fast = gm.add_corridor("IN", "OUT", length=10.0, speed=1.0)
        # Slow corridor via intermediate MID: length 40, speed 1 -> base_time = 40s
        gm.add_maze_node("MID", 25, 20)
        c_slow1 = gm.add_corridor("IN", "MID", length=20.0, speed=1.0)
        c_slow2 = gm.add_corridor("MID", "OUT", length=20.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        hazard_srv = HazardService(scenario_srv)

        # Place sniper on fast corridor midpoint (25, 0) with range 10.0
        # Fast corridor mid is (25, 0): covered! q_ini(0,0) and q_end(50,0) are outside range.
        # Average danger = 25 / 3 = 8.333. Potential = 8.333 * 10 = 83.333.
        # Fast weight w_fast = 10 + alpha * 83.333
        # Slow detour via MID(25, 20) is entirely outside range 10: w_slow = 20 + 20 = 40.0 (zero hazard).
        # When alpha = 0.1: w_fast = 10 + 8.333 = 18.333 < 40.0 -> FAST wins!
        # When alpha = 1.0: w_fast = 10 + 83.333 = 93.333 > 40.0 -> SLOW wins!
        snip = DefenseUnit(SoldierType.SNIPER, x=25.0, y=0.0, effective_range=10.0)
        hazard_srv.set_custom_defenses([snip])

        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)

        # Case 1: alpha = 0.1 (Risk Tolerant)
        sim_srv.reset(alpha_danger=0.1)
        dec_tolerant = sim_srv.evaluate_step_decision(alpha=0.1)
        assert dec_tolerant["chosen_next_node"] == "OUT", "Low alpha should take fast direct corridor"

        # Case 2: alpha = 1.0 (Risk Averse)
        sim_srv.reset(alpha_danger=1.0)
        dec_averse = sim_srv.evaluate_step_decision(alpha=1.0)
        assert dec_averse["chosen_next_node"] == "MID", "High alpha should divert through safer detour"

    def test_multi_machine_sequential_damage_allocation(self):
        """Damage is sequentially absorbed front-to-back: Tank -> Truck -> Robot."""
        t = EnemyMachine(EnemyType.TANK, custom_hp=200.0)
        k = EnemyMachine(EnemyType.TRUCK, custom_hp=100.0)
        r = EnemyMachine(EnemyType.ROBOT, custom_hp=50.0)

        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("M1", 10, 0)
        gm.add_maze_node("OUT", 20, 0, is_exit=True)

        gm.add_corridor("IN", "M1", length=10.0, speed=1.0)
        gm.add_corridor("M1", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm, enemies=[t, k, r])
        hazard_srv = HazardService(scenario_srv)

        # Defenses that inflict exactly 250 damage on IN-M1
        # 10 snipers on midpoint (5, 0): D = 250 dmg/s, t = 10s -> danger potential is high
        # We can set custom danger potential directly or set units
        # Midpoint of IN-M1 is (5, 0). Length = 10, speed = 1 -> base_time = 10s.
        # To get 250 total damage: average danger D_bar = 25.0. 1 sniper covering all 3 points gives D_bar = 25.0!
        snip = DefenseUnit(SoldierType.SNIPER, x=5.0, y=0.0, effective_range=15.0)
        hazard_srv.set_custom_defenses([snip])

        sim_srv = SimulationService(scenario_service=scenario_srv, hazard_service=hazard_srv)
        sim_srv.reset()

        step1 = sim_srv.step()
        assert step1["current_node"] == "M1"
        # 250 damage inflicted:
        # Tank takes 200 (destroyed)
        assert t.is_alive is False
        assert t.current_hp == 0.0
        # Truck takes remaining 50 (alive with 50 HP)
        assert k.is_alive is True
        assert k.current_hp == 50.0
        # Robot takes 0 (alive with 50 HP)
        assert r.is_alive is True
        assert r.current_hp == 50.0
        # Total convoy HP = 100
        assert sim_srv.get_total_hp() == 100.0

    def test_cycle_loop_diversion_and_escape(self):
        """Triangle cycle A - B - C - A where convoy arrives at B from A.
        Unconstrained optimal from B would be to backtrack B -> A -> OUT.
        Anti-backtracking triggers at B, evaluates alternate neighbor C,
        diverts along B -> C -> A -> OUT, and safely escapes!
        """
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True)
        gm.add_maze_node("A", 10, 0)
        gm.add_maze_node("B", 20, 5)
        gm.add_maze_node("C", 20, -5)
        gm.add_maze_node("OUT", 30, 0, is_exit=True)

        # IN -> A
        gm.add_corridor("IN", "A", length=5.0, speed=1.0)
        # Cycle: A - B (length 2), B - C (length 2), C - A (length 2)
        gm.add_corridor("A", "B", length=2.0, speed=1.0)
        gm.add_corridor("B", "C", length=2.0, speed=1.0)
        gm.add_corridor("C", "A", length=2.0, speed=1.0)
        # Exit: A -> OUT (length 10)
        gm.add_corridor("A", "OUT", length=10.0, speed=1.0)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        # Step 1: IN -> A
        step1 = sim_srv.step()
        assert step1["current_node"] == "A"
        assert step1["previous_node"] == "IN"

        # Manually force convoy to step to B to test backtrack avoidance at B
        sim_srv.current_node = "B"
        sim_srv.previous_node = "A"
        sim_srv.visited_nodes.append("B")

        # At B, unconstrained Dijkstra to OUT would choose B -> A -> OUT (cost 2 + 10 = 12)
        # But A is previous_node! Anti-backtracking triggers!
        # Alternate neighbor is C. Route: B -> C -> A -> OUT (cost 2 + 2 + 10 = 14)
        step_b = sim_srv.step()
        assert step_b["decision"]["type"] == "ANTI_BACKTRACK_AVOIDED"
        assert step_b["decision"]["backtrack_prevented"] is True
        assert step_b["decision"]["discarded_node"] == "A"
        assert step_b["current_node"] == "C"
        assert step_b["previous_node"] == "B"

        # At C: previous_node is B. Route to OUT: C -> A -> OUT.
        # Next candidate is A != B. Moves to A!
        step_c = sim_srv.step()
        assert step_c["current_node"] == "A"
        assert step_c["previous_node"] == "C"

        # At A: previous_node is C. Route to OUT: A -> OUT.
        # Next candidate is OUT != C. Moves to OUT and escapes!
        step_a = sim_srv.step()
        assert step_a["current_node"] == "OUT"
        assert step_a["is_finished"] is True
        assert step_a["escaped"] is True
        assert step_a["destroyed"] is False

    def test_single_node_start_equals_target(self):
        """Graph where entry IN is also exit OUT."""
        gm = MazeGraph()
        gm.add_maze_node("IN", 0, 0, is_entry=True, is_exit=True)

        scenario_srv = build_scenario_service_with_graph(gm)
        sim_srv = SimulationService(scenario_service=scenario_srv)
        sim_srv.reset()

        assert sim_srv.current_node == "IN"
        assert sim_srv.target_node == "IN"

        step_res = sim_srv.step()
        assert step_res["is_finished"] is True
        assert step_res["escaped"] is True
        assert step_res["destroyed"] is False
        assert step_res["decision"]["type"] == "REACHED_EXIT"
