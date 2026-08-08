class Switch:
    def __init__(self, id, name, switch_state, indicator_state, powered, available):
        self.id = id
        self.name = name
        self.switch_state = switch_state
        self.indicator_state = indicator_state
        self.powered = powered
        self.available = available

switches = []

switches.append(
    Switch(
        id = 1,
        name="Test Switch",
        switch_state = True,
        indicator_state = True,
        powered = True,
        available = True
    )
)


def req_data(data):
    print("Requesting data:", data)