package com.pwrsim.backend.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Persistent representation of reactor state snapshot.
 * Used for logging, persistence, and transient analysis.
 */
@Entity
@Table(name = "reactor_state")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class ReactorState {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false)
    private Long timestamp; // Unix milliseconds
    
    // ====== NEUTRONICS STATE ======
    @Column(nullable = false)
    private Double thermalPower; // MW
    
    @Column(nullable = false)
    private Double reactivity; // pcm (prompt critical + delayed)
    
    @Column(nullable = false)
    private Double boronConcentration; // ppm
    
    @Column(nullable = false)
    private Integer controlRodPosition; // % (0-100)
    
    // ====== THERMAL-HYDRAULICS STATE ======
    @Column(nullable = false)
    private Double coreInletTemp; // °C
    
    @Column(nullable = false)
    private Double coreOutletTemp; // °C
    
    @Column(nullable = false)
    private Double coreAvgTemp; // °C
    
    @Column(nullable = false)
    private Double primaryPressure; // MPa
    
    @Column(nullable = false)
    private Double primaryFlowRate; // kg/s
    
    @Column(nullable = false)
    private Double pressurizerLevel; // % (0-100)
    
    @Column(nullable = false)
    private Double pressurizerTemp; // °C
    
    // ====== SECONDARY SIDE STATE ======
    @Column(nullable = false)
    private Double steamGeneratorOutletTemp; // °C
    
    @Column(nullable = false)
    private Double steamGeneratorPressure; // MPa
    
    @Column(nullable = false)
    private Double steomMassFlowRate; // kg/s
    
    // ====== SYSTEM STATE ======
    @Column(nullable = false)
    private String operatingMode; // "STARTUP", "POWER_OPERATION", "SHUTDOWN", "SCRAM", "EMERGENCY_COOLING"
    
    @Column(nullable = false)
    private Boolean scramActive;
    
    @Column(nullable = false)
    private Boolean emergencyCoolingActive;
    
    @Column(length = 500)
    private String notes; // Any transient event or alarm state
}
