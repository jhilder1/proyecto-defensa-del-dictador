"""Logistics service for Stage 4: purchasing, ground dispatches, dynamic bridges, and helicopter circuits."""

from typing import Dict, List, Any, Optional, Tuple, Set, Union
from app.core.algorithms import calculate_euclidean_distance, dijkstra_elevated
from app.domain.node import ElevatedNode, ElevatedNodeType
from app.domain.soldier import Soldier, SoldierType, SOLDIER_CONFIG, parse_soldier_type
from app.domain.transport import (
    AirLeg,
    TransportMission,
    TransportType,
    TRANSPORT_CONFIG,
    parse_transport_type,
)
from app.services.scenario_service import ScenarioService


class LogisticsService:
    """Manages soldier acquisition, ground transport, bridge wear/rerouting, and aerial missions."""

    _instance: Optional["LogisticsService"] = None

    def __init__(self, scenario_service: Optional[ScenarioService] = None):
        self._scenario_service = scenario_service

    @property
    def scenario_service(self) -> ScenarioService:
        if self._scenario_service is not None:
            return self._scenario_service
        return ScenarioService.get_instance()

    @classmethod
    def get_instance(cls) -> "LogisticsService":
        if cls._instance is None:
            cls._instance = LogisticsService()
        return cls._instance

    def buy_soldier(
        self,
        soldier_type: Union[SoldierType, str],
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Purchases one or more soldiers and places them in waiting reserve at Base."""
        if quantity < 1:
            raise ValueError("La cantidad de soldados a comprar debe ser al menos 1.")

        s_type = parse_soldier_type(soldier_type)
        unit_cost = SOLDIER_CONFIG[s_type]["cost"]
        total_cost = unit_cost * int(quantity)

        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph

        base_node = ge.get_base_node()
        base_id = base_node.id if base_node else "Base"

        if not state.can_afford(total_cost):
            raise ValueError(
                f"Presupuesto insuficiente para comprar {quantity}x {s_type.value}. "
                f"Requerido: ${total_cost}, Disponible: ${round(state.budget_available, 2)}."
            )

        state.spend_budget(total_cost)
        purchased: List[Dict[str, Any]] = []

        for _ in range(int(quantity)):
            soldier = Soldier(
                soldier_type=s_type,
                location_node_id=base_id,
                status="en_base",
            )
            state.soldiers[soldier.id] = soldier
            purchased.append(soldier.to_dict())

        state.add_event(
            "SOLDIER_PURCHASED",
            f"Comprados {quantity}x {s_type.value} por ${total_cost}.",
            {"soldier_type": s_type.value, "quantity": quantity, "total_cost": total_cost},
        )

        return {
            "purchased": purchased,
            "total_cost": total_cost,
            "budget_available": round(state.budget_available, 2),
            "budget_reserved": round(state.budget_reserved, 2),
        }

    def dispatch_ground(
        self,
        transport_type: Union[TransportType, str],
        soldier_ids: List[str],
        destination_id: str,
        origin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches 1 soldier on foot or 1-2 soldiers by motorcycle along G_E."""
        t_type = parse_transport_type(transport_type)
        if t_type == TransportType.HELICOPTER:
            raise ValueError("Use dispatch_air para misiones en helicóptero.")

        if not soldier_ids:
            raise ValueError("Debe especificar al menos un soldado para el despacho.")
        if len(set(soldier_ids)) != len(soldier_ids):
            raise ValueError("La lista de soldados contiene identificadores duplicados.")

        max_cap = TRANSPORT_CONFIG[t_type]["max_capacity"]
        if len(soldier_ids) > max_cap:
            raise ValueError(
                f"El transporte '{t_type.value}' admite máximo {max_cap} soldado(s); se enviaron {len(soldier_ids)}."
            )

        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph

        dest = ge.get_elevated_node(destination_id)
        if not dest:
            raise ValueError(f"Torre destino '{destination_id}' no encontrada en la Red Elevada.")
        if not dest.is_active_tower or dest.node_type == ElevatedNodeType.BASE:
            raise ValueError(f"El nodo '{destination_id}' no es una torre defensiva habilitada.")
        if dest.available_slots < len(soldier_ids):
            raise ValueError(
                f"Capacidad insuficiente en torre '{dest.id}'. "
                f"Cupos disponibles: {dest.available_slots}, solicitados: {len(soldier_ids)}."
            )

        soldiers: List[Soldier] = []
        for s_id in soldier_ids:
            soldier = state.soldiers.get(s_id)
            if not soldier:
                raise ValueError(f"Soldado '{s_id}' no existe.")
            if soldier.status == "en_transito":
                raise ValueError(f"Soldado '{s_id}' ya se encuentra en tránsito.")
            if soldier.status == "apostado":
                raise ValueError(f"Soldado '{s_id}' ya está apostado en una torre.")
            soldiers.append(soldier)

        base_node = ge.get_base_node()
        default_origin = base_node.id if base_node else "Base"
        resolved_origin = str(origin_id) if origin_id else (soldiers[0].location_node_id or default_origin)

        for soldier in soldiers:
            if soldier.location_node_id != resolved_origin:
                raise ValueError(
                    f"Soldado '{soldier.id}' está en '{soldier.location_node_id}', no en el origen '{resolved_origin}'."
                )

        origin_node = ge.get_elevated_node(resolved_origin)
        if not origin_node:
            raise ValueError(f"Nodo origen '{resolved_origin}' no encontrado en la Red Elevada.")

        route_res = dijkstra_elevated(ge, resolved_origin, dest.id, mode=t_type)
        if route_res is None:
            raise ValueError(
                f"No existe ruta transitable en '{t_type.value}' desde '{resolved_origin}' hasta '{dest.id}'."
            )

        total_time, path = route_res

        # Reserve slots and commit transit status
        dest.reserved_slots += len(soldiers)
        for soldier in soldiers:
            soldier.status = "en_transito"
            soldier.location_node_id = None

        mission = TransportMission(
            transport_type=t_type,
            soldier_ids=soldier_ids,
            origin_id=resolved_origin,
            destination_id=dest.id,
            path=path,
            current_x=origin_node.x,
            current_y=origin_node.y,
        )
        state.active_missions.append(mission)

        state.add_event(
            "GROUND_DISPATCH",
            f"Despacho {t_type.value} ({len(soldiers)} soldado(s)) desde {resolved_origin} hacia {dest.id} (tiempo est: {round(total_time, 2)}s).",
            {"mission_id": mission.id, "path": path, "estimated_time": round(total_time, 2)},
        )

        return mission.to_dict()

    def dispatch_air(
        self,
        soldier_ids: List[str],
        destination_id: str,
    ) -> Dict[str, Any]:
        """Dispatches up to 4 soldiers by helicopter with automatic surplus redistribution."""
        if not soldier_ids:
            raise ValueError("Debe especificar al menos un soldado para el vuelo.")
        if len(set(soldier_ids)) != len(soldier_ids):
            raise ValueError("La lista de soldados contiene identificadores duplicados.")

        max_cap = TRANSPORT_CONFIG[TransportType.HELICOPTER]["max_capacity"]
        if len(soldier_ids) > max_cap:
            raise ValueError(f"El helicóptero tiene capacidad máxima de {max_cap} soldados.")

        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph

        heliport = ge.get_heliport_node()
        if not heliport:
            raise ValueError("El escenario no cuenta con un Helipuerto en la Red Elevada.")

        base_node = ge.get_base_node()
        if not base_node:
            raise ValueError("El escenario no cuenta con un nodo Base en la Red Elevada.")

        primary_dest = ge.get_elevated_node(destination_id)
        if not primary_dest:
            raise ValueError(f"Torre destino '{destination_id}' no encontrada.")
        if not primary_dest.is_active_tower or primary_dest.node_type == ElevatedNodeType.BASE:
            raise ValueError(f"El nodo '{destination_id}' no es una torre defensiva habilitada.")

        valid_origins = {base_node.id, heliport.id}
        soldiers: List[Soldier] = []
        for s_id in soldier_ids:
            soldier = state.soldiers.get(s_id)
            if not soldier:
                raise ValueError(f"Soldado '{s_id}' no existe.")
            if soldier.status != "en_base" or soldier.location_node_id not in valid_origins:
                raise ValueError(
                    f"Soldado '{s_id}' no está disponible en Base/Helipuerto (estado='{soldier.status}')."
                )
            soldiers.append(soldier)

        flight_cost = state.helicopter_cost
        if not state.can_afford(flight_cost):
            raise ValueError(
                f"Fondos insuficientes para vuelo en helicóptero. Costo: ${flight_cost}, Disponible: ${round(state.budget_available, 2)}."
            )

        # Plan single aerial circuit with surplus redistribution
        speed = state.helicopter_speed
        remaining = list(soldier_ids)
        legs: List[AirLeg] = []
        reservations_to_apply: List[Tuple[ElevatedNode, int]] = []
        visited_towers: Set[str] = set()

        # Leg 1: Heliport -> primary destination
        dist_1 = calculate_euclidean_distance((heliport.x, heliport.y), (primary_dest.x, primary_dest.y))
        dur_1 = dist_1 / speed
        can_take_1 = min(primary_dest.available_slots, len(remaining))
        dropoffs_1 = remaining[:can_take_1]
        remaining = remaining[can_take_1:]
        if can_take_1 > 0:
            reservations_to_apply.append((primary_dest, can_take_1))
        visited_towers.add(primary_dest.id)

        legs.append(
            AirLeg(
                from_node_id=heliport.id,
                to_node_id=primary_dest.id,
                from_pos=(heliport.x, heliport.y),
                to_pos=(primary_dest.x, primary_dest.y),
                distance=dist_1,
                duration=dur_1,
                dropoff_soldiers=dropoffs_1,
                is_return_to_base=False,
            )
        )
        curr_node = primary_dest

        # Subsequent legs for surplus redistribution
        while remaining:
            candidate_towers = [
                n
                for n in ge.elevated_nodes.values()
                if n.is_active_tower
                and n.node_type != ElevatedNodeType.BASE
                and n.id not in visited_towers
                and n.available_slots > 0
            ]

            if candidate_towers:
                candidate_towers.sort(
                    key=lambda n: (
                        calculate_euclidean_distance((curr_node.x, curr_node.y), (n.x, n.y)),
                        n.id,
                    )
                )
                nxt = candidate_towers[0]
                dist = calculate_euclidean_distance((curr_node.x, curr_node.y), (nxt.x, nxt.y))
                dur = dist / speed
                can_take = min(nxt.available_slots, len(remaining))
                dropoffs = remaining[:can_take]
                remaining = remaining[can_take:]
                reservations_to_apply.append((nxt, can_take))
                visited_towers.add(nxt.id)

                legs.append(
                    AirLeg(
                        from_node_id=curr_node.id,
                        to_node_id=nxt.id,
                        from_pos=(curr_node.x, curr_node.y),
                        to_pos=(nxt.x, nxt.y),
                        distance=dist,
                        duration=dur,
                        dropoff_soldiers=dropoffs,
                        is_return_to_base=False,
                    )
                )
                curr_node = nxt
            else:
                # No space left in any enabled tower -> return surplus to Base
                dist = calculate_euclidean_distance((curr_node.x, curr_node.y), (base_node.x, base_node.y))
                dur = dist / speed
                legs.append(
                    AirLeg(
                        from_node_id=curr_node.id,
                        to_node_id=base_node.id,
                        from_pos=(curr_node.x, curr_node.y),
                        to_pos=(base_node.x, base_node.y),
                        distance=dist,
                        duration=dur,
                        dropoff_soldiers=list(remaining),
                        is_return_to_base=True,
                    )
                )
                remaining = []

        # Commit reservations atomically
        state.reserve_budget(flight_cost)
        for node, count in reservations_to_apply:
            node.reserved_slots += count
        for soldier in soldiers:
            soldier.status = "en_transito"
            soldier.location_node_id = None

        circuit_path = [heliport.id] + [leg.to_node_id for leg in legs]
        mission = TransportMission(
            transport_type=TransportType.HELICOPTER,
            soldier_ids=soldier_ids,
            origin_id=heliport.id,
            destination_id=primary_dest.id,
            path=circuit_path,
            legs=legs,
            reserved_cost=flight_cost,
            current_x=heliport.x,
            current_y=heliport.y,
        )
        state.active_missions.append(mission)

        state.add_event(
            "AIR_DISPATCH",
            f"Vuelo aéreo despachado desde {heliport.id} hacia {primary_dest.id} con {len(soldiers)} soldado(s) (circuito: {' -> '.join(circuit_path)}).",
            {
                "mission_id": mission.id,
                "circuit": circuit_path,
                "flight_cost": flight_cost,
                "total_duration": round(mission.total_flight_duration, 2),
            },
        )

        return mission.to_dict()

    def advance_missions(self, dt: float) -> List[Dict[str, Any]]:
        """Advances all active ground and air transport missions by dt seconds."""
        state = self.scenario_service.simulation_state
        events: List[Dict[str, Any]] = []

        for mission in state.active_missions:
            if mission.is_completed:
                continue

            if mission.transport_type == TransportType.HELICOPTER:
                self._advance_air_mission(mission, dt, events)
            else:
                self._advance_ground_mission(mission, dt, events)

        return events

    def _complete_ground_arrival(
        self,
        mission: TransportMission,
        events: List[Dict[str, Any]],
    ) -> None:
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph
        dest = ge.get_elevated_node(mission.destination_id)

        if dest:
            dest.reserved_slots = max(0, dest.reserved_slots - len(mission.soldier_ids))
            mission.current_x = dest.x
            mission.current_y = dest.y
            for s_id in mission.soldier_ids:
                if s_id not in dest.stationed_soldiers:
                    dest.stationed_soldiers.append(s_id)
                if s_id in state.soldiers:
                    state.soldiers[s_id].location_node_id = dest.id
                    state.soldiers[s_id].status = "apostado"
            mission.delivered_map[dest.id] = list(mission.soldier_ids)

        mission.is_completed = True
        mission.is_blocked = False
        msg = f"Misión {mission.transport_type.value} ({mission.id}) llegó a torre {mission.destination_id}."
        state.add_event("GROUND_ARRIVAL", msg, {"mission_id": mission.id, "destination": mission.destination_id})
        events.append({"type": "GROUND_ARRIVAL", "message": msg, "mission_id": mission.id})

    def _advance_ground_mission(
        self,
        mission: TransportMission,
        dt: float,
        events: List[Dict[str, Any]],
    ) -> None:
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph
        remaining_dt = float(dt)

        while remaining_dt > 1e-9 and not mission.is_completed:
            if mission.current_step_index >= len(mission.path) - 1:
                self._complete_ground_arrival(mission, events)
                break

            u = mission.path[mission.current_step_index]
            v = mission.path[mission.current_step_index + 1]
            node_u = ge.get_elevated_node(u)
            node_v = ge.get_elevated_node(v)
            edge = ge.get_elevated_edge(u, v)

            if not mission.started_current_edge:
                if edge is None or not edge.is_passable():
                    # Bridge is impassable before entering; attempt reroute from node u
                    new_res = dijkstra_elevated(ge, u, mission.destination_id, mode=mission.transport_type)
                    if new_res is not None:
                        _, new_path = new_res
                        mission.path = new_path
                        mission.current_step_index = 0
                        mission.edge_progress = 0.0
                        mission.started_current_edge = False
                        if mission.is_blocked:
                            mission.is_blocked = False
                            resume_msg = f"Misión {mission.id} reanudada por ruta alterna desde {u}."
                            state.add_event("MISSION_RESUMED", resume_msg, {"mission_id": mission.id})
                            events.append({"type": "MISSION_RESUMED", "message": resume_msg})

                        reroute_msg = f"Misión {mission.id} recalculó ruta por puente caído ({u}-{v}): {' -> '.join(new_path)}."
                        state.add_event("MISSION_REROUTED", reroute_msg, {"mission_id": mission.id, "path": new_path})
                        events.append({"type": "MISSION_REROUTED", "message": reroute_msg})
                        continue
                    else:
                        if not mission.is_blocked:
                            mission.is_blocked = True
                            block_msg = f"Misión {mission.id} bloqueada en {u}: puente {u}-{v} caído sin ruta alterna."
                            state.add_event("MISSION_BLOCKED", block_msg, {"mission_id": mission.id, "node": u})
                            events.append({"type": "MISSION_BLOCKED", "message": block_msg})
                        if node_u:
                            mission.current_x = node_u.x
                            mission.current_y = node_u.y
                        break
                else:
                    if mission.is_blocked:
                        mission.is_blocked = False
                        resume_msg = f"Misión {mission.id} reanudada en {u} tras reconstrucción del puente {u}-{v}."
                        state.add_event("MISSION_RESUMED", resume_msg, {"mission_id": mission.id})
                        events.append({"type": "MISSION_RESUMED", "message": resume_msg})
                    mission.started_current_edge = True

            # Currently crossing edge u -> v (allowed to finish even if bridge collapsed)
            edge_duration = edge.foot_time if mission.transport_type == TransportType.FOOT else edge.moto_time
            time_left = max(0.0, edge_duration - mission.edge_progress)

            if remaining_dt >= time_left - 1e-9:
                remaining_dt -= time_left
                mission.edge_progress = 0.0
                mission.started_current_edge = False
                mission.current_step_index += 1
                if node_v:
                    mission.current_x = node_v.x
                    mission.current_y = node_v.y

                if mission.transport_type == TransportType.MOTORCYCLE and edge.is_bridge:
                    collapsed = ge.record_motorcycle_bridge_crossing(u, v)
                    if collapsed:
                        col_msg = (
                            f"Puente {edge.u}-{edge.v} colapsó tras cruce en moto "
                            f"(reconstrucción en {edge.reconstruction_duration}s)."
                        )
                        state.add_event("BRIDGE_COLLAPSED", col_msg, {"edge": f"{edge.u}-{edge.v}"})
                        events.append({"type": "BRIDGE_COLLAPSED", "message": col_msg})
                    else:
                        dmg_msg = (
                            f"Puente {edge.u}-{edge.v} desgastado por moto "
                            f"(resistencia: {edge.current_resistance}/{edge.max_resistance})."
                        )
                        state.add_event("BRIDGE_DAMAGED", dmg_msg, {"edge": f"{edge.u}-{edge.v}"})
                        events.append({"type": "BRIDGE_DAMAGED", "message": dmg_msg})

                if mission.current_step_index >= len(mission.path) - 1:
                    self._complete_ground_arrival(mission, events)
                    break
            else:
                mission.edge_progress += remaining_dt
                remaining_dt = 0.0
                if node_u and node_v and edge_duration > 1e-9:
                    ratio = min(1.0, max(0.0, mission.edge_progress / edge_duration))
                    mission.current_x = node_u.x + (node_v.x - node_u.x) * ratio
                    mission.current_y = node_u.y + (node_v.y - node_u.y) * ratio

    def _advance_air_mission(
        self,
        mission: TransportMission,
        dt: float,
        events: List[Dict[str, Any]],
    ) -> None:
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph
        remaining_dt = float(dt)

        while remaining_dt >= 0.0 and not mission.is_completed:
            if mission.current_leg_index >= len(mission.legs):
                mission.is_completed = True
                state.commit_reserved_budget(mission.reserved_cost)
                done_msg = f"Misión aérea {mission.id} completada."
                state.add_event("AIR_MISSION_COMPLETE", done_msg, {"mission_id": mission.id})
                events.append({"type": "AIR_MISSION_COMPLETE", "message": done_msg})
                break

            leg = mission.legs[mission.current_leg_index]
            time_left = max(0.0, leg.duration - mission.leg_progress)

            if remaining_dt >= time_left - 1e-9:
                remaining_dt -= time_left
                mission.leg_progress = 0.0
                mission.current_x, mission.current_y = leg.to_pos

                if leg.is_return_to_base:
                    for s_id in leg.dropoff_soldiers:
                        if s_id in state.soldiers:
                            state.soldiers[s_id].location_node_id = leg.to_node_id
                            state.soldiers[s_id].status = "en_base"
                    if leg.dropoff_soldiers:
                        mission.delivered_map.setdefault(leg.to_node_id, []).extend(leg.dropoff_soldiers)
                    ret_msg = f"Helicóptero ({mission.id}) retornó {len(leg.dropoff_soldiers)} soldado(s) excedente(s) a {leg.to_node_id}."
                    state.add_event("AIR_RETURN_BASE", ret_msg, {"mission_id": mission.id, "soldiers": leg.dropoff_soldiers})
                    events.append({"type": "AIR_RETURN_BASE", "message": ret_msg})
                else:
                    tower = ge.get_elevated_node(leg.to_node_id)
                    if tower:
                        tower.reserved_slots = max(0, tower.reserved_slots - len(leg.dropoff_soldiers))
                        for s_id in leg.dropoff_soldiers:
                            if s_id not in tower.stationed_soldiers:
                                tower.stationed_soldiers.append(s_id)
                            if s_id in state.soldiers:
                                state.soldiers[s_id].location_node_id = tower.id
                                state.soldiers[s_id].status = "apostado"
                    if leg.dropoff_soldiers:
                        mission.delivered_map.setdefault(leg.to_node_id, []).extend(leg.dropoff_soldiers)
                    drop_msg = f"Helicóptero ({mission.id}) desembarcó {len(leg.dropoff_soldiers)} soldado(s) en {leg.to_node_id}."
                    state.add_event("AIR_DROPOFF", drop_msg, {"mission_id": mission.id, "tower": leg.to_node_id, "soldiers": leg.dropoff_soldiers})
                    events.append({"type": "AIR_DROPOFF", "message": drop_msg})

                mission.current_leg_index += 1
                if mission.current_leg_index >= len(mission.legs):
                    mission.is_completed = True
                    state.commit_reserved_budget(mission.reserved_cost)
                    done_msg = f"Misión aérea {mission.id} completada."
                    state.add_event("AIR_MISSION_COMPLETE", done_msg, {"mission_id": mission.id})
                    events.append({"type": "AIR_MISSION_COMPLETE", "message": done_msg})
                    break

                if remaining_dt <= 1e-9:
                    break
            else:
                mission.leg_progress += remaining_dt
                remaining_dt = 0.0
                if leg.duration > 1e-9:
                    ratio = min(1.0, max(0.0, mission.leg_progress / leg.duration))
                    mission.current_x = leg.from_pos[0] + (leg.to_pos[0] - leg.from_pos[0]) * ratio
                    mission.current_y = leg.from_pos[1] + (leg.to_pos[1] - leg.from_pos[1]) * ratio
                break

    def get_logistics_state(self) -> Dict[str, Any]:
        """Returns current budget, soldier roster, active/completed missions, bridges, and tower occupancies."""
        state = self.scenario_service.simulation_state
        ge = self.scenario_service.elevated_graph

        return {
            "budget": {
                "initial": round(state.initial_budget, 2),
                "available": round(state.budget_available, 2),
                "reserved": round(state.budget_reserved, 2),
                "total": round(state.total_budget, 2),
            },
            "soldiers": [s.to_dict() for s in state.soldiers.values()],
            "missions": [m.to_dict() for m in state.active_missions],
            "bridges": [b.to_dict() for b in ge.get_bridges()],
            "towers": [
                n.to_dict()
                for n in ge.elevated_nodes.values()
                if n.is_active_tower and n.node_type != ElevatedNodeType.BASE
            ],
        }
