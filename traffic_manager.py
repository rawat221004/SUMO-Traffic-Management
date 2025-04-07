import traci
import logging
import math
import os
from collections import defaultdict

# Setup logging (ensure level is DEBUG if needed)
log_dir = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG for detailed output
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    filename=os.path.join(log_dir, 'traffic_simulation.log'),
    filemode='w'  # Overwrite log each time
)

# Get the root logger's handlers AFTER basicConfig is called
log_handlers = logging.getLogger().handlers

class TrafficManager:
    def __init__(self):
        # Dictionary to track preemption states
        self.preempted_lights = {}
        
        # Emergency vehicle priorities (lower number = higher priority)
        self.emergency_priorities = {
            "ambulance": 1,    # Highest priority
            "firetruck": 2,
            "police": 3
        }
        
        # Track vehicles that have been flagged for potential teleportation
        self.stuck_vehicles = {}
        
        # Duration to maintain green after emergency vehicle passes (seconds)
        self.green_extension = 5
        
        # Distance threshold for emergency vehicle detection near intersections (meters)
        self.emergency_detection_distance = 50
        
        # Emergency vehicle types
        self.emergency_types = ["ambulance", "firetruck", "police"]
        
        # Track configured emergency vehicles
        self.configured_emergency_vehicles = set()
        
        # Minimum queue length to trigger preemption
        self.min_queue_for_preemption = 8
        
        # Setup emergency vehicles by ensuring they ignore traffic lights at initialization
        self.setup_emergency_vehicles()
        
        # Subscribe to simulation variables to monitor potential teleportations
        if traci.isLoaded():
            traci.simulation.subscribe([
                traci.constants.VAR_TIME_STEP,
                traci.constants.VAR_DEPARTED_VEHICLES_IDS,
                traci.constants.VAR_TELEPORT_STARTING_VEHICLES_IDS,
                traci.constants.VAR_TELEPORT_ENDING_VEHICLES_IDS
            ])
    
    def setup_emergency_vehicles(self):
        """Configure emergency vehicles to ignore traffic lights when they enter the simulation"""
        logging.info("Setting up emergency vehicles with special permissions")
        
        # Listen for emergency vehicles entering simulation
        traci.simulation.subscribe([traci.constants.VAR_DEPARTED_VEHICLES_IDS])
    
    def configure_emergency_vehicle(self, veh_id, veh_type):
        """Apply special settings to emergency vehicles"""
        try:
            # Allow emergency vehicles to ignore all traffic rules and speed limits
            traci.vehicle.setSpeedMode(veh_id, 0)  # 0 = ignore all restrictions
            
            # Allow all lane changes without restrictions
            traci.vehicle.setLaneChangeMode(veh_id, 0)  # No restrictions
            
            # Set higher speed capability
            traci.vehicle.setMaxSpeed(veh_id, 50)  # Much higher max speed
            traci.vehicle.setSpeedFactor(veh_id, 2.5)  # Higher speed factor
            
            # Set immediate high speed to get the vehicle moving
            traci.vehicle.setSpeed(veh_id, 15.0)
            
            # Increase acceleration capabilities
            traci.vehicle.setAccel(veh_id, 5.0)
            traci.vehicle.setDecel(veh_id, 7.0)
            
            logging.info(f"Configured emergency vehicle {veh_id} ({veh_type}) with UNRESTRICTED movement")
        except traci.TraCIException as e:
            logging.error(f"TraCI Error configuring emergency vehicle {veh_id}: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error configuring emergency vehicle {veh_id}: {str(e)}")
    
    def step(self):
        """Execute one simulation step"""
        # Add a print statement to confirm execution
        print(f"Executing TrafficManager step at sim time: {traci.simulation.getTime():.2f}")
        logging.debug(f"Executing step at sim time: {traci.simulation.getTime():.2f}")  # Also log it

        # Process simulation subscriptions
        subscription_results = traci.simulation.getSubscriptionResults()
        
        if subscription_results:
            # Check for newly departed vehicles and configure emergency vehicles
            departed_vehicles = subscription_results.get(traci.constants.VAR_DEPARTED_VEHICLES_IDS, [])
            for veh_id in departed_vehicles:
                veh_type = traci.vehicle.getTypeID(veh_id)
                if veh_type in self.emergency_types:
                    self.configure_emergency_vehicle(veh_id, veh_type)
                    self.configured_emergency_vehicles.add(veh_id)
        
        # Handle emergency vehicles first
        self.process_emergency_vehicles()
        
        # Update traffic signals based on emergency vehicle proximity
        self.update_traffic_signals()
        
        # Check for and handle stuck vehicles (both emergency and regular)
        self.check_stuck_vehicles()

        # Manually flush log handlers at the end of each step
        try:
            for handler in log_handlers:
                handler.flush()
            # print(f"Flushed {len(log_handlers)} log handlers.")  # Optional: uncomment for verbose flushing confirmation
        except Exception as e:
            print(f"Error flushing log handlers: {e}")  # Print error if flushing fails
    
    def process_emergency_vehicles(self):
        """Configure and handle emergency vehicles"""
        current_vehicles = traci.vehicle.getIDList()
        vehicles_to_process = list(current_vehicles)  # Process a copy

        for veh_id in vehicles_to_process:
            # Check if vehicle still exists in simulation
            if veh_id not in current_vehicles:
                continue

            try:
                veh_type = traci.vehicle.getTypeID(veh_id)

                # Only process emergency vehicles
                if veh_type in self.emergency_types:
                    # Configure vehicle if not already done
                    if veh_id not in self.configured_emergency_vehicles:
                        self.configure_emergency_vehicle(veh_id, veh_type)
                        self.configured_emergency_vehicles.add(veh_id)
                        # Force immediate movement upon configuration
                        traci.vehicle.setSpeed(veh_id, 15.0)

                    # Force movement regardless of conditions
                    speed = traci.vehicle.getSpeed(veh_id)
                    if speed < 5.0:  # If vehicle isn't moving fast enough
                        # Force higher speed
                        traci.vehicle.setSpeed(veh_id, 15.0)
                        # Attempt unsticking operations
                        self.unstick_emergency_vehicle(veh_id)

            except traci.TraCIException as e:
                # Handle cases where vehicle might have left the simulation between getIDList and processing
                if "Vehicle '{}' is not known".format(veh_id) in str(e):
                    logging.warning(f"Vehicle {veh_id} left simulation during processing.")
                    if veh_id in self.configured_emergency_vehicles:
                        self.configured_emergency_vehicles.remove(veh_id)
                    if veh_id in self.stuck_vehicles:
                        del self.stuck_vehicles[veh_id]
                else:
                    logging.error(f"Error processing vehicle {veh_id}: {str(e)}")
            except Exception as e:  # Catch other potential errors
                logging.error(f"Unexpected error processing vehicle {veh_id}: {str(e)}")
    
    def boost_emergency_vehicle(self, veh_id):
        """Periodically boost emergency vehicles to ensure movement"""
        try:
            # Get current vehicle state
            speed = traci.vehicle.getSpeed(veh_id)
            
            # Apply boost only if speed is below target
            if speed < 15.0:
                # Reset any restrictions that might be hampering movement
                traci.vehicle.setSpeedMode(veh_id, 0)  # Ignore all restrictions
                traci.vehicle.setLaneChangeMode(veh_id, 0)  # Allow all lane changes
                
                # Force acceleration
                traci.vehicle.slowDown(veh_id, 20.0, 2.0)  # Target speed of 20 m/s within 2 seconds
                
                logging.info(f"Boosting emergency vehicle {veh_id} with current speed {speed:.2f}")
        except traci.TraCIException as e:
            logging.warning(f"Failed to boost emergency vehicle {veh_id}: {e}")
        except Exception as e:
            logging.warning(f"Error during emergency vehicle boost for {veh_id}: {e}")
    
    def unstick_emergency_vehicle(self, veh_id):
        """Special handling for stuck emergency vehicles with enhanced debugging"""
        try:
            # Always attempt unsticking immediately
            current_time = traci.simulation.getTime()
            
            edge_id = traci.vehicle.getRoadID(veh_id)
            lane_id = traci.vehicle.getLaneID(veh_id)
            
            logging.debug(f"Attempting to unstick emergency vehicle {veh_id} on {edge_id}")

            # 1. Reset all traffic rule compliance settings
            traci.vehicle.setSpeedMode(veh_id, 0)  # Ignore all rules
            traci.vehicle.setLaneChangeMode(veh_id, 0)  # No lane change restrictions
            
            # 2. Clear path ahead aggressively
            self.clear_path(veh_id, distance=50)
            
            # 3. Try teleporting slightly forward if stuck and on a regular road (not junction)
            if not edge_id.startswith(':'):  # Not on junction
                try:
                    # Calculate teleport distance - move forward on current lane
                    lane_pos = traci.vehicle.getLanePosition(veh_id)
                    lane_length = traci.lane.getLength(lane_id)
                    
                    # Only teleport if there's room ahead
                    if lane_pos < lane_length - 10:
                        new_pos = min(lane_pos + 10, lane_length - 5)
                        traci.vehicle.moveTo(veh_id, lane_id, new_pos)
                        logging.info(f"Teleported {veh_id} forward on lane {lane_id}")
                except traci.TraCIException as e:
                    logging.warning(f"Failed to teleport {veh_id}: {e}")
            
            # 4. Force high speed regardless of surroundings
            traci.vehicle.setSpeed(veh_id, 15.0)
            
            # Update last unstick attempt time
            self.stuck_vehicles[veh_id] = current_time

        except traci.TraCIException as e:
            # Handle case where vehicle might disappear during processing
            if "Vehicle '{}' is not known".format(veh_id) in str(e):
                logging.warning(f"Vehicle {veh_id} disappeared during unstick attempt.")
                if veh_id in self.stuck_vehicles:
                    del self.stuck_vehicles[veh_id]
                if veh_id in self.configured_emergency_vehicles:
                    self.configured_emergency_vehicles.remove(veh_id)
            else:
                logging.error(f"TraCI Error unsticking emergency vehicle {veh_id}: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error unsticking emergency vehicle {veh_id}: {str(e)}")
    
    def clear_path(self, emergency_veh_id, distance=30):
        """Move other vehicles out of the way of an emergency vehicle"""
        try:
            # Get emergency vehicle data
            emergency_pos = traci.vehicle.getPosition(emergency_veh_id)
            emergency_lane = traci.vehicle.getLaneID(emergency_veh_id)
            emergency_edge = traci.vehicle.getRoadID(emergency_veh_id)
            
            # If in junction, use a different approach
            if emergency_edge.startswith(':'):
                # For junctions, clear all vehicles in a radius
                radius = distance
                for veh_id in traci.vehicle.getIDList():
                    if veh_id == emergency_veh_id or traci.vehicle.getTypeID(veh_id) in self.emergency_types:
                        continue
                    
                    veh_pos = traci.vehicle.getPosition(veh_id)
                    dist = math.sqrt((emergency_pos[0] - veh_pos[0])**2 + (emergency_pos[1] - veh_pos[1])**2)
                    
                    if dist < radius:
                        try:
                            # Slow down blocking vehicles dramatically
                            traci.vehicle.slowDown(veh_id, 0.5, 1.0)  # Almost stop
                            logging.info(f"Slowing junction-blocking vehicle {veh_id} for {emergency_veh_id}")
                        except:
                            pass
                return
                
            # For normal edges, get emergency lane index
            try:
                emergency_lane_index = int(emergency_lane.split('_')[-1])
            except:
                return  # Skip if can't parse lane index
                
            # Check vehicles on the same edge and nearby edges
            nearby_edges = [emergency_edge]
            vehicles_to_check = []
            
            for edge in nearby_edges:
                vehicles_to_check.extend(traci.edge.getLastStepVehicleIDs(edge))
            
            # Process vehicles
            for veh_id in vehicles_to_check:
                if veh_id == emergency_veh_id or traci.vehicle.getTypeID(veh_id) in self.emergency_types:
                    continue  # Skip self and other emergency vehicles
                    
                try:
                    veh_pos = traci.vehicle.getPosition(veh_id)
                    veh_lane = traci.vehicle.getLaneID(veh_id)
                    veh_edge = traci.vehicle.getRoadID(veh_id)
                    
                    # Skip if not on same edge
                    if veh_edge != emergency_edge:
                        continue
                        
                    try:
                        veh_lane_index = int(veh_lane.split('_')[-1])
                    except:
                        continue  # Skip if can't parse lane index
                    
                    # Calculate distance along the lane
                    emergency_lane_pos = traci.vehicle.getLanePosition(emergency_veh_id)
                    veh_lane_pos = traci.vehicle.getLanePosition(veh_id)
                    
                    # Check if vehicle is blocking (ahead within distance or on same lane)
                    is_blocking = False
                    
                    # Same lane and ahead
                    if veh_lane == emergency_lane and veh_lane_pos > emergency_lane_pos and (veh_lane_pos - emergency_lane_pos) < distance:
                        is_blocking = True
                    
                    # Adjacent lane and in proximity
                    elif veh_lane != emergency_lane and abs(veh_lane_pos - emergency_lane_pos) < distance:
                        is_blocking = True
                    
                    if is_blocking:
                        # Aggressive path clearing for blocking vehicles
                        lane_count = traci.edge.getLaneNumber(emergency_edge)
                        
                        if lane_count > 1:
                            # Try to move vehicle to any lane that's not the emergency vehicle's lane
                            for target_lane in range(lane_count):
                                if target_lane != emergency_lane_index:
                                    try:
                                        traci.vehicle.changeLane(veh_id, target_lane, 0)  # Immediate lane change
                                        logging.info(f"Moving vehicle {veh_id} to lane {target_lane} for {emergency_veh_id}")
                                        break
                                    except:
                                        continue
                        
                        # Slow down blocking vehicles dramatically
                        try:
                            traci.vehicle.slowDown(veh_id, 0.5, 1.0)  # Almost stop
                            logging.info(f"Slowing blocking vehicle {veh_id} for {emergency_veh_id}")
                        except:
                            pass
                except:
                    continue  # Skip if vehicle processing fails
                    
        except traci.TraCIException as e:
            logging.error(f"TraCI Error clearing path for {emergency_veh_id}: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error clearing path for {emergency_veh_id}: {str(e)}")
    
    def update_traffic_signals(self):
        """Find emergency vehicles in long queues at red lights and preempt signals"""
        # Track emergency vehicles needing preemption by intersection
        emergency_by_intersection = defaultdict(list)

        # Get all traffic lights
        traffic_lights = traci.trafficlight.getIDList()
        current_vehicles = set(traci.vehicle.getIDList())

        # Check each emergency vehicle
        for veh_id in current_vehicles:
            try:
                veh_type = traci.vehicle.getTypeID(veh_id)

                if veh_type in self.emergency_types:
                    # Check if the vehicle is stopped or moving very slowly
                    speed = traci.vehicle.getSpeed(veh_id)
                    if speed < 1.0:  # Consider vehicles moving very slowly or stopped
                        lane_id = traci.vehicle.getLaneID(veh_id)
                        edge_id = traci.vehicle.getRoadID(veh_id)

                        # Check the next traffic light ahead
                        next_tls_data = traci.vehicle.getNextTLS(veh_id)

                        if next_tls_data:
                            tls_id = next_tls_data[0][0]
                            tls_state = next_tls_data[0][3]  # State of the upcoming signal for this vehicle
                            tls_dist = next_tls_data[0][2]

                            # Check if the light is red (or red-yellow) and vehicle is close
                            if tls_state.lower() == 'r' and tls_dist < 20:  # Close to red light
                                # Check the queue length on the vehicle's current lane
                                queue_length = traci.lane.getLastStepHaltingNumber(lane_id)

                                if queue_length >= self.min_queue_for_preemption:
                                    # Found an emergency vehicle in a long queue at a red light
                                    priority = self.emergency_priorities.get(veh_type, 99)
                                    position = traci.vehicle.getPosition(veh_id)

                                    emergency_by_intersection[tls_id].append({
                                        'id': veh_id,
                                        'type': veh_type,
                                        'priority': priority,
                                        'edge': edge_id,
                                        'distance': tls_dist
                                    })

            except traci.TraCIException:
                pass
            except Exception as e:
                logging.error(f"Error checking vehicle {veh_id} for signal preemption: {e}")

        # Process intersections with emergency vehicles found in queues
        for tls_id, vehicles in emergency_by_intersection.items():
            if vehicles:
                # Sort by priority (lower number = higher priority)
                vehicles.sort(key=lambda x: x['priority'])

                # Preempt for highest priority vehicle in the queue at this light
                self.preempt_signal(tls_id, vehicles[0])

        # Check if any preemptions need to be released
        self.check_signal_release()
    
    def preempt_signal(self, tls_id, vehicle):
        """Preempt traffic signal for emergency vehicle"""
        try:
            current_time = traci.simulation.getTime()
            # Manage preemption state (existing logic seems okay)
            if tls_id not in self.preempted_lights:
                self.preempted_lights[tls_id] = {
                    'program': traci.trafficlight.getProgram(tls_id),
                    'phase': traci.trafficlight.getPhase(tls_id),
                    'vehicle_id': vehicle['id'],
                    'priority': vehicle['priority'],
                    'time': current_time,
                    'passed': False
                }
                logging.info(f"Preempting traffic light {tls_id} for {vehicle['type']} {vehicle['id']} approaching from {vehicle['edge']}")
            elif vehicle['priority'] < self.preempted_lights[tls_id]['priority']:
                # Update if higher priority vehicle arrives
                self.preempted_lights[tls_id].update({
                    'vehicle_id': vehicle['id'],
                    'priority': vehicle['priority'],
                    'time': current_time,
                    'passed': False
                })
                logging.info(f"Updating preemption at {tls_id} for higher priority {vehicle['type']} {vehicle['id']} approaching from {vehicle['edge']}")
            elif vehicle['id'] == self.preempted_lights[tls_id]['vehicle_id']:
                # Update time if same vehicle is still waiting
                self.preempted_lights[tls_id]['time'] = current_time
            else:
                # Lower priority vehicle arrives while already preempted, ignore
                return

            # --- Start Refined Logic ---
            approach_edge = vehicle['edge']
            controlled_links = traci.trafficlight.getControlledLinks(tls_id)
            if not controlled_links:
                logging.warning(f"No controlled links found for TLS {tls_id}. Cannot preempt.")
                return

            # Determine the number of signals in the phase definition
            # Assuming all phases have the same length state string
            program_logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)
            if not program_logic or not program_logic[0].phases:
                 logging.warning(f"Could not get program logic or phases for TLS {tls_id}. Cannot determine signal count.")
                 return
            num_signals = len(program_logic[0].phases[0].state) # Length of the state string (e.g., "GrGr")

            # Initialize the new state string, default to red
            new_state = list('r' * num_signals)
            found_signal_index = -1

            logging.debug(f"Preempting {tls_id} for veh {vehicle['id']} from edge {approach_edge}. Controlled Links: {controlled_links}")

            # Iterate through the controlled links to find the one matching the approach edge
            for links_for_signal_group in controlled_links:
                for link_info_tuple in links_for_signal_group:
                    # link_info_tuple format: (incoming_lane, outgoing_lane, via_lane, incoming_edge, outgoing_edge, direction, signal_index)
                    if link_info_tuple and len(link_info_tuple) > 6:
                        incoming_edge = link_info_tuple[3]
                        signal_index = link_info_tuple[6] # This is the crucial index for the state string

                        if incoming_edge == approach_edge:
                            # Found the link corresponding to the vehicle's approach
                            if 0 <= signal_index < num_signals:
                                new_state[signal_index] = 'G' # Set this specific signal index to Green
                                found_signal_index = signal_index
                                logging.debug(f"Found matching link for edge {approach_edge}. Setting signal index {signal_index} to 'G'.")
                                # Optional: break if only one signal controls this approach,
                                # but continue checking in case multiple signals need setting (unlikely but possible)
                            else:
                                logging.warning(f"Signal index {signal_index} from controlled links is out of bounds for state string length {num_signals} at TLS {tls_id}.")

            if found_signal_index == -1:
                logging.warning(f"Could not find signal index for approach edge '{approach_edge}' in controlled links for TLS {tls_id}. State not changed.")
                # Optionally, you might want to revert preemption status if the signal can't be set
                # del self.preempted_lights[tls_id]
                return # Don't set the state if we couldn't find the right signal

            final_state_str = "".join(new_state)
            logging.info(f"Setting TLS {tls_id} state to '{final_state_str}' for vehicle {vehicle['id']}")
            traci.trafficlight.setRedYellowGreenState(tls_id, final_state_str)
            # --- End Refined Logic ---

        except traci.TraCIException as e:
            logging.error(f"TraCI Error preempting signal {tls_id} for vehicle {vehicle.get('id', 'N/A')}: {str(e)}")
            # Clean up preemption state if error occurs during setting
            if tls_id in self.preempted_lights:
                 del self.preempted_lights[tls_id]
        except Exception as e:
            logging.error(f"Unexpected error preempting signal {tls_id} for vehicle {vehicle.get('id', 'N/A')}: {str(e)}")
            # Clean up preemption state
            if tls_id in self.preempted_lights:
                 del self.preempted_lights[tls_id]
    
    def check_signal_release(self):
        """Check if any preempted signals can be released"""
        current_time = traci.simulation.getTime()
        to_release = []
        current_vehicles = set(traci.vehicle.getIDList())

        for tls_id, info in list(self.preempted_lights.items()):
            veh_id = info['vehicle_id']

            if veh_id not in current_vehicles:
                if not info['passed']:
                    info['passed'] = True
                    info['time'] = current_time
            else:
                if not info['passed']:
                    veh_pos = traci.vehicle.getPosition(veh_id)
                    tls_pos = traci.junction.getPosition(tls_id)
                    distance = math.sqrt((veh_pos[0] - tls_pos[0])**2 + (veh_pos[1] - tls_pos[1])**2)
                    if distance > self.emergency_detection_distance * 1.1:
                        info['passed'] = True
                        info['time'] = current_time
                        logging.info(f"Vehicle {veh_id} has passed traffic light {tls_id}")

            grace_period = 5
            if info['passed'] and (current_time - info['time']) >= grace_period:
                to_release.append(tls_id)

        for tls_id in to_release:
            if tls_id in self.preempted_lights:
                try:
                    info = self.preempted_lights[tls_id]
                    traci.trafficlight.setProgram(tls_id, info['program'])
                    logging.info(f"Released preemption for traffic light {tls_id}")
                    del self.preempted_lights[tls_id]
                except traci.TraCIException as e:
                    logging.error(f"TraCI Error releasing preemption for {tls_id}: {str(e)}")
                    if tls_id in self.preempted_lights:
                        del self.preempted_lights[tls_id]
                except Exception as e:
                    logging.error(f"Unexpected error releasing preemption for {tls_id}: {str(e)}")
                    if tls_id in self.preempted_lights:
                        del self.preempted_lights[tls_id]
    
    def check_stuck_vehicles(self):
        """Handle regular stuck vehicles and cleanup"""
        current_time = traci.simulation.getTime()
        current_vehicles = set(traci.vehicle.getIDList())

        stuck_to_remove = [veh_id for veh_id in self.stuck_vehicles if veh_id not in current_vehicles]
        for veh_id in stuck_to_remove:
            del self.stuck_vehicles[veh_id]

        for veh_id in current_vehicles:
            try:
                if traci.vehicle.getTypeID(veh_id) in self.emergency_types:
                    continue

                speed = traci.vehicle.getSpeed(veh_id)
                waiting_time = traci.vehicle.getWaitingTime(veh_id)

                if speed < 0.1 and waiting_time > 120:
                    last_handled = self.stuck_vehicles.get(veh_id, 0)
                    if (current_time - last_handled) >= 60:
                        logging.info(f"Regular vehicle {veh_id} is stuck, attempting reroute.")
                        traci.vehicle.rerouteTraveltime(veh_id, currentTravelTime=True)
                        self.stuck_vehicles[veh_id] = current_time
            except traci.TraCIException:
                if veh_id in self.stuck_vehicles:
                    del self.stuck_vehicles[veh_id]
            except Exception as e:
                logging.error(f"Error checking stuck status for vehicle {veh_id}: {e}")
