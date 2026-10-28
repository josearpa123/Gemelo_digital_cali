class Controller:
    """Strategy interface. `sumo` is the libsumo/traci module of the running simulation."""

    name = "base"
    label = "base"

    def activate(self, sumo, programs: dict) -> None:
        """Take control of all tls. `programs` holds the original SUMO logics per tls."""

    def step(self, sumo) -> None:
        """Called once before every simulation step."""

    def after_step(self) -> None:
        """Called once after every simulation step."""

    def deactivate(self, sumo, programs: dict) -> None:
        """Release control and restore the original programs."""
        restore_programs(sumo, programs)


def restore_programs(sumo, programs: dict) -> None:
    for tls_id, (program_id, logics) in programs.items():
        for logic in logics:
            sumo.trafficlight.setProgramLogic(tls_id, logic)
        sumo.trafficlight.setProgram(tls_id, program_id)
