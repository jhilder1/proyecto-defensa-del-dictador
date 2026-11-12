"""Unit tests for Stage 3 Corridor Hazard Calculations (Requirement R3, F4-F6).

Verifies:
- Point damage rate D(q) = sum(d_s * f_s)
- Single-count artillery rule: D(q) counts gunners at most once
- Effective range R_ef = R_base * (1 + beta * z)
- Average corridor hazard D_bar(e) over 3 points (q_ini, q_mid, q_end)
- Potential damage P(e) = D_bar(e) * t(e)
- Reactive edge weight w(e) = t(e) + alpha * P(e)
- Edge cases: alpha=0 neutrality, zero hazard, elevation boundary values
"""

import pytest
from app.domain.soldier import DefenseUnit, SoldierType
from app.domain.edge import MazeEdge
from app.core.maze_graph import MazeGraph
from app.services.hazard_service import (
    calculate_point_damage,
    calculate_corridor_hazard,
    get_covering_defenses,
)


class TestPointDamageRate:
    def test_single_infantry_damage_rate(self):
        """Infantería: damage=10.0, fire_rate=1.0 -> 10.0 damage/s."""
        unit = DefenseUnit(SoldierType.INFANTRY, x=0.0, y=0.0, effective_range=10.0)
        damage = calculate_point_damage((0.0, 5.0), [unit])
        assert damage == 10.0

    def test_single_sniper_damage_rate(self):
        """Francotirador: damage=50.0, fire_rate=0.5 -> 25.0 damage/s."""
        unit = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=20.0)
        damage = calculate_point_damage((0.0, 10.0), [unit])
        assert damage == 25.0

    def test_single_gunner_damage_rate(self):
        """Artillero: damage=100.0, fire_rate=0.2 -> 20.0 damage/s."""
        unit = DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=15.0)
        damage = calculate_point_damage((0.0, 5.0), [unit])
        assert damage == 20.0

    def test_single_count_artillery_rule_with_multiple_gunners(self):
        """CRITICAL: Single-count artillery rule.
        Regardless of how many gunners reach q, artillery contribution is counted AT MOST ONCE (20.0).
        """
        g1 = DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=20.0, unit_id="g1")
        g2 = DefenseUnit(SoldierType.GUNNER, x=5.0, y=0.0, effective_range=20.0, unit_id="g2")
        g3 = DefenseUnit(SoldierType.GUNNER, x=0.0, y=5.0, effective_range=20.0, unit_id="g3")
        g4 = DefenseUnit(SoldierType.GUNNER, x=2.0, y=2.0, effective_range=20.0, unit_id="g4")

        # 2 gunners covering q=(1.0, 1.0)
        dmg_2 = calculate_point_damage((1.0, 1.0), [g1, g2])
        assert dmg_2 == 20.0, "2 gunners must yield exactly 20.0, not 40.0"

        # 3 gunners covering q=(1.0, 1.0)
        dmg_3 = calculate_point_damage((1.0, 1.0), [g1, g2, g3])
        assert dmg_3 == 20.0, "3 gunners must yield exactly 20.0, not 60.0"

        # 4 gunners covering q=(1.0, 1.0)
        dmg_4 = calculate_point_damage((1.0, 1.0), [g1, g2, g3, g4])
        assert dmg_4 == 20.0, "4 gunners must yield exactly 20.0, not 80.0"

    def test_mixed_defenses_coverage(self):
        """1 Infantry (10.0), 2 Snipers (2 * 25.0 = 50.0), and 3 Gunners (20.0 once).
        Total D(q) = 10.0 + 50.0 + 20.0 = 80.0.
        """
        inf = DefenseUnit(SoldierType.INFANTRY, x=0.0, y=0.0, effective_range=20.0, unit_id="inf")
        snip1 = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=20.0, unit_id="s1")
        snip2 = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=20.0, unit_id="s2")
        gun1 = DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=20.0, unit_id="g1")
        gun2 = DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=20.0, unit_id="g2")
        gun3 = DefenseUnit(SoldierType.GUNNER, x=0.0, y=0.0, effective_range=20.0, unit_id="g3")

        dmg = calculate_point_damage((1.0, 1.0), [inf, snip1, snip2, gun1, gun2, gun3])
        assert dmg == 80.0

    def test_unreachable_point_damage_is_zero(self):
        """Point outside range of all units has D(q) = 0.0."""
        unit = DefenseUnit(SoldierType.INFANTRY, x=0.0, y=0.0, effective_range=5.0)
        # Point at dist = 10.0 > 5.0
        damage = calculate_point_damage((10.0, 0.0), [unit])
        assert damage == 0.0


class TestElevationEffectiveRange:
    def test_elevation_formula(self):
        """R_ef = R_base * (1 + beta * z)."""
        # Infantry R_base = 5.0, z = 10.0, beta = 0.1 -> 5.0 * (1 + 1.0) = 10.0
        inf = DefenseUnit(SoldierType.INFANTRY, x=0, y=0, z=10.0, beta=0.1)
        assert inf.effective_range == pytest.approx(10.0)

        # Sniper R_base = 20.0, z = 10.0, beta = 0.1 -> 20.0 * (1 + 1.0) = 40.0
        snip = DefenseUnit(SoldierType.SNIPER, x=0, y=0, z=10.0, beta=0.1)
        assert snip.effective_range == pytest.approx(40.0)

        # Gunner R_base = 15.0, z = 10.0, beta = 0.1 -> 15.0 * (1 + 1.0) = 30.0
        gun = DefenseUnit(SoldierType.GUNNER, x=0, y=0, z=10.0, beta=0.1)
        assert gun.effective_range == pytest.approx(30.0)

    def test_zero_and_negative_elevation(self):
        """Elevation z=0 yields R_base. Negative elevation clamps to z=0."""
        unit_z0 = DefenseUnit(SoldierType.SNIPER, x=0, y=0, z=0.0, beta=0.1)
        assert unit_z0.effective_range == pytest.approx(20.0)

        unit_neg = DefenseUnit(SoldierType.SNIPER, x=0, y=0, z=-5.0, beta=0.1)
        assert unit_neg.effective_range == pytest.approx(20.0)


class TestCorridorHazardCalculations:
    def test_three_point_sampling_average(self):
        """Corridor e=(u, v) evaluated at q_ini, q_mid, q_end.
        D_bar(e) = (D(q_ini) + D(q_mid) + D(q_end)) / 3.0.
        """
        gm = MazeGraph()
        gm.add_maze_node("A", x=0.0, y=0.0)
        gm.add_maze_node("B", x=20.0, y=0.0)
        corr = gm.add_corridor("A", "B", length=20.0, speed=2.0)

        # q_ini = (0, 0), q_mid = (10, 0), q_end = (20, 0)
        # Defense covers ONLY q_ini (x=0, y=0) with 1 Infantry -> D(q_ini)=10, D(q_mid)=0, D(q_end)=0
        unit = DefenseUnit(SoldierType.INFANTRY, x=0.0, y=0.0, effective_range=5.0)

        hazard = calculate_corridor_hazard(corr, [unit], alpha=1.0, maze_graph=gm)
        expected_d_bar = (10.0 + 0.0 + 0.0) / 3.0
        assert hazard.avg_danger == pytest.approx(expected_d_bar)

        # Time t(e) = 20 / 2 = 10.0 s
        expected_p = expected_d_bar * 10.0
        assert hazard.danger_potential == pytest.approx(expected_p)

        # w(e) = t(e) + 1.0 * P(e)
        expected_w = 10.0 + 1.0 * expected_p
        assert hazard.reactive_weight == pytest.approx(expected_w)

    def test_directional_invariance(self):
        """Corridor hazard is identical regardless of whether evaluated u->v or v->u."""
        gm = MazeGraph()
        gm.add_maze_node("U", x=0.0, y=0.0)
        gm.add_maze_node("V", x=30.0, y=0.0)
        corr_uv = gm.add_corridor("U", "V", length=30.0, speed=5.0)

        # Asymmetric defense covering U and middle, but not V
        unit1 = DefenseUnit(SoldierType.SNIPER, x=0.0, y=0.0, effective_range=15.0)
        unit2 = DefenseUnit(SoldierType.GUNNER, x=15.0, y=0.0, effective_range=10.0)

        h1 = calculate_corridor_hazard(corr_uv, [unit1, unit2], alpha=1.5, maze_graph=gm)

        # Inverted corridor
        gm2 = MazeGraph()
        gm2.add_maze_node("V", x=30.0, y=0.0)
        gm2.add_maze_node("U", x=0.0, y=0.0)
        corr_vu = gm2.add_corridor("V", "U", length=30.0, speed=5.0)

        h2 = calculate_corridor_hazard(corr_vu, [unit1, unit2], alpha=1.5, maze_graph=gm2)

        assert h1.avg_danger == pytest.approx(h2.avg_danger)
        assert h1.danger_potential == pytest.approx(h2.danger_potential)
        assert h1.reactive_weight == pytest.approx(h2.reactive_weight)

    def test_alpha_zero_ignores_danger(self):
        """When alpha = 0, reactive weight w(e) == base_time t(e), ignoring all hazards."""
        gm = MazeGraph()
        gm.add_maze_node("N1", x=0.0, y=0.0)
        gm.add_maze_node("N2", x=50.0, y=0.0)
        corr = gm.add_corridor("N1", "N2", length=50.0, speed=5.0)  # base_time = 10.0s

        # Very deadly coverage (sniper + gunner)
        units = [
            DefenseUnit(SoldierType.SNIPER, x=25.0, y=0.0, effective_range=30.0),
            DefenseUnit(SoldierType.GUNNER, x=25.0, y=0.0, effective_range=30.0),
        ]

        hazard = calculate_corridor_hazard(corr, units, alpha=0.0, maze_graph=gm)
        assert hazard.avg_danger > 0.0
        assert hazard.danger_potential > 0.0
        assert hazard.reactive_weight == pytest.approx(10.0), "With alpha=0, w(e) must equal base_time 10.0"

    def test_zero_hazard_corridor_weight_equals_base_time(self):
        """Corridor with no defense coverage has D_bar=0, P=0, and w=base_time for any alpha."""
        gm = MazeGraph()
        gm.add_maze_node("Safe1", x=500.0, y=500.0)
        gm.add_maze_node("Safe2", x=550.0, y=500.0)
        corr = gm.add_corridor("Safe1", "Safe2", length=50.0, speed=10.0)  # base_time = 5.0s

        hazard = calculate_corridor_hazard(corr, [], alpha=2.5, maze_graph=gm)
        assert hazard.avg_danger == 0.0
        assert hazard.danger_potential == 0.0
        assert hazard.reactive_weight == pytest.approx(5.0)
