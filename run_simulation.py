import os
import sys
import subprocess

def main():
    """Run SUMO with parameters to disable teleportation and launch TraCI"""
    
    # SUMO binary - use GUI for visualization
    sumo_binary = "sumo-gui"
    
    # Configuration file
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm.sumocfg")
    
    # Command line parameters
    command = [
        sumo_binary,
        "-c", config_file,
        "--time-to-teleport", "300",  # Allow teleporting after 5 minutes as last resort
        "--collision.action", "warn",  # Only warn on collisions, don't remove vehicles
        "--step-length", "0.1",  # Smaller steps for smoother movement
        "--lanechange.duration", "0",  # Instant lane changes
        "--ignore-junction-blocker", "60",  # Wait before handling junction blockers
        "--emergencydecel", "9.0",  # Higher emergency deceleration
        "--max-depart-delay", "1"  # Ensure vehicles depart quickly
    ]
    
    print("Starting simulation with command:")
    print(" ".join(command))
    
    # Run the simulation
    subprocess.call(command)

if __name__ == "__main__":
    main()
