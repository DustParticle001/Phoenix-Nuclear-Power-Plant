package com.pwrsim.backend.controller;

import com.pwrsim.backend.simulation.ReactorSimulationService;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * REST API controller for reactor status and control commands.
 * Routes to simulation engines for actual physics computation.
 */
@RestController
@RequestMapping("/api/reactor")
@CrossOrigin(origins = "*")
@Slf4j
public class ReactorController {
    
    @Autowired
    private ReactorSimulationService simulationService;
    
    /**
     * GET /api/reactor/status
     * Returns current reactor state (power, temps, pressure, etc.)
     */
    @GetMapping("/status")
    public ResponseEntity<ReactorStatusResponse> getStatus() {
        log.debug("GET /status requested");
        
        // TODO: Get state from simulationService and format response
        ReactorSimulationService.ReactorSimulationState state = simulationService.getCurrentState();
        
        ReactorStatusResponse response = new ReactorStatusResponse();
        if (state != null && state.getNeutronicsState() != null && state.getThermalHydraulicsState() != null) {
            response.setState(state.getOperatingMode());
            response.setTemperature(state.getThermalHydraulicsState().getCoreAvgTemp());
            response.setPressure(state.getThermalHydraulicsState().getPrimaryPressure());
            response.setPowerLevel(state.getNeutronicsState().getThermalPower());
        }
        
        return ResponseEntity.ok(response);
    }
    
    /**
     * POST /api/reactor/control
     * Send control command (rod movement, power setpoint, etc.)
     */
    @PostMapping("/control")
    public ResponseEntity<ControlResponse> controlReactor(@RequestBody ReactorCommand command) {
        log.info("POST /control: action={}, value={}", command.getAction(), command.getValue());
        
        try {
            // TODO: Route commands to appropriate control functions
            switch (command.getAction()) {
                case "power_setpoint":
                    simulationService.setPowerSetpoint(command.getValue());
                    break;
                case "temperature_setpoint":
                    simulationService.setTemperatureSetpoint(command.getValue());
                    break;
                case "control_rod_position":
                    simulationService.moveControlRods(command.getValue().intValue());
                    break;
                case "boron_concentration":
                    simulationService.setBoronConcentration(command.getValue());
                    break;
                default:
                    log.warn("Unknown command: {}", command.getAction());
                    return ResponseEntity.badRequest().body(
                        new ControlResponse("error", "Unknown command: " + command.getAction())
                    );
            }
            
            return ResponseEntity.ok(new ControlResponse("success", "Command processed: " + command.getAction()));
        } catch (Exception e) {
            log.error("Error processing control command", e);
            return ResponseEntity.status(500).body(
                new ControlResponse("error", "Failed to process command: " + e.getMessage())
            );
        }
    }
    
    /**
     * GET /api/reactor/status/detailed
     * Returns detailed reactor state (all parameters)
     */
    @GetMapping("/status/detailed")
    public ResponseEntity<ReactorDetailedStatus> getDetailedStatus() {
        log.debug("GET /status/detailed requested");
        
        // TODO: Format full state from simulationService
        ReactorSimulationService.ReactorSimulationState state = simulationService.getCurrentState();
        ReactorDetailedStatus response = new ReactorDetailedStatus();
        
        if (state != null) {
            if (state.getNeutronicsState() != null) {
                response.setPower(state.getNeutronicsState().getThermalPower());
                response.setReactivity(state.getNeutronicsState().getReactivity());
            }
            if (state.getThermalHydraulicsState() != null) {
                response.setCoreInletTemp(state.getThermalHydraulicsState().getCoreInletTemp());
                response.setCoreOutletTemp(state.getThermalHydraulicsState().getCoreOutletTemp());
                response.setCoreAvgTemp(state.getThermalHydraulicsState().getCoreAvgTemp());
                response.setPrimaryPressure(state.getThermalHydraulicsState().getPrimaryPressure());
                response.setPrimaryFlow(state.getThermalHydraulicsState().getPrimaryMassFlow());
                response.setPressurizerLevel(state.getThermalHydraulicsState().getPressurizerLevel());
                response.setPressurizerTemp(state.getThermalHydraulicsState().getPressurizerTemp());
            }
        }
        
        return ResponseEntity.ok(response);
    }
    
    /**
     * POST /api/reactor/simulate/step
     * Perform one simulation timestep
     */
    @PostMapping("/simulate/step")
    public ResponseEntity<String> simulateStep() {
        log.debug("POST /simulate/step requested");
        
        try {
            simulationService.step();
            return ResponseEntity.ok("Simulation stepped");
        } catch (Exception e) {
            log.error("Error stepping simulation", e);
            return ResponseEntity.status(500).body("Error: " + e.getMessage());
        }
    }
    
    /**
     * POST /api/reactor/simulate/start
     * Start continuous simulation
     */
    @PostMapping("/simulate/start")
    public ResponseEntity<String> startSimulation() {
        log.info("POST /simulate/start requested");
        
        try {
            simulationService.startSimulation();
            return ResponseEntity.ok("Simulation started");
        } catch (Exception e) {
            log.error("Error starting simulation", e);
            return ResponseEntity.status(500).body("Error: " + e.getMessage());
        }
    }
    
    /**
     * POST /api/reactor/simulate/stop
     * Stop simulation
     */
    @PostMapping("/simulate/stop")
    public ResponseEntity<String> stopSimulation() {
        log.info("POST /simulate/stop requested");
        
        try {
            simulationService.stopSimulation();
            return ResponseEntity.ok("Simulation stopped");
        } catch (Exception e) {
            log.error("Error stopping simulation", e);
            return ResponseEntity.status(500).body("Error: " + e.getMessage());
        }
    }
    
    // ====== RESPONSE DTOs ======
    
    @Data
    public static class ReactorStatusResponse {
        private String state;
        private Double temperature;
        private Double pressure;
        private Double powerLevel;
    }
    
    @Data
    public static class ReactorDetailedStatus {
        private Double power;
        private Double reactivity;
        private Double coreInletTemp;
        private Double coreOutletTemp;
        private Double coreAvgTemp;
        private Double primaryPressure;
        private Double primaryFlow;
        private Double pressurizerLevel;
        private Double pressurizerTemp;
    }
    
    @Data
    public static class ControlResponse {
        private String status;
        private String message;
        
        public ControlResponse(String status, String message) {
            this.status = status;
            this.message = message;
        }
    }
    
    @Data
    public static class ReactorCommand {
        private String action;
        private Double value;
    }
}
