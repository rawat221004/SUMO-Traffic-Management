import os
import sys
import subprocess
import threading
import time

def run_sumo():
    """Run the SUMO simulation with optimized parameters for emergency vehicles"""
    # Define the SUMO binary and config file
    sumo_binary = "sumo-gui"
    sumo_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm.sumocfg")
    
    # Define parameters for better emergency vehicle movement
    params = [
        "--remote-port", "8813",  # Port for TraCI connection
        "--time-to-teleport", "300",  # Allow teleport after 5 minutes as last resort
        "--collision.action", "warn",  # Only warn on collisions
        "--step-length", "0.1",  # Smaller steps for smoother movement
        "--ignore-junction-blocker", "60",  # Wait 60 seconds before ignoring blockers
        "--emergencydecel", "9.0",  # Higher emergency deceleration
        "--lanechange.overtake-right", "true",  # Allow overtaking on the right
        "--waiting-time-memory", "300",  # Remember waiting time for longer
        "--max-depart-delay", "1"  # Reduce waiting time for departure
    ]
    
    # Construct command
    command = [sumo_binary, "-c", sumo_config] + params
    
    print("Starting SUMO with command:")
    print(" ".join(command))
    
    # Run SUMO
    subprocess.call(command)

def run_teleport_helper():
    """Run the emergency teleport helper script"""
    # Wait for SUMO to start
    time.sleep(5)
    
    # Run the teleport helper script
    helper_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergency_teleport_helper.py")
    
    # Make sure Python is in path
    python_cmd = sys.executable
    
    command = [python_cmd, helper_script]
    
    print("Starting teleport helper with command:")
    print(" ".join(command))
    
    # Run the helper script
    subprocess.call(command)

def main():
    """Run both SUMO and the teleport helper"""
    # Start SUMO in a separate thread
    sumo_thread = threading.Thread(target=run_sumo)
    sumo_thread.daemon = True
    sumo_thread.start()
    
    # Run teleport helper in main thread
    run_teleport_helper()
    
    # Wait for SUMO to finish if needed
    sumo_thread.join()

if __name__ == "__main__":
    main()
