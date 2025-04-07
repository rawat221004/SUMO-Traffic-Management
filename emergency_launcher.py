import os
import sys
import subprocess

def run_simulation():
    """Run SUMO with the correct parameters to enable emergency vehicle movement"""
    
    # Define the SUMO binary and config file
    sumo_binary = "sumo-gui"  # Use GUI version for visualization
    sumo_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm.sumocfg")
    
    # Define additional command-line parameters for better emergency vehicle movement
    additional_params = [
        "--time-to-teleport", "300",  # Allow teleporting after 300 seconds as last resort
        "--ignore-junction-blocker", "60",  # Wait 60 seconds before ignoring junction blockers
        "--collision.action", "warn",  # Warn on collisions but don't remove vehicles
        "--step-length", "0.1",  # Smaller step length for smoother simulation
        "--emergencydecel", "9.0",  # Higher emergency deceleration
        "--max-depart-delay", "1",  # Ensure vehicles depart quickly
        "--waiting-time-memory", "300",  # Remember waiting time for longer
        "--lanechange.overtake-right", "true"  # Allow overtaking on the right
    ]
    
    # Construct the command
    command = [sumo_binary, "-c", sumo_config] + additional_params
    
    print("Starting SUMO with the following command:")
    print(" ".join(command))
    
    # Run SUMO
    subprocess.call(command)

if __name__ == "__main__":
    run_simulation()
