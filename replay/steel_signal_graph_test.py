from ai.steel_signal_graph import SteelSignalGraph

def main():
    print("Instantiating SteelSignalGraph...")
    graph = SteelSignalGraph()

    # 1. Print all relationships
    print("\n--- All Relationships ---")
    all_rels = graph.all()
    for rel in all_rels:
        print(f"Source: {rel['source']} -> Target: {rel['target']} (Type: {rel['relationship_type']}, Direction: {rel['direction']}, Weight: {rel['weight']}, Lag: {rel['lag_expectation']})")

    # 2. Print drivers_for("STEEL_FUTURE")
    print("\n--- Drivers for STEEL_FUTURE ---")
    drivers_future = graph.drivers_for("STEEL_FUTURE")
    for rel in drivers_future:
        print(f"Source: {rel['source']}, Weight: {rel['weight']}")

    # 3. Print drivers_for("STEEL_PHYSICAL_PLATE")
    print("\n--- Drivers for STEEL_PHYSICAL_PLATE ---")
    drivers_plate = graph.drivers_for("STEEL_PHYSICAL_PLATE")
    for rel in drivers_plate:
        print(f"Source: {rel['source']}, Weight: {rel['weight']}")

    # 4. Print targets_for("IRON_ORE")
    print("\n--- Targets for IRON_ORE ---")
    targets_ore = graph.targets_for("IRON_ORE")
    for rel in targets_ore:
        print(f"Target: {rel['target']}, Weight: {rel['weight']}")

    # 5. Print by_type("cost_pressure")
    print("\n--- By Type: cost_pressure ---")
    cost_pressure_rels = graph.by_type("cost_pressure")
    for rel in cost_pressure_rels:
        print(f"Source: {rel['source']} -> Target: {rel['target']}, Weight: {rel['weight']}")

    # 6. Print weighted_drivers_for("STEEL_FUTURE")
    print("\n--- Weighted Drivers for STEEL_FUTURE (Sorted by Weight Descending) ---")
    weighted_drivers = graph.weighted_drivers_for("STEEL_FUTURE")
    for rel in weighted_drivers:
        print(f"Source: {rel['source']}, Weight: {rel['weight']}")

    # Assertions
    print("\nRunning assertions...")
    assert len(all_rels) >= 10, f"Expected >= 10 relationships, got {len(all_rels)}"
    assert len(drivers_future) >= 6, f"Expected >= 6 drivers for STEEL_FUTURE, got {len(drivers_future)}"
    assert len(drivers_plate) >= 3, f"Expected >= 3 drivers for STEEL_PHYSICAL_PLATE, got {len(drivers_plate)}"
    
    target_symbols = [rel["target"] for rel in targets_ore]
    assert "STEEL_FUTURE" in target_symbols, f"Expected STEEL_FUTURE in targets of IRON_ORE, got {target_symbols}"
    
    assert len(cost_pressure_rels) >= 3, f"Expected >= 3 cost pressure relationships, got {len(cost_pressure_rels)}"
    
    assert weighted_drivers[0]["weight"] >= weighted_drivers[-1]["weight"], "Expected sorted weights descending"
    
    print("All assertions passed successfully!")

if __name__ == "__main__":
    main()
