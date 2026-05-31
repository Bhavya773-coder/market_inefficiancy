from ai.event_bus import EventBus

bus = EventBus()
bus.create_group("test_group")

print("=== CONSUMER STARTED ===")

while True:
    data = bus.read_ticks("test_group", "consumer_1")

    if data:
        for stream, messages in data:
            for msg_id, msg in messages:
                print("RECEIVED:", msg)
