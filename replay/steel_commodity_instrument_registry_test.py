from ai.steel_commodity_instrument_registry import SteelCommodityInstrumentRegistry

def main():
    print("Instantiating SteelCommodityInstrumentRegistry...")
    registry = SteelCommodityInstrumentRegistry()

    # 1. Print all instruments
    print("\n--- All Instruments ---")
    all_insts = registry.all()
    for inst in all_insts:
        print(f"Symbol: {inst['symbol']}, Name: {inst['name']}, Category: {inst['category']}, Role: {inst['role']}, Priority: {inst['priority']}, Delivery Relevance: {inst['delivery_relevance']}")

    # 2. Print category steel
    print("\n--- Category: steel ---")
    steel_insts = registry.by_category("steel")
    for inst in steel_insts:
        print(f"Symbol: {inst['symbol']}, Name: {inst['name']}")

    # 3. Print role cost_driver
    print("\n--- Role: cost_driver ---")
    cost_drivers = registry.by_role("cost_driver")
    for inst in cost_drivers:
        print(f"Symbol: {inst['symbol']}, Name: {inst['name']}")

    # 4. Print priority_universe(max_priority=1)
    print("\n--- Priority Universe (max_priority=1) ---")
    priority_1 = registry.priority_universe(1)
    for inst in priority_1:
        print(f"Symbol: {inst['symbol']}, Priority: {inst['priority']}")

    # 5. Print delivery_relevant
    print("\n--- Delivery Relevant ---")
    delivery_rel = registry.delivery_relevant()
    for inst in delivery_rel:
        print(f"Symbol: {inst['symbol']}, Delivery Relevance: {inst['delivery_relevance']}")

    # Assertions
    print("\nRunning assertions...")
    assert len(all_insts) >= 15, f"Expected >= 15 instruments, got {len(all_insts)}"
    assert len(steel_insts) >= 3, f"Expected >= 3 steel instruments, got {len(steel_insts)}"
    assert len(cost_drivers) >= 3, f"Expected >= 3 cost drivers, got {len(cost_drivers)}"
    assert len(priority_1) >= 8, f"Expected >= 8 priority 1 instruments, got {len(priority_1)}"
    
    delivery_symbols = [inst["symbol"] for inst in delivery_rel]
    required_delivery = ["STEEL_PHYSICAL_PLATE", "STEEL_PHYSICAL_ANGLE", "STEEL_FUTURE", "GOLD"]
    for sym in required_delivery:
        assert sym in delivery_symbols, f"Expected '{sym}' in delivery relevant instruments, got {delivery_symbols}"
        
    print("All assertions passed successfully!")

if __name__ == "__main__":
    main()
