"""Single runtime gateway for developer-only technical observations."""

TECHNICAL_TOOLS = {"read_console", "list_failed_requests"}


class ObservationGateway:
    def __init__(self, persona, collector):
        self.persona, self.collector = persona, collector
        self.allowed = (set(persona.browsing_profile.tools) & TECHNICAL_TOOLS
                        if persona.browsing_profile.tech_level == "developer" else set())
        self.observed = {}

    def observe(self, name, events):
        if name not in self.allowed:
            self.collector.record("technical_access_denied", {"persona_id": self.persona.persona_id, "tool": name})
            return None
        self.observed.update({item["event_id"]: item for item in events})
        self.collector.record("technical_tool_access", {"persona_id": self.persona.persona_id, "tool": name,
                              "event_ids": [item["event_id"] for item in events]})
        return events
