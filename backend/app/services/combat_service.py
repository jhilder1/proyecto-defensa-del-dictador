"""Combat service for Stage 5: per-tick soldier attacks, effective range, cooldowns, and bounties."""

from typing import Dict, List, Any, Optional, Tuple
from app.core.algorithms import calculate_euclidean_distance
from app.domain.node import ElevatedNodeType
from app.services.scenario_service import ScenarioService


class CombatService:
    """Executes discrete combat attacks from stationed soldiers against the enemy convoy."""

    _instance: Optional["CombatService"] = None

    def __init__(self, scenario_service: Optional[ScenarioService] = None):
        self._scenario_service = scenario_service

    @property
    def scenario_service(self) -> ScenarioService:
        if self._scenario_service is not None:
            return self._scenario_service
        return ScenarioService.get_instance()

    @classmethod
    def get_instance(cls) -> "CombatService":
        if cls._instance is None:
            cls._instance = CombatService()
        return cls._instance

    def execute_combat_tick(
        self,
        dt: float,
        convoy_pos: Tuple[float, float],
        scenario_service: Optional[ScenarioService] = None,
    ) -> Dict[str, Any]:
        """Executes cooldown updates, tower attacks, enemy destruction, and bounty credits."""
        srv = scenario_service or self.scenario_service
        state = srv.simulation_state
        ge = srv.elevated_graph

        # Gather all active non-Base towers deterministically
        active_towers = sorted(
            [
                n
                for n in ge.elevated_nodes.values()
                if n.is_active_tower and n.node_type != ElevatedNodeType.BASE
            ],
            key=lambda n: n.id,
        )

        # 1. Update cooldowns for all stationed soldiers (even if convoy is out of range)
        for tower in active_towers:
            for s_id in tower.stationed_soldiers:
                soldier = state.soldiers.get(s_id)
                if soldier:
                    soldier.update_cooldown(dt)

        alive_before = {e.id for e in state.get_alive_enemies()}
        attacks: List[Dict[str, Any]] = []
        total_damage_dealt = 0.0

        # 2. Execute attacks
        for tower in active_towers:
            dist = calculate_euclidean_distance((tower.x, tower.y), convoy_pos)
            for s_id in sorted(tower.stationed_soldiers):
                alive_enemies = state.get_alive_enemies()
                if not alive_enemies:
                    break

                soldier = state.soldiers.get(s_id)
                if not soldier:
                    continue

                r_ef = soldier.get_effective_range(tower.z, beta=state.beta_elevation)
                if dist <= r_ef + 1e-9 and soldier.can_attack():
                    if soldier.is_area:
                        # Gunner: area damage to ALL alive enemies in range
                        hit_targets: List[str] = []
                        dealt_this_shot = 0.0
                        for enemy in alive_enemies:
                            dmg = enemy.take_damage(soldier.damage)
                            dealt_this_shot += dmg
                            total_damage_dealt += dmg
                            hit_targets.append(enemy.id)
                        soldier.trigger_attack()
                        attacks.append({
                            "soldier_id": soldier.id,
                            "soldier_type": soldier.soldier_type.value,
                            "tower_id": tower.id,
                            "is_area": True,
                            "targets": hit_targets,
                            "damage_dealt": round(dealt_this_shot, 2),
                        })
                        state.add_event(
                            "COMBAT_ATTACK",
                            f"{soldier.soldier_type.value} en {tower.id} realizó ataque en área sobre {len(hit_targets)} máquina(s) ({round(dealt_this_shot, 1)} daño).",
                            {"tower_id": tower.id, "soldier_id": soldier.id, "targets": hit_targets},
                        )
                    else:
                        # Infantry / Sniper: single-target attack on alive enemy with lowest HP
                        target = min(alive_enemies, key=lambda e: (e.current_hp, e.id))
                        dmg = target.take_damage(soldier.damage)
                        total_damage_dealt += dmg
                        soldier.trigger_attack()
                        attacks.append({
                            "soldier_id": soldier.id,
                            "soldier_type": soldier.soldier_type.value,
                            "tower_id": tower.id,
                            "is_area": False,
                            "targets": [target.id],
                            "damage_dealt": round(dmg, 2),
                        })
                        state.add_event(
                            "COMBAT_ATTACK",
                            f"{soldier.soldier_type.value} en {tower.id} impactó a {target.enemy_type.value} ({target.id}) por {round(dmg, 1)} daño.",
                            {"tower_id": tower.id, "soldier_id": soldier.id, "target_id": target.id},
                        )

        # 3. Destruction checks and bounty rewards
        newly_destroyed = [
            e for e in state.enemies
            if e.id in alive_before and not e.is_alive
        ]
        rewards_earned = 0
        for enemy in newly_destroyed:
            state.add_reward(enemy.reward)
            rewards_earned += enemy.reward
            state.add_event(
                "ENEMY_DESTROYED",
                f"{enemy.enemy_type.value} ({enemy.id}) destruido! Recompensa acreditada: +${enemy.reward}.",
                {"enemy_id": enemy.id, "enemy_type": enemy.enemy_type.value, "reward": enemy.reward},
            )

        return {
            "attacks": attacks,
            "destroyed_enemies": [e.to_dict() for e in newly_destroyed],
            "rewards_earned": rewards_earned,
            "total_damage_dealt": round(total_damage_dealt, 2),
        }
