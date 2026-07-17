#!/usr/bin/env python3
"""
Setup script for multi-Pi synchronized display system
"""

import os
import sys

def main():
    print("Multi-Pi RGB Matrix Display Setup")
    print("=" * 40)
    
    # Get Pi role
    print("\nWhat is the role of this Pi?")
    print("1. Coordinator only (manages image cycling)")
    print("2. Coordinator + Display Pi #1 (recommended)")
    print("3. Display Pi #1 only (4 screens)")
    print("4. Display Pi #2 only (4 screens)")
    print("5. Display Pi #3 only (2 screens)")
    
    while True:
        choice = input("\nEnter choice (1-5): ").strip()
        if choice in ['1', '2', '3', '4', '5']:
            break
        print("Invalid choice, please enter 1, 2, 3, 4, or 5")
    
    if choice == '1':
        # Coordinator only setup
        print("\n=== COORDINATOR ONLY SETUP ===")
        print("This Pi will run the image coordinator service only.")
        print("To start the coordinator:")
        print("  python3 image_coordinator.py")
        print("\nThe coordinator will run on http://0.0.0.0:5001")
        print("Put all exhibition images in the 'exhibition' folder.")
        
    elif choice == '2':
        # Coordinator + Display Pi #1 setup
        print("\n=== COORDINATOR + DISPLAY PI #1 SETUP ===")
        print("This Pi will run BOTH the coordinator and display services.")
        
        # Update the display app configuration for Display #1
        config_file = "jpg_cycle_app_alt_screen_type.py"
        
        try:
            with open(config_file, 'r') as f:
                content = f.read()
            
            # Update configuration - use localhost since coordinator is on same Pi
            content = content.replace('COORDINATOR_IP = "192.168.1.100"', 'COORDINATOR_IP = "127.0.0.1"')
            content = content.replace('DISPLAY_ID = 0', 'DISPLAY_ID = 0')  # Display #1
            
            with open(config_file, 'w') as f:
                f.write(content)
            
            print(f"✓ Updated {config_file}")
            print("  - Coordinator IP: 127.0.0.1 (localhost)")
            print("  - Display ID: 0 (Display Pi #1)")
            
        except Exception as e:
            print(f"✗ Error updating config: {e}")
            print("You can manually edit the configuration in jpg_cycle_app_alt_screen_type.py:")
            print("  - Set COORDINATOR_IP = \"127.0.0.1\"")
            print("  - Set DISPLAY_ID = 0")
        
        print("\nTo start the system:")
        print("  1. First: python3 image_coordinator.py")
        print("  2. Then in another terminal: python3 jpg_cycle_app_alt_screen_type.py")
        print("\nPut all exhibition images in the 'exhibition' folder.")
        
    else:
        # Display Pi only setup
        if choice == '3':
            display_id = 0  # Display Pi #1
            pi_name = "#1 (4 screens)"
            config_file = "jpg_cycle_app_alt_screen_type.py"
        elif choice == '4':
            display_id = 1  # Display Pi #2
            pi_name = "#2 (4 screens)"
            config_file = "jpg_cycle_app_alt_screen_type.py"
        else:  # choice == '5'
            display_id = 2  # Display Pi #3
            pi_name = "#3 (2 screens)"
            config_file = "jpg_cycle_app_2_screen.py"
        
        print(f"\n=== DISPLAY PI {pi_name} SETUP ===")
        
        # Get coordinator IP
        coordinator_ip = input(f"\nEnter the IP address of the coordinator Pi: ").strip()
        if not coordinator_ip:
            coordinator_ip = "192.168.1.100"  # default
        
        # Update the display app configuration
        
        try:
            with open(config_file, 'r') as f:
                content = f.read()
            
            # Update configuration
            content = content.replace('COORDINATOR_IP = "192.168.1.100"', f'COORDINATOR_IP = "{coordinator_ip}"')
            content = content.replace('DISPLAY_ID = 0', f'DISPLAY_ID = {display_id}')
            content = content.replace('DISPLAY_ID = 1', f'DISPLAY_ID = {display_id}')
            content = content.replace('DISPLAY_ID = 2', f'DISPLAY_ID = {display_id}')
            
            with open(config_file, 'w') as f:
                f.write(content)
            
            print(f"✓ Updated {config_file}")
            print(f"  - Coordinator IP: {coordinator_ip}")
            print(f"  - Display ID: {display_id}")
            
        except Exception as e:
            print(f"✗ Error updating config: {e}")
            print(f"You can manually edit the configuration in {config_file}:")
            print(f"  - Set COORDINATOR_IP = \"{coordinator_ip}\"")
            print(f"  - Set DISPLAY_ID = {display_id}")
        
        print(f"\nTo start the display:")
        print(f"  python3 {config_file}")
        
        print(f"\nMake sure the coordinator Pi ({coordinator_ip}) is running first!")
    
    print("\n" + "=" * 40)
    print("Setup complete!")

if __name__ == "__main__":
    main()
