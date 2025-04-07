import os
import sys
import subprocess
import threading
import time

def run_simulation():
    """Start SUMO with required parameters"""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_simulation.py")
    python_exe = sys.executable
    
    subprocess.call([python_exe, script_path])

def run_emergency_helper():
    """Start the emergency force movement helper"""
    # Wait for SUMO to initialize
    time.sleep(5)
    
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergency_force_movement.py")
    python_exe = sys.executable
    
    subprocess.call([python_exe, script_path])

def main():
    """Run both the simulation and emergency helper"""
    # Start SUMO in a separate thread
    sim_thread = threading.Thread(target=run_simulation)
    sim_thread.daemon = True
    sim_thread.start()
    
    # Run the helper in the main thread
    run_emergency_helper()
    
    # Wait for simulation to finish
    sim_thread.join()

if __name__ == "__main__":
    main()
